#!/usr/bin/env python3
"""分野ごとの再生リストを作り、動画を入れる。

なぜ要るのか:
  2026-10-08 本人「再生リストとかもまとめてあるかな？」。試験の勉強の動画は、分野ごとにまとめて見られるので、
  台本の topic（例：「応用情報｜経営戦略」「応用情報 午後｜経営戦略」）から入れる再生リストを決める。
  再生リストの番号は data/playlists.json に覚えておく（公開してよい情報）。

使い方:
  python scripts/playlists.py            # published/ の全部を、まだ入っていなければ入れる
  （publish_queue.py からは add(video_id, topic) を呼ぶ）
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
STORE = ROOT / "data" / "playlists.json"
DESC = "めたん先生のIT試験ゼミ：応用情報技術者試験・情報処理安全確保支援士試験の{}を、ずんだもんと四国めたんの対話で。ショートと解説をまとめています。"


SHORTS = "応用情報｜ショート"


def lists_for(topic, fmt=None):
    """topic から入れる再生リストの名前（1つ以上）。
    10/10 本人「一旦ショートと長編で2つで良くない？」→ ショートは「応用情報｜ショート」1つ、長編は分野ごと（終わりの札で案内しているため）。"""
    if fmt == "short":
        return [SHORTS]
    head, _, field = (topic or "").partition("｜")
    if head == "試験の制度":
        return ["応用情報｜試験の制度"]
    names = []
    if field:
        names.append(f"応用情報｜{field}")
    if "午後" in head:
        names.append("応用情報｜午後問題の解き方")
    return names or ["応用情報｜そのほか"]


def _yt():
    from googleapiclient.discovery import build
    import upload_youtube
    return build("youtube", "v3", credentials=upload_youtube.credentials())


def _store():
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"lists": {}, "added": {}}


def ensure(yt, st, name):
    if name not in st["lists"]:
        field = name.split("｜", 1)[1]
        desc = ("めたん先生のIT試験ゼミ：応用情報技術者試験・情報処理安全確保支援士試験の用語を、1分未満のショートで。"
                if name == SHORTS else DESC.format(field))
        r = yt.playlists().insert(part="snippet,status", body={
            "snippet": {"title": name, "description": desc, "defaultLanguage": "ja"},
            "status": {"privacyStatus": "public"}}).execute()
        st["lists"][name] = r["id"]
        STORE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8")  # 10/10 作ったらすぐ記録（重複を防ぐ）
        print(f"[info] 再生リストを作った: {name}（{r['id']}）")
    return st["lists"][name]


def add(video_id, topic, yt=None, fmt=None):
    yt = yt or _yt()
    st = _store()
    for name in lists_for(topic, fmt):
        pid = ensure(yt, st, name)
        key = f"{pid}:{video_id}"
        if key in st["added"]:
            continue
        import time
        for t in range(4):  # 10/10 作ったばかりの再生リストには、すぐ入れると 409（aborted）になる → 少し待ってやり直す
            try:
                yt.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
                break
            except Exception as e:
                if t == 3 or "409" not in str(e):
                    raise
                time.sleep(5 * (t + 1))
        st["added"][key] = True
        print(f"[info] {name} に入れた: {video_id}")
    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _items():
    """公開・予約した動画の (公開日時, 動画ID, topic, 形)"""
    items = []
    for f in sorted((ROOT / "published").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("video_id"):
            items.append((d["publish_at"], d["video_id"], d.get("topic"), d.get("format", "long")))
    for x in json.loads((ROOT / "data" / "early_videos.json").read_text(encoding="utf-8")):
        items.append((x["published"], x["video_id"], x["topic"], x.get("format", "long")))
    return sorted(items)


def migrate(yt):
    """10/10 分野別・午前の過去問の再生リストに入っているショートを外す（動画は消さない。入れ先を付け替えるだけ）。"""
    st = _store()
    shorts = {v for _, v, _, f in _items() if f == "short"}
    for name, pid in st["lists"].items():
        if name == SHORTS:
            continue
        tok = None
        while True:
            r = yt.playlistItems().list(part="snippet", playlistId=pid, maxResults=50, pageToken=tok).execute()
            for it in r["items"]:
                vid = it["snippet"]["resourceId"]["videoId"]
                if vid in shorts:
                    yt.playlistItems().delete(id=it["id"]).execute()
                    st["added"].pop(f"{pid}:{vid}", None)
                    print(f"[info] {name} から外した: {vid}")
            tok = r.get("nextPageToken")
            if not tok:
                break
    STORE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8")


def main(args=()):
    yt = _yt()
    if "--migrate" in args:
        migrate(yt)
    for _, vid, topic, fmt in _items():
        add(vid, topic, yt, fmt)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
