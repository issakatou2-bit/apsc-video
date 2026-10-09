#!/usr/bin/env python3
"""台詞の読み（say）が文全体カタカナになっているものを、漢字のまま読ませる形に戻す。

なぜ要るのか:
  2026-10-10 本人「カタカナで台本に渡すと、イントネーションがおかしくなることもある」。
  調べると、1005 の下書きには文全体をカタカナにした say が約400あり、カタカナだと助詞の「は」を「ハ」と読むなど
  かえって読み間違えていた。漢字の字幕（text）を辞書（data/readings.json）に通したものを読ませれば、
  音声ソフトが単語ごとの抑揚をつけてくれる。

やること:
  say を持つ台詞ごとに、「text を辞書に通したもの」と「say」を音声ソフト（VOICEVOX）の音素で比べる。
  長音のゆれ（えい／ええ、おう／おお）・無声化・助詞の「は／へ」の読みの違いだけなら、say を消す（text で読む）。
  それ以外の違いがあれば say を残し、違う所を一覧に出す（辞書に足すか、その言葉だけ直す）。

使い方:
  python scripts/fix_says.py queue episodes/batch4         # 直す
  python scripts/fix_says.py queue --dry-run              # 数えるだけ
"""
import json
import pathlib
import re
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mock_build  # noqa: E402

_CACHE = {}


def phonemes(text):
    if text not in _CACHE:
        r = requests.post(f"{mock_build.URL}/audio_query", params={"text": text, "speaker": 2}, timeout=60).json()
        out = []
        for ap in r["accent_phrases"]:
            for mo in ap["moras"]:
                out.append(((mo["consonant"] or "") + mo["vowel"]).lower())
        _CACHE[text] = out
    return _CACHE[text]


def norm(ph):
    """長音のゆれをそろえる（ei→ee、ou→oo、uu）。"""
    out = []
    for p in ph:
        if out and p == "i" and out[-1].endswith("e"):
            p = "e"
        if out and p == "u" and out[-1].endswith(("o", "u")):
            p = "o" if out[-1].endswith("o") else "u"
        out.append(p)
    return out


def same(a, b):
    """助詞「は／へ」の ha/wa・he/e のちがいは同じとみなす（漢字のほうが正しく読む）。"""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y or {x, y} in ({"ha", "wa"}, {"he", "e"}):
            continue
        return False
    return True


def main(args):
    dry = "--dry-run" in args
    files = []
    for a in [x for x in args if not x.startswith("--")]:
        p = ROOT / a
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    dropped = kept = 0
    report = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        changed = False
        for ln in d.get("lines", []):
            say = ln.get("say")
            if not say or not ln.get("text"):
                continue
            if len(re.findall(r"[ァ-ヶー]", say)) < len(say) * 0.6:
                continue  # 一部だけの読み替えは、そのまま
            if same(norm(phonemes(mock_build.to_say(ln["text"]))), norm(phonemes(say))):
                if not dry:
                    ln.pop("say")
                changed = True
                dropped += 1
            else:
                kept += 1
                report.append(f"{f.name}: {ln['text']} ／ say={say}")
        if changed and not dry:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[info] カタカナの say：漢字で読ませる形に戻した {dropped}・残した {kept}")
    out = ROOT / "build" / "fix_says_kept.txt"
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"[info] 残した分の一覧 -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
