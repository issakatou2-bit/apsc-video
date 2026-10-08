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
BRAND_DEFAULT = False  # 最初と最後のチャンネル札。本人の OK（見本 build/brand_demo）が出たら True に


_READ = None


def to_say(text):
    """字幕の文字を、data/readings.json の辞書で読み上げ用に直す（say が無い台詞に使う）。"""
    global _READ
    if _READ is None:
        import re
        p = pathlib.Path(__file__).resolve().parent.parent / "data" / "readings.json"
        _READ = [(re.compile(a), b) for a, b in json.loads(p.read_text(encoding="utf-8"))["rules"]]
    for rx, rep in _READ:
        text = rx.sub(rep, text)
    return text


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
    # 10/8 本人「各動画で最初はチャンネル名、最後は手短なチャンネル説明。ショートは数秒、長編でも5秒以内」
    if spec.get("scenes") and spec.get("brand", BRAND_DEFAULT):
        lines = list(spec["lines"])
        if spec.get("format") != "short":
            # 10/8 本人「めたんが『めたん先生』と言うのはどうなの」→ 生徒役のずんだもんが呼ぶ。最初の画面は約1.5秒
            lines.insert(0, {"scene": "_open", "step": 0, "sfx": "impact", "who": "zundamon", "speed": 1.7,
                             "text": "めたん先生のIT試験ゼミ！", "say": "めたん先生の、アイティー試験ゼミ！"})
            lines.append({"scene": "_end", "step": 0, "sfx": "swish", "who": "zundamon",
                          "text": "分野ごとの再生リストで、続けて聞けるのだ。チャンネル登録で、毎日の続きが届くのだ！"})
        else:
            lines.append({"scene": "_end", "step": 0, "sfx": "swish", "who": "zundamon", "speed": 1.6,
                          "text": "くわしくは、チャンネルの解説動画で、なのだ！"})
        spec = {**spec, "lines": lines}
    pieces, cues, timeline = [], [], []
    lead = 0.15 if spec["lines"] and spec["lines"][0].get("scene") == "_open" else LEAD
    t = lead
    pieces.append(np.zeros(int(lead * SR)))
    prev_scene = None
    for i, ln in enumerate(spec["lines"]):
        if prev_scene is not None:
            g = SCENE_GAP if ln["scene"] != prev_scene else GAP
            if prev_scene == "_open":
                g = 0.12
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
            if ln.get("speed"):
                tune = {**tune, "speed": ln["speed"]}
            x = synth(ln.get("say") or to_say(ln["text"]), ln["who"], tune)
            dur = len(x) / SR
        timeline.append({**{k: v for k, v in ln.items() if k != "say"}, "i": i,
                         "start": round(t, 3), "end": round(t + dur, 3)})
        pieces.append(x)
        t += dur
        prev_scene = ln["scene"]
    pieces.append(np.zeros(int(TAIL * SR)))
    voice = np.concatenate(pieces)
    bgm = sound_mix._decode(pathlib.Path(__file__).resolve().parent.parent / spec["bgm"]) if spec.get("bgm") else None
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
    meta = {"id": spec["id"], "format": spec.get("format"), "title": spec["title"],
            "topic": spec.get("topic"), "scenes": spec.get("scenes"),
            "upload": spec.get("upload"), "thumb": spec.get("thumb"), "emote": spec.get("emote"), "duration": round(len(y) / SR, 3), "lines": timeline}
    (out / f"{spec['id']}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[info] {spec['id']}: {meta['duration']:.1f}秒・{len(timeline)}行 -> {mp3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "build/mock"))
