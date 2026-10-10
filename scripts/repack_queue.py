#!/usr/bin/env python3
"""棚（queue/）の予約時刻を、今の枠（produce.SLOTS）で前から詰め直す。

なぜ要るのか:
  2026-10-10 本人「台本だけどんどん溜まってるけど、投稿が追いついてない？ OKなやつからどんどん出せないか」。
  枠を増やしたとき、すでに棚にある分は古い枠のままなので、順番は変えずに空いた早い枠へ詰める。
  YouTube にもう上げた分（published/）の時刻は動かさない。

使い方:
  python scripts/repack_queue.py            # 詰めたあとの日ごとの本数を見るだけ
  python scripts/repack_queue.py --apply    # ファイル名と publish_at を書き換える
  --start 2026-10-11  … この日から詰める（既定は明日。翌朝の自動投稿で上がる時刻なので）
"""
import argparse
import collections
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from produce import SLOTS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--start", default=None)
    a = ap.parse_args()
    start = (datetime.date.fromisoformat(a.start) if a.start
             else datetime.date.today() + datetime.timedelta(days=1))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    used = {f.name[:13] for f in (ROOT / "published").glob("*.json")}
    q = ROOT / "queue"
    items = collections.defaultdict(list)
    for f in sorted(q.glob("*.json")):  # ファイル名の順＝今の予約の順
        d = json.loads(f.read_text(encoding="utf-8"))
        items["short" if d.get("format") == "short" else "long"].append((f, d))
    plan = []
    for fmt, lst in items.items():
        day, i = start, 0
        while i < len(lst):
            for hm in sorted(SLOTS[fmt]):
                if i >= len(lst):
                    break
                key = day.strftime("%Y%m%d") + "T" + hm.replace(":", "")
                at = datetime.datetime.fromisoformat(f"{day.isoformat()}T{hm}:00+09:00")
                if key in used or at <= now + datetime.timedelta(hours=1):
                    continue
                f, d = lst[i]
                i += 1
                plan.append((f, d, key, at))
            day += datetime.timedelta(days=1)
    per = collections.Counter()
    for f, d, key, at in plan:
        per[key[:8]] += 1
    for k in sorted(per):
        print(k, per[k])
    moved = sum(1 for f, d, key, at in plan if f.name[:13] != key)
    print(f"[info] 棚 {len(plan)}本・時刻が変わる {moved}本")
    if not a.apply:
        return 0
    tmp = []
    for f, d, key, at in plan:  # 名前がぶつからないよう、いったん別名にしてから付け直す
        d["publish_at"] = at.isoformat(timespec="seconds")
        t = f.with_name("_repack_" + f.name)
        f.rename(t)
        tmp.append((t, d, key))
    for t, d, key in tmp:
        name = key + "_" + t.name[len("_repack_") + 14:]
        (q / name).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        t.unlink()
    print("[info] 書き換えた")
    return 0


if __name__ == "__main__":
    sys.exit(main())
