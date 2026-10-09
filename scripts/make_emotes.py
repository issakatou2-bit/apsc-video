#!/usr/bin/env python3
"""assets/emotes/*.svg（汗・電球・きらきら）を、背景の透けた PNG にする。動画ではこの PNG を重ねる。

なぜ要るのか:
  2026-10-09 本人「汗・電球・きらきら これもっと自然でデザインよくして」。Pillow で形を描くと固く見えるので、
  ぼかし・グラデーションの効く SVG で描いてブラウザで PNG にした（PNG はリポジトリに入れるので、Actions では作らない）。

使い方:
  python scripts/make_emotes.py
"""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "assets" / "emotes"


def main():
    from playwright.sync_api import sync_playwright
    ch = os.environ.get("APSC_BROWSER", "msedge")
    with sync_playwright() as p:
        b = p.chromium.launch(channel=ch) if ch != "chromium" else p.chromium.launch()
        pg = b.new_page()
        for svg in sorted(D.glob("*.svg")):
            pg.set_content(f'<html><body style="margin:0;background:transparent">{svg.read_text(encoding="utf-8")}</body></html>')
            pg.locator("svg").screenshot(path=str(svg.with_suffix(".png")), omit_background=True)
            print("[info]", svg.with_suffix(".png").name)
        b.close()


if __name__ == "__main__":
    main()
