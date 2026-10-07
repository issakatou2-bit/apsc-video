#!/usr/bin/env python3
"""VOICEVOX の設定（速さ・高さ・抑揚・声の種類）を変えた聞き比べの音を作る。

なぜ要るのか:
  2026-10-07 本人「ずんだもんは棒読みだし、めたんは上ずってるように聞こえる」。
  モック第1版は、めたんの高さ +0.03（コレスポの値）・抑揚 1.0（既定）のままだった。
  同じ台詞を設定違いで並べ、耳で選んでもらう。

使い方:
  python scripts/voice_compare.py build/mock/voice
  → <案>_<行>.mp3 と voice.json（案の一覧）
"""
import io
import json
import pathlib
import subprocess
import sys
import wave

import requests

URL = "http://127.0.0.1:50021"

LINES = {
    "zundamon": ["鎖みたいに、1か所でも切れたらおしまい、ってことなのだ？",
                 "2台に増やしたのに、下がったのだ！ 手伝いを頼んだら、仕事が増えたみたいなのだ。"],
    "metan": ["そのとおり。だから稼働率は掛け算。0.9かける0.9で、0.81になるわ。",
              "そこがよくある勘違い。つなぎ方を変えると、逆に上がるのよ。"],
}
# 案: (名前, 話者ID, 速さ, 高さ, 抑揚, 説明)
VARIANTS = [
    ("Z1", "zundamon", 3, 1.20, 0.00, 1.00, "第1版のまま（ノーマル・速さ1.2・抑揚1.0）"),
    ("Z2", "zundamon", 3, 1.15, 0.00, 1.35, "ノーマル・抑揚を強く（1.35）"),
    ("Z3", "zundamon", 3, 1.15, 0.02, 1.60, "ノーマル・抑揚をもっと強く（1.6）・少し高く"),
    ("Z4", "zundamon", 1, 1.15, 0.00, 1.30, "あまあま・抑揚1.3"),
    ("M1", "metan", 2, 1.10, 0.03, 1.00, "第1版のまま（ノーマル・速さ1.1・高さ+0.03）"),
    ("M2", "metan", 2, 1.05, 0.00, 1.10, "高さを戻す（0）・抑揚1.1"),
    ("M3", "metan", 2, 1.05, -0.03, 1.15, "少し低く（−0.03）・抑揚1.15"),
    ("M4", "metan", 2, 1.00, -0.02, 1.25, "落ち着いて（速さ1.0・−0.02・抑揚1.25）"),
]


def synth(text, speaker, speed, pitch, inton):
    q = requests.post(f"{URL}/audio_query", params={"text": text, "speaker": speaker}, timeout=60).json()
    q.update({"speedScale": speed, "pitchScale": pitch, "intonationScale": inton,
              "prePhonemeLength": 0.05, "postPhonemeLength": 0.1, "pauseLengthScale": 0.85})
    r = requests.post(f"{URL}/synthesis", params={"speaker": speaker}, json=q, timeout=120)
    r.raise_for_status()
    return r.content


def main(out_dir):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = []
    for name, who, spk, speed, pitch, inton, note in VARIANTS:
        files = []
        for i, text in enumerate(LINES[who]):
            wav = out / f"{name}_{i}.wav"
            wav.write_bytes(synth(text, spk, speed, pitch, inton))
            mp3 = wav.with_suffix(".mp3")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "96k", str(mp3)], check=True)
            wav.unlink()
            files.append({"file": f"voice/{mp3.name}", "text": text})
        meta.append({"name": name, "who": who, "speaker": spk, "speed": speed, "pitch": pitch,
                     "intonation": inton, "note": note, "files": files})
    (out / "voice.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[info] {len(meta)}案 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "build/mock/voice"))
