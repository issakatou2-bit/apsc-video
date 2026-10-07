#!/usr/bin/env python3
"""YouTube に投稿するための許可（リフレッシュトークン）を取る。最初の1回だけ。

なぜ要るのか:
  2026-10-08 本人「API だな」。長編は 15MB を超え、ブラウザ経由の道具（1回10MBまで）で上げられない。
  コレスポの鍵は GitHub Secrets にしか無いので、このプロジェクト用に手元で許可を取る。

使い方:
  1. 本人が Google Cloud のコンソールで OAuth クライアント（種類：デスクトップ アプリ）の JSON をダウンロードし、
     .secrets/client_secret.json に置く（.secrets/ は git の対象外）。
  2. python scripts/youtube_auth.py
     → ブラウザが開く。本人がログインし、「めたん先生のIT試験ゼミ」を選んで許可する。
  3. .secrets/youtube_token.json ができる（中身は表示しない）。どのチャンネルの許可かを確かめて表示する。
"""
import json
import pathlib
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".secrets"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def main():
    client = SECRETS / "client_secret.json"
    if not client.exists():
        print(f"[error] {client} がありません。Google Cloud のコンソールから OAuth クライアントの JSON を置いてください。")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    token = SECRETS / "youtube_token.json"
    token.write_text(creds.to_json(), encoding="utf-8")
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    for c in ch:
        print(f"[info] 許可したチャンネル: {c['snippet']['title']}（{c['id']}）")
    print(f"[info] 許可を保存しました: {token}（中身は秘密。コミットしない）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
