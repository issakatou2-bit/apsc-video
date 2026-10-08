#!/usr/bin/env python3
"""投稿の棚（queue/）から、公開の時刻が近い台本を、声 → 動画 → 予約公開まで進める。

なぜ要るのか:
  2026-10-08 本人「定期自動投稿まで考えたい」「Actions で自動にする」。
  台本づくりと監査（produce.py、ヒロ）は手元、声・動画・投稿は GitHub Actions で PC なしに回す「在庫」方式。
  棚の台本は監査で「可」になったものだけ（produce.py が入れる）。

使い方:
  python scripts/publish_queue.py [--within-hours 30] [--dry-run]
    publish_at が「今から within-hours 時間以内」の台本を処理する。済んだものは published/ に移し、
    mock/published.md（台帳）に1行足す。説明欄は台本の "upload"（題・要約・出典・タグ）と章の時刻から作る。
"""
import argparse
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

THUMB = True  # 長編のサムネ（scripts/make_thumb.py）。10/8 本人 OK（用語の回は A ノート、午後の回は C 斜め分割）
CREDIT = "※この動画はIPA（情報処理推進機構）とは関係ありません。\n\n音声：VOICEVOX:ずんだもん／VOICEVOX:四国めたん\n立ち絵：坂本アヒル様"


def fmt(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def retry_thumbs():
    """10/8：サムネの上げすぎ（429）で付けられなかった分を、data/thumb_retry.json から付け直す。"""
    p = ROOT / "data" / "thumb_retry.json"
    if not p.exists():
        return
    import make_thumb
    left = []
    for it in json.loads(p.read_text(encoding="utf-8")):
        try:
            d = json.loads((ROOT / it["src"]).read_text(encoding="utf-8"))
            d.setdefault("upload", {"title": d.get("title", "")})
            if it.get("thumb"):
                d["thumb"] = it["thumb"]
            out = ROOT / "build" / f"thumb_{it['video_id']}.jpg"
            out.parent.mkdir(exist_ok=True)
            make_thumb.render(d, str(out))
            make_thumb.set_thumbnail(it["video_id"], out)
            print(f"[info] サムネを付け直した: {it['video_id']}")
        except Exception as e:
            print(f"[warn] サムネの付け直しはまた次に: {it['video_id']}（{str(e)[:60]}）")
            left.append(it)
    p.write_text(json.dumps(left, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8")


def pick_title(d, timeline):
    """10/8 本人「題は伸びる方で」→ 日付が偶数の日は B 型、奇数の日は C 型で比べる（title_b・title_c が無ければ title）。"""
    up = d["upload"]
    day = int(d["publish_at"][8:10])
    key = "title_b" if day % 2 == 0 else "title_c"
    t = up.get(key) or up["title"]
    sec = timeline["duration"]
    t = t.replace("{min}", str(max(1, round(sec / 60)))).replace("{sec}", str(int(round(sec / 5) * 5)))
    d["title_variant"] = key if up.get(key) else "title"
    d["title_used"] = t
    return t[:100]


def description(d, timeline):
    up = d["upload"]
    parts = [up["summary"]]
    if d.get("format", "long") == "long":
        ch = [(0, "はじめに")] + [(ln["start"], ln["chapter"]) for ln in timeline["lines"] if ln.get("chapter")]
        if len(ch) >= 3:
            parts.append("\n".join(f"{fmt(t)} {n}" for t, n in ch))
    parts.append("\n".join(up.get("sources", [])))
    parts.append(CREDIT)
    tags = list(up.get("tags", []))
    if d.get("format") == "short" and "Shorts" not in tags:
        tags.append("Shorts")
    parts.append(" ".join("#" + t for t in tags))
    return "\n\n".join(p for p in parts if p), tags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--within-hours", type=float, default=30)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc)
    limit = now + datetime.timedelta(hours=a.within_hours)
    q = ROOT / "queue"
    done = ROOT / "published"
    done.mkdir(exist_ok=True)
    items = sorted(q.glob("*.json")) if q.exists() else []
    todo = []
    for f in items:
        d = json.loads(f.read_text(encoding="utf-8"))
        at = datetime.datetime.fromisoformat(d["publish_at"])
        if at <= now + datetime.timedelta(minutes=20):
            at = now + datetime.timedelta(minutes=30)  # 過ぎた時刻は受け付けないので、30分後に回す
            d["publish_at"] = at.isoformat(timespec="seconds")
        if at <= limit:
            todo.append((f, d))
    print(f"[info] 棚 {len(items)}本・今回 {len(todo)}本")
    import os
    if todo and not a.dry_run and not (ROOT / ".secrets" / "youtube_token.json").exists()             and not os.environ.get("YOUTUBE_REFRESH_TOKEN"):
        print("[info] 投稿の許可（Secrets）がまだ無いので、何もせず終わる（scripts/set_secrets.py を本人が実行）")
        return 0
    if a.dry_run:
        for f, d in todo:
            print(" ", f.name, d["publish_at"], d["upload"]["title"])
        return 0
    import mock_build
    import render_video
    import upload_youtube
    retry_thumbs()
    ledger = ROOT / "mock" / "published.md"
    for f, d in todo:
        out = ROOT / "build" / "queue"
        out.mkdir(parents=True, exist_ok=True)
        src = out / f"{d['id']}.src.json"
        src.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        mock_build.main(str(src), str(out))
        render_video.main(d["id"], str(out))
        timeline = json.loads((out / f"{d['id']}.json").read_text(encoding="utf-8"))
        desc, tags = description(d, timeline)
        title = pick_title(d, timeline)
        try:
            vid = upload_youtube.upload(out / f"{d['id']}.mp4", title, desc, tags,
                                        publish_at=d["publish_at"])
        except Exception as e:  # 10/8：1日に上げられる本数の上限（uploadLimitExceeded）に当たった
            if "uploadLimitExceeded" in str(e):
                print("[stop] YouTube の1日のアップロード上限に当たったので、今日はここまで（残りは棚のまま次の回に）")
                return 0
            raise
        d["video_id"] = vid
        if THUMB and d.get("format", "long") == "long":
            try:
                import make_thumb
                jpg = make_thumb.render(d, out / f"{d['id']}.jpg")
                make_thumb.set_thumbnail(vid, jpg)
                print("[info] サムネを設定した")
            except Exception as e:
                print(f"[warn] サムネを設定できなかった: {e}")
        try:  # 10/8：台本から字幕を上げる（失敗しても投稿は止めない）
            import captions
            captions.upload(vid, timeline)
        except Exception as e:
            print(f"[warn] 字幕を上げられなかった: {e}")
        try:  # 10/8：分野ごとの再生リストに入れる（失敗しても投稿は止めない）
            import playlists
            playlists.add(vid, d.get("topic"))
        except Exception as e:
            print(f"[warn] 再生リストに入れられなかった: {e}")
        if d.get("replace_video_id"):  # 10/8：作り直した版を上げたら、古い版の予約を外して非公開に（消さない）
            from googleapiclient.discovery import build as gbuild
            yt = gbuild("youtube", "v3", credentials=upload_youtube.credentials())
            yt.videos().update(part="status", body={"id": d["replace_video_id"], "status": {
                "privacyStatus": "private", "selfDeclaredMadeForKids": False}}).execute()
            print(f"[info] 古い版 {d['replace_video_id']} の予約を外して非公開にした")
        (done / f.name).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        f.unlink()
        kind = "ショート" if d.get("format") == "short" else "長編"
        with ledger.open("a", encoding="utf-8") as w:
            w.write(f"| {d['publish_at'][:10]} | {kind} | {d['upload']['title']} | https://youtu.be/{vid} | published/{f.name} | "
                    f"{(d.get('audit') or [{}])[-1].get('verdict', '')}（予約 {d['publish_at']}） |\n")
        print(f"[info] 予約しました: https://youtu.be/{vid}（{d['publish_at']} に公開）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
