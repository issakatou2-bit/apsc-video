#!/usr/bin/env python3
"""IPA の過去問 PDF（build/ipa/pdf）を1ページずつ PNG に（build/ipa/png/<名前>/p001.png）。

なぜ要るのか:
  2026-10-11 本人「Codex ガッツリ使って」→ Codex に長編を下書きさせる。問題冊子の PDF は文字が取り出せない
  （字の形だけの PDF）ので、Codex がページの絵を見て問題文と正答を確かめられるようにする。
"""
import pathlib
import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
src, dst = ROOT / "build" / "ipa" / "pdf", ROOT / "build" / "ipa" / "png"
for f in sorted(src.glob("*.pdf")):
    out = dst / f.stem
    if out.exists():
        continue
    out.mkdir(parents=True)
    doc = pymupdf.open(f)
    for i, page in enumerate(doc, 1):
        page.get_pixmap(dpi=110).save(out / f"p{i:03d}.png")
    print(f.stem, len(doc))
