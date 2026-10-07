#!/usr/bin/env python3
"""モックの音（声・BGM・効果音）と、画面を合わせるための時刻表を作る。

なぜ要るのか:
  2026-10-07 本人「モック出せる？デザインもちゃんとしたいし、うっすらBGMも流したいし、
  うっすら効果音も入れたい」。台本（mock/*.json）から VOICEVOX で声を作り、
  BGM と効果音を重ねた 1本の mp3 と、台詞ごとの開始・終了の時刻表（json）を書き出す。
  画面（HTML）は時刻表を見て、いまの台詞・場面・段を出す。

使い方:
  VOICEVOX を http://127.0.0.1:50021 で動かしてから
  python scripts/mock_build.py mock/long_kadouritsu.json build/mock
"""
import json
import pathlib
import subprocess
import sys
import wave

import numpy as np
import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sfx  # noqa: E402
import sound_mix  # noqa: E402

SR = sfx.SR
URL = "http://127.0.0.1:50021"
SPEAKER = {"zundamon": 3, "metan": 2}
PITCH = {"metan": 0.03}
LEAD = 0.6        # 最初の無音
GAP = 0.3         # 台詞と台詞の間
SCENE_GAP = 0.55  # 場面が変わるときは少し長く
TAIL = 1.5        # 最後の余韻


def synth(text, who, tune):
    """tune: {"speaker", "speed", "pitch", "intonation"}。10/7 本人「ずんだもんは棒読み、めたんは上ずって聞こえる」
    → 抑揚（intonationScale）と高さを台本の json で決められるようにした。"""
    spk = tune.get("speaker", SPEAKER[who])
    q = requests.post(f"{URL}/audio_query", params={"text": text, "speaker": spk}, timeout=60).json()
    q["speedScale"] = tune.get("speed", 1.0)
    q["pitchScale"] = tune.get("pitch", PITCH.get(who, 0.0))
    q["intonationScale"] = tune.get("intonation", 1.0)
    q["prePhonemeLength"] = 0.0
    q["postPhonemeLength"] = 0.05
    q["pauseLengthScale"] = 0.85
    q["outputSamplingRate"] = SR
    r = requests.post(f"{URL}/synthesis", params={"speaker": spk}, json=q, timeout=120)
    r.raise_for_status()
    import io
    with wave.open(io.BytesIO(r.content), "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    return x


def main(script_path, out_dir):
    spec = json.loads(pathlib.Path(script_path).read_text(encoding="utf-8"))
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pieces, cues, timeline = [], [], []
    t = LEAD
    pieces.append(np.zeros(int(LEAD * SR)))
    prev_scene = None
    for i, ln in enumerate(spec["lines"]):
        if prev_scene is not None:
            g = SCENE_GAP if ln["scene"] != prev_scene else GAP
            pieces.append(np.zeros(int(g * SR)))
            t += g
        if ln.get("sfx"):
            cues.append((max(0.0, t - 0.08), ln["sfx"], "a", 0.0))
        if ln.get("pause"):
            dur = float(ln["pause"])
            x = np.zeros(int(dur * SR))
            if ln.get("countdown"):
                for k in range(int(dur)):
                    cues.append((t + k, "pop", "b", -4.0))
        else:
            tune = spec.get("voice", {}).get(ln["who"]) or {"speed": spec["speed"][ln["who"]]}
            x = synth(ln.get("say") or ln["text"], ln["who"], tune)
            dur = len(x) / SR
        timeline.append({**{k: v for k, v in ln.items() if k != "say"}, "i": i,
                         "start": round(t, 3), "end": round(t + dur, 3)})
        pieces.append(x)
        t += dur
        prev_scene = ln["scene"]
    pieces.append(np.zeros(int(TAIL * SR)))
    voice = np.concatenate(pieces)
    bgm = sound_mix._decode(spec["bgm"]) if spec.get("bgm") else None
    y = sound_mix.mix(voice, bgm=bgm, cues=cues, bgm_db=-24.0, duck_db=-6.0, sfx_db=-13.0)
    wav = out / f"{spec['id']}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    mp3 = out / f"{spec['id']}.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "128k", str(mp3)], check=True)
    wav.unlink()
    meta = {"id": spec["id"], "title": spec["title"], "duration": round(len(y) / SR, 3), "lines": timeline}
    (out / f"{spec['id']}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[info] {spec['id']}: {meta['duration']:.1f}秒・{len(timeline)}行 -> {mp3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "build/mock"))
