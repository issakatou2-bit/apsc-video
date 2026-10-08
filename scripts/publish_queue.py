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

CREDIT = "※この動画はIPA（情報処理推進機構）とは関係ありません。\n\n音声：VOICEVOX:ずんだもん／VOICEVOX:四国めたん\n立ち絵：坂本アヒル様"


def fmt(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


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
    if a.dry_run:
        for f, d in todo:
            print(" ", f.name, d["publish_at"], d["upload"]["title"])
        return 0
    import mock_build
    import render_video
    import upload_youtube
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
        vid = upload_youtube.upload(out / f"{d['id']}.mp4", d["upload"]["title"], desc, tags,
                                    publish_at=d["publish_at"])
        d["video_id"] = vid
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
