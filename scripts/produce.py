#!/usr/bin/env python3
"""台本を「監査 → 直し → 再監査」で「可」まで持っていき、投稿の棚（queue/）に入れる。

なぜ要るのか:
  2026-10-08 本人「監査はいいけど、指摘箇所を直して投稿までスムーズにこぎつける仕組みにしたい。
  情報に間違いがないことを確認した上で。前提情報が冗長な時があるのでそこも」。
  これまでエマが手で「ヒロの表を読む → 直す → もう一度送る」をしていたのを1本にした。

流れ:
  1. 長い台詞を分ける（split_lines）
  2. ヒロ（Codex CLI、GPT）に、決まり（episodes/README.md）・材料・画面・台本を渡して監査を頼む。
     返事は JSON：判断（可／直せば可／不可）と、直した後の文（fixes）。
  3. fixes を台本に当てる（台詞の差し替え・削除・追加、画面の文字の差し替えだけ。場面の組み立ては変えない）。
  4. 「可」になるまで最大3回。「可」なら queue/ に写す（--publish-at を付けて）。ならなければ止めて報告。
  監査の記録は台本の "audit" に足す（どの回で何を直したか）。

使い方:
  python scripts/produce.py episodes/xxx.json --publish-at 2026-10-09T20:00:00+09:00
  python scripts/produce.py episodes/xxx.json --publish-at auto   # 空いているいちばん早い枠に
  （--dry-run で、ヒロに送る文を表示するだけ）
"""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mock_build  # noqa: E402
import split_lines  # noqa: E402

CODEX_DIR = pathlib.Path("C:/Users/issak/Desktop/metan3D/tools/codex")
CODEX = CODEX_DIR / "codex-x86_64-pc-windows-msvc.exe"
WORK = ROOT / "build" / "codex"
USAGE_LIMIT = 95.0  # 10/9 本人「リセットあるから気にしないで使っていいよ」（前は全プロジェクト共通の50%の決まりで45%）
NAME = {"metan": "めたん", "zundamon": "ずんだもん"}
# 10/8 本人「9本/日が上限？影響もデメリットもないなら上限までやろう」→ 1日9枠（ショート6・長編3）。
# 前からある 7:00・19:00・20:00 はそのまま。棚が足りない日は、埋まった枠だけ出す。
SLOTS = {"short": ["07:00", "09:00", "12:00", "15:00", "19:00", "21:00"], "long": ["20:00", "17:30", "22:00"]}


def free_slot(fmt, start=None):
    """queue/・published/ で使われていない、いちばん早い枠（明後日から）。"""
    used = set()
    for f in list((ROOT / "queue").glob("*.json")) + list((ROOT / "published").glob("*.json")):
        used.add(f.name[:13])  # 例 20261011T0700
    day = start or (datetime.date.today() + datetime.timedelta(days=2))
    for _ in range(400):
        for hm in SLOTS["short" if fmt == "short" else "long"]:
            key = day.strftime("%Y%m%d") + "T" + hm.replace(":", "")
            if key not in used:
                return f"{day.isoformat()}T{hm}:00+09:00"
        day += datetime.timedelta(days=1)
    raise SystemExit("[stop] 空き枠が見つからない")


def rules_text():
    t = (ROOT / "episodes" / "README.md").read_text(encoding="utf-8")
    return t.split("## 4.")[0]


def numbered(d):
    out = []
    for i, ln in enumerate(d["lines"], 1):
        if ln.get("who"):
            say = ln.get("say") or mock_build.to_say(ln["text"])
            extra = f"（読み：{say}）" if say != ln["text"] else ""
            k = mock_build.kana(say)  # 10/9 実際に読む音も見せて、読み間違いを見つけてもらう
            if k:
                extra += f"〔音：{k}〕"
            out.append(f"{i}. [{ln['scene']}/{ln['step']}] {NAME[ln['who']]}：{ln['text']}{extra}"
                       + ("【冗談】" if ln.get("joke") else ""))
        else:
            out.append(f"{i}. [{ln['scene']}/{ln['step']}] （考える時間 {ln.get('pause')}秒）")
    return "\n".join(out)


def message(d, rnd, prev):
    head = (f"台本の監査をお願いします（{d['id']}、{rnd}回目）。立場は公開前の監査役。ファイルは読まず、編集もしないでください。"
            if rnd == 1 else
            f"直した台本です（{d['id']}、{rnd}回目）。前回の指摘が直っているか、新しい問題が無いかを見てください。ファイルは読まず、編集もしないでください。")
    mats = "\n".join("- " + m for m in d.get("materials", []))
    return f"""{head}

## 台本の決まり（これに沿っているかも見る）
{rules_text()}

## 材料（台本はこの材料と一般に確立した知識だけで書く決まり）
{mats}

## 画面の文字（場面ごと。キーが場面の名前）
{json.dumps(d.get("scenes", {}), ensure_ascii=False)}

## 台本（番号. [場面/段] 話し手：字幕（読み））
{numbered(d)}

## 見てほしいこと
1. 誤り・材料との食い違い・言い換えで意味が変わった所（最優先）
2. 言い過ぎ・断定しすぎ・材料で確かめられない断定
3. 冗長（決まりの2。出典の読み上げ、前置き、同じことの2回目。消しても正しさと分かりやすさが変わらない台詞）
4. 出典（場面の src）、読み（〔音：〕は合成音声が実際に読むカタカナ。用語・人名・英字の読み間違いがあれば say で直す）、冗談
{prev}
## 返事の形（JSON だけ。``` で囲まない。説明の文を外に書かない）
{{"verdict": "可" または "直せば可" または "不可",
 "fixes": [
  {{"op": "replace", "line": 台詞の番号, "text": "直した後の字幕（60字以内）", "why": "理由を短く"}},
  {{"op": "replace", "line": 台詞の番号, "say": "直した後の読み（カナ）", "why": "…"}}　← 読みだけ直すとき（字幕はそのまま）
  {{"op": "replace", "line": 台詞の番号, "who": "metan か zundamon", "text": "…", "why": "…"}}　← 話す人も変えるとき
  {{"op": "delete", "line": 台詞の番号, "why": "…"}},
  {{"op": "insert_after", "line": 台詞の番号, "who": "metan か zundamon", "text": "…", "why": "…"}},
  {{"op": "scene", "scene": "場面の名前", "path": "items.0.desc のような場所", "value": "直した後の文", "why": "…"}}
 ],
 "notes": "問題の無かった観点を1〜2行"}}
- 「可」なら fixes は空。「直せば可」なら、fixes を当てれば「可」になるように、直した後の文をそのまま書く。
- 材料に無い事実を足して直さない（確かめられない所は削る・弱める）。番号は今回の台本の番号。
"""


def codex_usage():
    try:
        out = subprocess.run(["py", str(CODEX_DIR / "codex_usage.py")], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60).stdout
        m = re.search(r"([\d.]+)%", out)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def ask_hiro(msg, tag):
    WORK.mkdir(parents=True, exist_ok=True)
    thread = (WORK / "thread.txt").read_text().strip()
    mfile, ofile = WORK / f"msg_{tag}.txt", WORK / f"last_{tag}.txt"
    mfile.write_text(msg, encoding="utf-8")
    args = [str(CODEX), "exec", "-C", str(ROOT), "-s", "read-only", "--skip-git-repo-check",
            "-m", "gpt-6.1-sol", "-c", 'model_reasoning_effort="medium"', "--json", "-o", str(ofile),
            "resume", thread, "-"]
    with open(mfile, "rb") as fin, open(WORK / f"run_{tag}.jsonl", "wb") as fout:
        subprocess.run(args, stdin=fin, stdout=fout, stderr=subprocess.DEVNULL, timeout=1200)
    return ofile.read_text(encoding="utf-8")


def parse(reply):
    m = re.search(r"\{.*\}", reply, flags=re.S)
    if not m:
        raise ValueError("JSON が見つからない")
    return json.loads(m.group(0))


def set_path(obj, path, value):
    keys = [int(k) if k.isdigit() else k for k in path.split(".")]
    for k in keys[:-1]:
        obj = obj[k]
    obj[keys[-1]] = value


def apply(d, fixes):
    lines = d["lines"]
    log = []
    for f in sorted([f for f in fixes if f.get("op") != "scene"], key=lambda f: -int(f["line"])):
        i = int(f["line"]) - 1
        if not 0 <= i < len(lines):
            log.append(f"範囲外の番号 {f['line']} を飛ばした")
            continue
        if f["op"] == "replace":
            if f.get("who") in NAME:  # 10/9 話す人の入れ替え（無いと同じ指摘がくり返された）
                lines[i]["who"] = f["who"]
            if f.get("text"):
                lines[i]["text"] = f["text"]
                lines[i].pop("say", None)
            if f.get("say"):
                lines[i]["say"] = f["say"]
        elif f["op"] == "delete":
            lines.pop(i)
        elif f["op"] == "insert_after":
            base = lines[i]
            lines.insert(i + 1, {"scene": base["scene"], "step": base["step"], "who": f["who"], "text": f["text"]})
        log.append(f"{f['op']} {f['line']}: {f.get('why', '')}")
    for f in fixes:
        if f.get("op") == "scene":
            set_path(d["scenes"][f["scene"]], f["path"], f["value"])
            log.append(f"scene {f['scene']}.{f['path']}: {f.get('why', '')}")
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--publish-at", help="予約公開の時刻（ISO、+09:00 つき）")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    path = pathlib.Path(a.script)
    split_lines.main(str(path))
    d = json.loads(path.read_text(encoding="utf-8"))
    if a.dry_run:
        print(message(d, 1, ""))
        return 0
    prev, verdict = "", None
    for rnd in range(1, a.max_rounds + 1):
        u = codex_usage()
        if u is not None and u > USAGE_LIMIT:
            print(f"[stop] Codex の週の使用量が {u}% で、{USAGE_LIMIT}% を超えたので頼まない")
            return 3
        reply = ask_hiro(message(d, rnd, prev), f"{d['id']}_{rnd}")
        try:
            r = parse(reply)
        except Exception as e:
            print(f"[stop] 返事を読めなかった（{e}）。build/codex/last_{d['id']}_{rnd}.txt を見る")
            return 4
        verdict = r.get("verdict")
        fixes = r.get("fixes") or []
        print(f"[info] {rnd}回目：{verdict}・直し {len(fixes)}件（週 {u}%）")
        log = apply(d, fixes) if fixes else []
        d.setdefault("audit", []).append({"by": "ヒロ（gpt-6.1-sol medium）", "date": datetime.date.today().isoformat(),
                                          "round": rnd, "verdict": verdict, "fixes": log, "notes": r.get("notes", "")})
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        split_lines.main(str(path))
        d = json.loads(path.read_text(encoding="utf-8"))
        if verdict == "可" and not fixes:
            break
        # 10/9 最後の回の直しが「読み（say）だけ」なら、当てた時点で可とみなす（字幕・画面・中身は変わらないため）
        if rnd == a.max_rounds and fixes and all(f.get("op") == "replace" and f.get("say") and not f.get("text")
                                                 and not f.get("who") for f in fixes):
            verdict = "可"
            d["audit"][-1]["verdict"] = "可"
            d["audit"][-1]["notes"] += "（最後の直しが読みだけだったので、当てて可とした）"
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
            break
        if verdict == "不可":
            print("[stop] 「不可」なので止めた。台本を書き直す")
            return 2
        prev = "\n## 前回の指摘（当てた直し）\n" + "\n".join("- " + x for x in log) + "\n"
    if verdict != "可":
        print(f"[stop] {a.max_rounds}回で「可」にならなかった。本人に知らせる")
        return 2
    if a.publish_at == "auto":
        a.publish_at = free_slot(d.get("format"))
    if a.publish_at:
        q = ROOT / "queue"
        q.mkdir(exist_ok=True)
        d["publish_at"] = a.publish_at
        out = q / f"{a.publish_at[:16].replace(':', '').replace('-', '')}_{d['id']}.json"
        out.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[info] 「可」→ 棚に入れた: {out.relative_to(ROOT)}")
    else:
        print("[info] 「可」（--publish-at が無いので棚には入れない）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
