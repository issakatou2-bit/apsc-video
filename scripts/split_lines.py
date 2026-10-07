#!/usr/bin/env python3
"""台本の長い台詞（字幕が3行を超えるもの）を、文の切れ目で2つに分ける。

なぜ要るのか:
  2026-10-08、長編 第1回で 70字の台詞が字幕4行になり、画面の札にかぶった。
  字幕は1行およそ24字なので、60字を超える台詞を「。！？」の切れ目で分ける。

使い方: python scripts/split_lines.py episodes/xxx.json
"""
import json
import re
import sys

LIMIT = 60


def sents(t):
    return [s for s in re.split(r"(?<=[。！？])", t) if s]


def main(path):
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for ln in d["lines"]:
        t = ln.get("text", "")
        if len(t) <= LIMIT:
            out.append(ln)
            continue
        ts = sents(t)
        ss = sents(ln["say"]) if ln.get("say") else None
        if len(ts) < 2 or (ss and len(ss) != len(ts)):
            print(f"[warn] 分けられない（{len(t)}字）: {t}")
            out.append(ln)
            continue
        k = min(range(1, len(ts)), key=lambda i: abs(len("".join(ts[:i])) - len(t) / 2))
        a = {**ln, "text": "".join(ts[:k])}
        b = {key: v for key, v in ln.items() if key not in ("sfx", "chapter")}
        b["text"] = "".join(ts[k:])
        if ss:
            a["say"], b["say"] = "".join(ss[:k]), "".join(ss[k:])
        out += [a, b]
        print(f"[info] 分けた {len(t)} → {len(a['text'])}+{len(b['text'])}")
    d["lines"] = out
    open(path, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
