#!/usr/bin/env python3
"""モックの画面（HTML）と声の時刻表から mp4 を作る。

なぜ要るのか:
  2026-10-08 本人「挙げられるのから挙げていこう」。モックの見た目のまま動画ファイルにする。
  画面を毎コマ撮ると遅いので、
    1) 場面・段・字幕が変わるところだけ、ブラウザ（Edge）で静止画にする（キャラは隠す）
    2) 立ち絵は部品（体・腕・眉・目・口）をコマごとに重ねる（口パク・まばたき・話す人の揺れ）
    3) 場面が変わるところは 0.3 秒で重ね合わせる
  という作りにした。音は mock_build.py が作った mp3 をそのまま使う。

使い方:
  python scripts/render_video.py short build/mock   → build/mock/short.mp4
  （build/mock/preview.html・<id>.json・<id>.mp3 が要る。preview.html は index.html に文字コードの行を足したもの）
"""
import json
import math
import pathlib
import subprocess
import sys

from PIL import Image, ImageEnhance

ROOT = pathlib.Path(__file__).resolve().parent.parent
FPS = 30
FADE = 0.3
SIZE = {"long": (1920, 1080), "short": (1080, 1920)}
# 立ち絵：部品の切り抜き範囲（モックの img2 と同じ）と、画面での幅・左右の余白
CROP = {"metan": ("四国めたん", (60, 0, 1022, 1080)), "zunda": ("ずんだもん", (150, 0, 1062, 1000))}
WHO_W = {"long": 380, "short": 430}
PAD = {"long": 6, "short": 0}
EXPR = {"neutral": ("open", "base", "close"), "smile": ("smile", "base", "smile"),
        "surprise": ("wide", "up", "big")}
PART = {"eye": "目", "brow": "眉", "mouth": "口"}
VAL = {"open": "開", "close": "閉", "smile": "笑", "wide": "見開", "base": "基本", "up": "上げ", "big": "大"}

SNAP_JS = """
async ([kind, st]) => {
  if (!window.__stage) {
    const t = document.getElementById('T_' + kind);
    document.body.innerHTML = '';
    document.body.style.margin = '0';
    const host = document.createElement('div');
    host.appendChild(t.content.cloneNode(true));
    document.body.appendChild(host);
    window.__stage = host.querySelector('.frame');
    window.__stage.querySelector('.cast').style.display = 'none';
    await document.fonts.ready;
  }
  const F = window.__stage;
  F.querySelectorAll('.sc').forEach(s => { s.className = 'sc' + (s.dataset.sc === st.scene ? ' show st' + st.step : ''); });
  F.querySelectorAll('.sc, .rv').forEach(e => e.style.transition = 'none');
  const tab = F.querySelector('[data-tab]');
  if (tab) { tab.textContent = st.chapter || ''; tab.style.opacity = st.chapter ? 1 : 0; tab.style.transition = 'none'; }
  const subt = F.querySelector('.subt');
  subt.style.transition = 'none';
  if (st.who) {
    subt.classList.remove('hide');
    const nm = subt.querySelector('.nm'); nm.textContent = st.name; nm.className = 'nm ' + st.who;
    subt.querySelector('.tx').textContent = st.text;
    subt.querySelector('.jk').hidden = true;
  } else { subt.classList.add('hide'); }
  const c = F.querySelector('[data-count]');
  if (c && st.count) c.textContent = st.count;
  return true;
}
"""


def states_of(data):
    """時刻表から、画面が変わる時刻と、その時の状態の一覧を作る。"""
    out, chapter, last_who = [], "", None
    for ln in data["lines"]:
        chapter = ln.get("chapter") or chapter
        base = {"scene": ln["scene"], "step": ln["step"], "chapter": chapter}
        if ln.get("who"):
            last_who = {"who": ln["who"], "name": {"metan": "めたん", "zundamon": "ずんだもん"}[ln["who"]],
                        "text": ln["text"]}
            out.append((ln["start"], {**base, **last_who}))
        elif ln.get("countdown"):
            n = int(round(ln["end"] - ln["start"]))
            for k in range(n):
                out.append((ln["start"] + k, {**base, "count": n - k}))
        else:
            out.append((ln["start"], {**base, **(last_who or {})}))
    out[0] = (0.0, out[0][1])
    return out


def snapshot(vid, kind, states, page_url, out_dir, data=None):
    """data に "scenes" があれば共通のページ video/frame.html（setup/setState）で撮る。無ければモックのページ。"""
    from playwright.sync_api import sync_playwright
    w, h = SIZE[kind]
    files = []
    with sync_playwright() as p:
        import os
        ch = os.environ.get("APSC_BROWSER", "msedge")  # GitHub Actions では chromium
        b = p.chromium.launch(channel=ch) if ch != "chromium" else p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.goto(page_url)
        pg.wait_for_load_state("networkidle")
        generic = bool(data and data.get("scenes"))
        if generic:
            pg.evaluate("ep => window.setup(ep)", data)
        for i, (_, st) in enumerate(states):
            if generic:
                pg.evaluate("st => window.setState(st)", st)
            else:
                pg.evaluate(SNAP_JS, [vid, st])
            pg.wait_for_timeout(60)
            f = out_dir / f"st_{i:04d}.png"
            pg.locator(".frame").screenshot(path=str(f))
            files.append(f)
        b.close()
    return files


# 10/8 本人「ずんだもんとめたんの頭上や周りに、セリフや感情・表情に合わせて記号（！や？など色つき）を浮かばせたり
# フェードアウトさせたり」→ 台詞の頭の約0.9秒、話す人の頭の近くに記号をぽんと出し、少し上がりながら消す。
EMOTE_DEFAULT = True  # 10/8 本人「記号おけです。今後も増やしていきましょう」
EMOTE_FONTS = ["C:/Windows/Fonts/meiryob.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
               "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"]


def emote_for(ln, prev=None):
    t = (ln.get("text") or "").strip()
    # 10/8 本人「ずんだもんが冗談を言ったら、それに答えつつ『…w』をめたんに」
    if prev and prev.get("joke") and prev.get("who") == "zundamon" and ln.get("who") == "metan":
        return "…w", (122, 104, 160)
    if ln.get("expr") == "surprise":
        return "！？", (229, 72, 77)
    if ln.get("joke"):
        return "♪", (255, 95, 162)
    if t.endswith("？"):
        return "？", (47, 125, 225)
    if t.endswith("！"):
        return "！", (255, 140, 40)
    if ln.get("expr") == "smile":
        return "♪", (255, 95, 162)
    return None


_EMO = {}


def emote_img(sym, color, size):
    k = (sym, color, size)
    if k not in _EMO:
        from PIL import ImageDraw, ImageFont
        font = None
        for f in EMOTE_FONTS:
            try:
                font = ImageFont.truetype(f, size)
                break
            except OSError:
                continue
        if font is None:  # 日本語の字体が無い環境でも止めない（記号は英字の字体で描ける）
            font = ImageFont.load_default(size)
        im = Image.new("RGBA", (size * 3, size * 2), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        sw = max(4, size // 12)
        ink = (23, 35, 58, 255)
        if sym == "…w":  # 字の「…」は四角い点になるので、丸を3つ描いてから w
            r = size * 0.075
            for j in range(3):
                cx, cy = size * (0.45 + j * 0.28), size * 1.08
                dr.ellipse((cx - r - sw, cy - r - sw, cx + r + sw, cy + r + sw), fill=ink)
                dr.ellipse((cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3), fill=(255, 255, 255, 255))
                dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (255,))
            wx, sym = size * 1.25, "w"
        else:
            wx = size * 0.3
        dr.text((wx, size * 0.2), sym, font=font, fill=ink, stroke_width=sw + 5, stroke_fill=ink)
        dr.text((wx, size * 0.2), sym, font=font, fill=color + (255,), stroke_width=sw, stroke_fill=(255, 255, 255, 255))
        im = im.crop(im.getbbox()).rotate(-10 if k[0] != "？" else 10, resample=Image.BICUBIC, expand=True)
        _EMO[k] = im
    return _EMO[k]


def paste_emote(frame, ln, e, t, x, y, w, kind, side="left"):
    """台詞 ln の始めの約0.9秒（「…w」は1.4秒）、(x, y) の近くに記号 e を出す。"""
    if not e or not ln.get("who"):
        return
    p = (t - ln["start"]) / (1.4 if e[0] == "…w" else 0.9)
    if p < 0 or p > 1:
        return
    scale = 0.6 + p / 0.2 * 0.5 if p < 0.2 else (1.1 - (p - 0.2) / 0.1 * 0.1 if p < 0.3 else 1.0)
    alpha = 1.0 if p < 0.6 else max(0.0, 1 - (p - 0.6) / 0.4)
    base = 120 if kind == "long" else 150
    im = emote_img(e[0], e[1], base)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 1:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    # 横に長い記号は、顔にかからないよう相手の側へ寄せる
    ax = 0.5 if im.width < im.height * 1.3 else (0.85 if side == "right" else 0.15)
    frame.paste(im, (int(x - im.width * ax), int(y - im.height - 30 * p)), im)


class Cast:
    """立ち絵の部品を重ねた絵を、組み合わせごとに覚えておく。"""

    def __init__(self, kind):
        self.w = WHO_W[kind]
        self.cache = {}
        self.parts = {}

    def _part(self, key, name):
        k = (key, name)
        if k not in self.parts:
            folder, box = CROP[key]
            im = Image.open(ROOT / "assets" / "portraits" / folder / f"{name}.png").convert("RGBA").crop(box)
            h = round(im.height * self.w / im.width)
            self.parts[k] = im.resize((self.w, h), Image.LANCZOS)
        return self.parts[k]

    def get(self, key, eye, brow, mouth, dim):
        k = (key, eye, brow, mouth, dim)
        if k not in self.cache:
            im = self._part(key, "体").copy()
            for n in ("右腕_基本", "左腕_基本", f"眉_{VAL[brow]}", f"目_{VAL[eye]}", f"口_{VAL[mouth]}"):
                im.alpha_composite(self._part(key, n))
            if key == "zunda":
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            if dim:
                a = im.getchannel("A")
                im = ImageEnhance.Brightness(ImageEnhance.Color(im.convert("RGB")).enhance(0.75)).enhance(0.96).convert("RGBA")
                im.putalpha(a)
            self.cache[k] = im
        return self.cache[k]


def main(vid, d):
    d = pathlib.Path(d)
    data = json.loads((d / f"{vid}.json").read_text(encoding="utf-8"))
    kind = data.get("format") or ("short" if vid == "short" else "long")
    states = states_of(data)
    snap_dir = d / f"frames_{vid}"
    snap_dir.mkdir(exist_ok=True)
    page = (ROOT / "video" / "frame.html").as_uri() if data.get("scenes") else (d / "preview.html").resolve().as_uri()
    files = snapshot(vid, kind, states, page, snap_dir, data)
    # 10/8 本人「最初はチャンネル名とタイトル、動画のテーマを同時に」→ 長編の _open はサムネの見た目にチャンネル名の帯
    for i, (_, st) in enumerate(states):
        if st.get("scene") == "_open" and data.get("upload"):
            import make_thumb
            make_thumb.render(data, str(snap_dir / f"st_{i:04d}.jpg"), channel=True, scale=1.5)
            files[i] = snap_dir / f"st_{i:04d}.jpg"
    imgs = [Image.open(f).convert("RGB") for f in files]
    w, h = SIZE[kind]
    imgs = [im if im.size == (w, h) else im.resize((w, h)) for im in imgs]
    cast = Cast(kind)
    times = [t for t, _ in states]
    n = int(math.ceil(data["duration"] * FPS))
    out = d / f"{vid}.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                           "-r", str(FPS), "-i", "-", "-i", str(d / f"{vid}.mp3"), "-c:v", "libx264",
                           "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
                           "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    lines = data["lines"]
    # 記号は出しすぎるとうるさいので、前に出してから4秒以上あいた台詞だけ
    emo_ok, last = {}, -99.0
    for i, ln in enumerate(lines):
        e = emote_for(ln, lines[i - 1] if i else None)
        if ln.get("who") and not ln["scene"].startswith("_") and e and (ln["start"] - last >= 4.0 or e[0] == "…w"):
            emo_ok[i] = e
            last = ln["start"]
    for fi in range(n):
        t = fi / FPS
        si = max(i for i, x in enumerate(times) if x <= t + 1e-6)
        frame = imgs[si]
        if si > 0 and t - times[si] < FADE and states[si][1]["scene"] != states[si - 1][1]["scene"]:
            frame = Image.blend(imgs[si - 1], imgs[si], (t - times[si]) / FADE)
        frame = frame.copy()
        li = max(i for i, ln in enumerate(lines) if ln["start"] <= t + 1e-6) if t >= lines[0]["start"] else 0
        L = lines[li]
        speaking = L["start"] <= t < L["end"] and L.get("who")
        if L.get("scene") == "_open":  # サムネの絵にキャラが入っているので重ねない
            ff.stdin.write(frame.tobytes())
            continue
        xs = {"zunda": PAD[kind], "metan": w - PAD[kind] - cast.w}
        for key, who, off in (("zunda", "zundamon", 1.7), ("metan", "metan", 0.0)):
            me = speaking and L["who"] == who
            eye, brow, mouth = EXPR[(me and L.get("expr")) or "neutral"]
            if me and int(t * 9) % 2 == 0:
                mouth = "big" if mouth == "big" else "open"
            if eye == "open" and ((t + off) % 3.9) < 0.13:
                eye = "close"
            im = cast.get(key, eye, brow, mouth, not me)
            bob = -8 * (1 - math.cos(math.pi * t / 0.5)) / 2 if me else 0
            frame.paste(im, (xs[key], h - im.height + round(bob) + (8 if me else 0)), im)
            if me and li in emo_ok and (EMOTE_DEFAULT if data.get("emote") is None else data["emote"]):
                # 頭の上：ずんだもん（左・右向き）は右寄り、めたん（右・左向き）は左寄り
                hx = xs[key] + (cast.w * 0.92 if key == "zunda" else cast.w * 0.08)
                paste_emote(frame, L, emo_ok[li], t, hx, h - im.height + (150 if kind == "long" else 190), cast.w, kind,
                            "right" if key == "metan" else "left")
        ff.stdin.write(frame.tobytes())
    ff.stdin.close()
    ff.wait()
    print(f"[info] {out}（{n}コマ・場面の静止画 {len(files)}枚）")
    return ff.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "build/mock"))
