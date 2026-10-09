#!/usr/bin/env python3
"""棚（queue/）の台本を直したとき、Codex の確認をもう一度通してから棚に戻す。

なぜ要るのか:
  2026-10-09 本人「ショートでこんな長文読む人いない。かいつまんだ問題の要約も先に言うべき」→ 棚の午前の1問に要約の台詞を足した。
  中身が変わったので、そのまま出さずに Codex の確認（produce.py、最大2回）を通し、「可」になった分だけ同じ公開時刻のまま棚に戻す。

使い方:
  python scripts/recheck_queue.py episodes/fix/*.json   # 各ファイルに "_queue_file"（元の棚のファイル）を入れておく
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main(paths):
    bad = []
    for p in paths:
        p = pathlib.Path(p)
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "produce.py"), str(p), "--max-rounds", "2"],
                           capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])
        d = json.loads(p.read_text(encoding="utf-8"))
        last = (d.get("audit") or [{}])[-1]
        q = d.pop("_queue_file", None)
        if r.returncode == 0 and last.get("verdict") == "可" and q:
            (ROOT / q).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[info] 棚に戻した: {q}")
        else:
            bad.append(p.name)
    if bad:
        print("[stop] 戻せなかった（元の棚のまま）: " + ", ".join(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
