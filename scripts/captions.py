#!/usr/bin/env python3
"""台本の時刻表（mock_build.py が書く <id>.json）から字幕（SRT）を作り、YouTube に上げる。

なぜ要るのか:
  2026-10-08。字幕は台本そのものなので、自動の字幕より正確。音を出せない人・検索にも効く。
  字幕の文は画面の字幕と同じ（読み上げ用の say ではなく text）。

使い方:
  python scripts/captions.py 動画ID 時刻表.json     # 1本
  （publish_queue.py からは upload(video_id, timeline) を呼ぶ）
"""
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(timeline):
    out, n = [], 0
    for ln in timeline["lines"]:
        if not ln.get("who") or not ln.get("text"):
            continue
        n += 1
        out.append(f"{n}\n{ts(ln['start'])} --> {ts(ln['end'])}\n{ln['text']}\n")
    return "\n".join(out)


def upload(video_id, timeline, yt=None):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    import upload_youtube
    yt = yt or build("youtube", "v3", credentials=upload_youtube.credentials())
    body = {"snippet": {"videoId": video_id, "language": "ja", "name": "日本語（台本）", "isDraft": False}}
    media = MediaIoBaseUpload(io.BytesIO(srt(timeline).encode("utf-8")), mimetype="application/octet-stream")
    r = yt.captions().insert(part="snippet", body=body, media_body=media).execute()
    print(f"[info] 字幕を上げた: {video_id}（{r['id']}）")
    return r["id"]


if __name__ == "__main__":
    upload(sys.argv[1], json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")))
