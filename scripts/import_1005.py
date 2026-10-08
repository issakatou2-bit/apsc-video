#!/usr/bin/env python3
"""1005（クラウドの作業一覧）の下書きを episodes/batch*/ に取り込み、形を機械で確かめる。

なぜ要るのか:
  2026-10-08 本人「とにかく増やす。質を保証した上で」。1005 の成果（apsc-video/out/<番号>/*.json）を
  手で写すと漏れや取り違えが出るので、取り込みと形の検査を1本にした。中身の正しさはこの後の produce.py（ヒロの監査）。

確かめること:
  場面の型が7つのどれか・台詞の scene が場面にあるか・who・upload の title/title_b/title_c/sources、
  ショートの長さの目安（台詞の数）、id の重なり。声と BGM は長編・ショートの決まりの値にそろえる。

使い方:
  python scripts/import_1005.py build/r1005 origin/claude/results-1007 103 104 ... --to episodes/batch3
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TYPES = {"title", "list", "levels", "grid", "forces", "cards", "quiz"}
VOICE = {
    "long": ({"zundamon": {"speaker": 3, "speed": 1.43, "pitch": 0.0, "intonation": 1.35},
              "metan": {"speaker": 2, "speed": 1.3, "pitch": 0.0, "intonation": 1.55}}, "assets/bgm/nighter.mp3"),
    "short": ({"zundamon": {"speaker": 3, "speed": 1.54, "pitch": 0.0, "intonation": 1.45},
               "metan": {"speaker": 2, "speed": 1.35, "pitch": 0.0, "intonation": 1.55}}, "assets/bgm/everyday.mp3"),
}


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, check=True).stdout.decode("utf-8")


def check(d):
    errs = []
    fmt = d.get("format")
    if fmt not in ("long", "short"):
        errs.append(f"format が {fmt}")
    scenes = d.get("scenes") or {}
    for k, s in scenes.items():
        if s.get("type") not in TYPES:
            errs.append(f"場面 {k} の型 {s.get('type')}")
        if fmt == "short" and s.get("type") == "forces":
            errs.append(f"ショートに forces（{k}）")
    for i, ln in enumerate(d.get("lines") or []):
        if ln.get("scene") not in scenes:
            errs.append(f"台詞 {i} の場面 {ln.get('scene')} が無い")
        if not ln.get("pause") and ln.get("who") not in ("zundamon", "metan"):
            errs.append(f"台詞 {i} の who {ln.get('who')}")
    up = d.get("upload") or {}
    for k in ("title", "title_b", "title_c", "sources"):
        if not up.get(k):
            errs.append(f"upload.{k} が無い")
    n = len(d.get("lines") or [])
    if fmt == "short" and not 5 <= n <= 14:
        errs.append(f"ショートの台詞が {n}")
    if fmt == "long" and n < 60:
        errs.append(f"長編の台詞が {n}（短い）")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("ref")
    ap.add_argument("nums", nargs="+")
    ap.add_argument("--to", default="episodes/batch3")
    a = ap.parse_args()
    out = ROOT / a.to
    out.mkdir(parents=True, exist_ok=True)
    known = {p.stem for p in ROOT.glob("episodes/**/*.json")}
    ok = bad = 0
    for n in a.nums:
        names = [x for x in git(a.repo, "ls-tree", "--name-only", f"{a.ref}:apsc-video/out/{n}").split("\n")
                 if x.endswith(".json")]
        for name in names:
            d = json.loads(git(a.repo, "show", f"{a.ref}:apsc-video/out/{n}/{name}"))
            d["id"] = f"b{n}_{pathlib.Path(name).stem}"
            if d["id"] in known:
                print(f"[skip] {d['id']} はもうある")
                continue
            d["voice"], d["bgm"] = VOICE.get(d.get("format"), VOICE["long"])
            errs = check(d)
            if errs:
                bad += 1
                print(f"[ng] {d['id']}: " + "／".join(errs[:6]))
                d["import_errors"] = errs
            else:
                ok += 1
            (out / f"{d['id']}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[info] 取り込み：形に問題なし {ok}本・要確認 {bad}本 -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
