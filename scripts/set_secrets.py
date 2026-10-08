#!/usr/bin/env python3
"""手元の .secrets/ にある YouTube の許可を、GitHub の Secrets（apsc-video）に入れる。**本人が実行する。**

なぜ要るのか:
  2026-10-08 本人「Actions で自動にする」。GitHub Actions が投稿するには、許可（クライアント ID・シークレット・
  リフレッシュトークン）が Secrets に要る。値を画面やチャットに出さずに、gh CLI に直接渡す。
  （鍵を入れる操作はエマがしない決まりなので、本人が自分のターミナルで動かす）

使い方（本人）:
  py scripts/set_secrets.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "issakatou2-bit/apsc-video"


def put(name, value):
    r = subprocess.run(["gh", "secret", "set", name, "--repo", REPO], input=value, text=True,
                       capture_output=True)
    print(f"{name}: {'設定しました' if r.returncode == 0 else '失敗 ' + r.stderr.strip()}")
    return r.returncode == 0


def main():
    tok = json.loads((ROOT / ".secrets" / "youtube_token.json").read_text(encoding="utf-8"))
    ok = all([put("YOUTUBE_CLIENT_ID", tok["client_id"]),
              put("YOUTUBE_CLIENT_SECRET", tok["client_secret"]),
              put("YOUTUBE_REFRESH_TOKEN", tok["refresh_token"])])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
