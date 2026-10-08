#!/usr/bin/env python3
"""動画を YouTube に上げる（YouTube Data API）。

なぜ要るのか:
  2026-10-08 本人「API だな」。長編はブラウザ経由の道具の上限（10MB）を超えるため。
  コレスポの scripts/upload_youtube.py は MLB 向けの処理が多いので、要るところだけ新しく書いた。

使い方:
  python scripts/upload_youtube.py 動画.mp4 --meta mock/upload_meta.md --key ③ [--privacy public|unlisted|private] [--channel UC...]
    --meta の md から「## <key> …」の節を探し、「題: 」の行を題、その下の本文を説明欄にする（mock/upload_meta.md の形）。
  投稿の前に、許可したチャンネルが --channel と同じかを確かめ、違えば止める（コレスポに上げてしまわないため）。

設定（Studio で手で選んでいたもの）:
  子ども向けではない（selfDeclaredMadeForKids=False）、AI の使用「いいえ」（containsSyntheticMedia=False）、
  カテゴリ 27（教育）、言語 ja。
"""
import argparse
import json
import pathlib
import re
import sys

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKEN = ROOT / ".secrets" / "youtube_token.json"
CHANNEL = "UCFPlgxr-u00RDIXYtQfKA2g"  # めたん先生のIT試験ゼミ


def read_meta(path, key):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.search(r"^## " + re.escape(key) + r".*?$\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
    if not m:
        raise SystemExit(f"[error] {path} に「## {key}」の節がありません")
    body = m.group(1).strip("\n")
    t = re.search(r"^題: (.+)$", body, flags=re.M)
    if not t:
        raise SystemExit("[error] 「題: 」の行がありません")
    desc = body[t.end():].strip("\n")
    return t.group(1).strip(), desc


def credentials():
    """手元では .secrets/youtube_token.json、GitHub Actions では Secrets（環境変数）から許可を作る。"""
    import os
    if TOKEN.exists():
        return Credentials.from_authorized_user_info(json.loads(TOKEN.read_text(encoding="utf-8")))
    info = {"client_id": os.environ["YOUTUBE_CLIENT_ID"], "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
            "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "token_uri": "https://oauth2.googleapis.com/token"}
    return Credentials.from_authorized_user_info(info)


def upload(video, title, desc, tags, privacy="public", publish_at=None, channel=CHANNEL):
    """1本上げて動画の ID を返す。publish_at（ISO）があれば非公開で上げて、その時刻に自動で公開される。"""
    yt = build("youtube", "v3", credentials=credentials())
    mine = [c["id"] for c in yt.channels().list(part="id", mine=True).execute().get("items", [])]
    if channel not in mine:
        raise SystemExit(f"[error] 許可しているチャンネル {mine} が {channel} と違うので止めました")
    status = {"privacyStatus": "private" if publish_at else privacy, "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": False}
    if publish_at:
        status["publishAt"] = publish_at
    body = {"snippet": {"title": title, "description": desc, "tags": [t for t in tags if t != "Shorts"],
                        "categoryId": "27", "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
            "status": status}
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--meta", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    title, desc = read_meta(a.meta, a.key)
    tags = re.findall(r"#(\S+)", desc)
    print(f"[info] 題: {title}\n[info] 説明欄 {len(desc)}字・タグ {tags}")
    if len(title) > 100:
        raise SystemExit("[error] 題が100字を超えています")
    if a.dry_run:
        print(desc)
        return 0
    vid = upload(a.video, title, desc, tags, a.privacy, None, a.channel)
    print(f"[info] 上げました: https://youtu.be/{vid}（{a.privacy}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
