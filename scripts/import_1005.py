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
  python scripts/import_1005.py build/r1005 <ブランチ> 143 144 ... --audited --to episodes/batch3
  python scripts/import_1005.py build/codex_drafts - 240 241 ... --to episodes/batch7
    （10/11 ref を - にすると、git ではなくフォルダ <repo>/<番号>/*.json から読む。Codex の下書き（scripts/draft_codex.py）用）
    （10/9 1005 での1回目の監査と直し（指示書 Opus-13）の成果を、同じ id の台本に上書きで戻す。
     <id>.audit.md の中身を台本の audit に足す。このあと produce.py で Codex の最後の確認）
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
TYPES = {"title", "list", "levels", "grid", "forces", "cards", "quiz"}
VOICE = {
    "long": ({"zundamon": {"speaker": 3, "speed": 1.43, "pitch": 0.0, "intonation": 1.35},
              "metan": {"speaker": 2, "speed": 1.3, "pitch": 0.0, "intonation": 1.55}}, "assets/bgm/nighter.mp3"),
    "short": ({"zundamon": {"speaker": 3, "speed": 1.54, "pitch": 0.0, "intonation": 1.45},
               "metan": {"speaker": 2, "speed": 1.35, "pitch": 0.0, "intonation": 1.55}}, "assets/bgm/everyday.mp3"),
}


def ls_out(repo, ref, n):
    if ref == "-":
        return sorted(p.name for p in (pathlib.Path(repo) / str(n)).glob("*.json"))
    return [x for x in git(repo, "ls-tree", "--name-only", f"{ref}:apsc-video/out/{n}").split("\n") if x.endswith(".json")]


def read_out(repo, ref, n, name):
    if ref == "-":
        return (pathlib.Path(repo) / str(n) / name).read_text(encoding="utf-8")
    return git(repo, "show", f"{ref}:apsc-video/out/{n}/{name}")


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
    ap.add_argument("--audited", action="store_true")
    a = ap.parse_args()
    out = ROOT / a.to
    out.mkdir(parents=True, exist_ok=True)
    known = {p.stem for p in ROOT.glob("episodes/**/*.json")}
    ok = bad = 0
    for n in a.nums:
        for name in ls_out(a.repo, a.ref, n):
            d = json.loads(read_out(a.repo, a.ref, n, name))
            if a.audited:
                d["id"] = pathlib.Path(name).stem
                try:
                    note = git(a.repo, "show", f"{a.ref}:apsc-video/out/{n}/{d['id']}.audit.md")
                except subprocess.CalledProcessError:
                    note = ""
                head = note[:300]  # 判断は audit.md の最初のほうに書く決まり
                verdict = "不可" if ("不可" in head and "直せば可" not in head) else "直した"
                d.setdefault("audit", []).append({"by": "1005（Claude、指示書 Opus-13）", "round": "1回目の監査と直し",
                                                  "verdict": verdict, "notes": note[:4000]})
            else:
                d["id"] = f"b{n}_{pathlib.Path(name).stem}"
            if d["id"] in known and not a.audited:
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
    try:  # 10/10 文全体カタカナの say を、漢字で読ませる形に（音素が同じものだけ）
        import fix_says
        fix_says.main([str(out.relative_to(ROOT))])
    except Exception as e:
        print(f"[warn] say の見直しができなかった（音声ソフトが止まっている？）: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
