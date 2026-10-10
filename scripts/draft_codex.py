#!/usr/bin/env python3
"""1005 の作業一覧の「台本の下書き」の行を、Codex に書かせる（成果は build/codex_drafts/<番号>/）。

なぜ要るのか:
  2026-10-10 夜 1005 の自動の作業者が一時停止（再開は本人が決める、火曜ごろの見込み）。
  2026-10-11 本人「Codex リセットしたのでガッツリ使ってください」→ 長編が 11/3 から足りないので、
  1005 に頼んだ行（240〜268）と同じ指示書のまま、Codex に下書きさせる。
  過去問は build/ipa/（IPA の PDF をページの絵にしたもの、scripts/ipa_pages.py）で確かめさせる。

使い方:
  python scripts/draft_codex.py 240 241 ... [--jobs 3] [--effort high]
  → build/codex_drafts/<番号>/*.json・notes.md
  → python scripts/import_1005.py build/codex_drafts - 240 241 ... --to episodes/batch7
  → produce.py で監査（下書きとは別の新しい会話）
"""
import argparse
import concurrent.futures
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from produce import CODEX  # noqa: E402

R1005 = ROOT / "build" / "r1005"
OUT = ROOT / "build" / "codex_drafts"


def rows(nums):
    t = (R1005 / "作業一覧.md").read_text(encoding="utf-8") + (R1005 / "完了一覧.md").read_text(encoding="utf-8")
    got = {}
    for ln in t.splitlines():
        m = re.match(r"\| (\d+) \| apsc-video \| (.*?) \| ", ln)
        if m and m.group(1) in nums:
            got[m.group(1)] = m.group(2)
    return got


def existing_titles():
    seen = []
    for f in sorted(ROOT.glob("episodes/**/*.json")) + sorted(ROOT.glob("queue/*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        t = (d.get("upload") or {}).get("title") or d.get("title")
        if t and t not in seen:
            seen.append(t)
    return seen


def prompt(n, task):
    brief = re.search(r"\[(apsc-video/指示書/[^\]]+)\]", task)
    return f"""あなたは YouTube チャンネル「めたん先生のIT試験ゼミ」（ずんだもんと四国めたんの対話で応用情報技術者試験を解説）の台本の下書き担当です。返事と台本はすべて日本語。

## 今回の作業（作業一覧の {n} 番）
{task}

## 先に読むもの（このリポジトリの中）
- build/r1005/.claude/skills/apsc-script/SKILL.md（台本の決まり。いちばん大事）
- build/r1005/apsc-video/README.md と episodes/README.md（決まりと監査で見られる点）
- 指示書：build/r1005/{brief.group(1) if brief else "apsc-video/指示書/Opus-06.md"}
- 形の手本：build/r1005/apsc-video/src/episodes/strategy3.json（長編の JSON の形）、queue/ の中の長編（例 queue/*_b229_long.json）も手本にしてよい
- 回の候補表：build/r1005/apsc-video/src/tables/candidates.md、午前の一覧 build/r1005/apsc-video/src/tables/ap_am_list.csv、午後の一覧 build/r1005/apsc-video/src/tables/ap_pm_list.csv
- すでにある回の題：build/codex_drafts/existing_titles.txt（重ねない）

## 材料（ネットは使えません。IPA の公表した過去問はここにあります）
- build/ipa/png/<年度>_ap_<am|pm>_<qs|ans|cmnt>/p001.png …（問題冊子・解答・採点講評のページの絵。画像を開いて読む道具で見る）
  年度は 2022r04h（令和4年度春期）・2022r04a（令和4年度秋期）… 2025r07h（令和7年度春期）・2025r07a（令和7年度秋期）の8回分だけ。
- build/ipa/txt/<同じ名前>.txt（文字が取り出せた分だけ。解答・講評は文字で読めることが多い）
- 過去問の問題文・選択肢・正答は、必ずページの絵で確かめてから台本に書く。この8回分にない過去問は使わない。令和8年度の問題には触れない。

## 書き出すもの
- build/codex_drafts/{n}/ に、指示書が言うファイル（用語の回は long.json、午後の解き方は pm<問番号>_<年度記号>.json）と notes.md。
- JSON は UTF-8、手本と同じ形（id・format・title・topic・materials・upload・scenes・lines）。書いたら python で読み込めるか確かめる（py -c "import json;json.load(open(...,encoding='utf-8'))"）。
- ショートは作らない。ほかのファイルは書き換えない。git の操作はしない。
- 終わったら、作ったファイルの名前と、台詞の数、使った過去問（年度・問番号・正答）を短く返す。
"""


def run(n, task, effort):
    d = OUT / n
    d.mkdir(parents=True, exist_ok=True)
    log = OUT / f"run_{n}.jsonl"
    args = [str(CODEX), "exec", "-C", str(ROOT), "-s", "workspace-write", "--skip-git-repo-check",
            "-m", "gpt-6.1-sol", "-c", f'model_reasoning_effort="{effort}"', "--json",
            "-o", str(OUT / f"last_{n}.txt"), "-"]
    with open(log, "w", encoding="utf-8") as lf:
        r = subprocess.run(args, input=prompt(n, task).encode("utf-8"), stdout=lf, stderr=subprocess.STDOUT)
    files = sorted(p.name for p in d.glob("*.json"))
    ok = []
    for name in files:
        try:
            json.loads((d / name).read_text(encoding="utf-8"))
            ok.append(name)
        except ValueError as e:
            print(f"[ng] {n}/{name}: JSON が読めない {e}", flush=True)
    print(f"[info] {n}: exit {r.returncode}・できた {ok}", flush=True)
    return n, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nums", nargs="+")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--effort", default="high")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "existing_titles.txt").write_text("\n".join(existing_titles()) + "\n", encoding="utf-8")
    tasks = rows(set(a.nums))
    todo = [n for n in a.nums if n in tasks and not list((OUT / n).glob("*.json"))]
    print(f"[info] 下書き {len(todo)}本（並べて {a.jobs}）", flush=True)
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda n: run(n, tasks[n], a.effort), todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
