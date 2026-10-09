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
EMOTE_FONTS = ["C:/Windows/Fonts/meiryob.ttc", str(pathlib.Path.home() / ".fonts" / "NotoSansCJKjp-Bold.otf"), "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
               "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"]


# 10/9 本人「記号おけです。今後も増やしていきましょうね」→ 相手に付く記号も。
#   めたんがずんだもんの勘違いを直す → ずんだもんに汗、ずんだもんが分かった → 電球、めたんの「正解は」→ きらきら
FIX_HEADS = ("半分はずれ", "はずれ", "違う", "ちがう", "惜しい", "おしい", "いいえ", "そうじゃない", "残念")
GOT_IT = ("なるほど", "分かったのだ", "わかったのだ", "そういうことなのだ", "分かってきたのだ")
SPECIAL = ("sweat", "bulb", "sparkle", "…w")  # 4秒の間あけを待たずに出す
EMOTE_EXTRA = True  # 10/9 本人「だいぶ自然になりました いいと思います」


def emote_for(ln, prev=None, extra=None):
    """(記号, 色, 付ける人)。付ける人は、ふつうは話している人。"""
    e = _emote_for(ln, prev, EMOTE_EXTRA if extra is None else extra)
    return None if e is None else (e + (ln.get("who"),) if len(e) == 2 else e)


def _emote_for(ln, prev=None, extra=False):
    t = (ln.get("text") or "").strip()
    pw = prev.get("who") if prev else None
    if not extra:
        pass
    elif ln.get("who") == "metan" and pw == "zundamon" and not prev.get("joke") and t.startswith(FIX_HEADS):
        return "sweat", (70, 150, 230), "zundamon"
    elif ln.get("who") == "zundamon" and any(k in t for k in GOT_IT):
        return "bulb", (255, 200, 40)
    elif ln.get("who") == "metan" and t.startswith("正解"):
        return "sparkle", (255, 190, 30)
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
        if sym in ("sweat", "bulb", "sparkle"):
            _EMO[k] = shape_img(sym, color, size)
            return _EMO[k]
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


def shape_img(sym, color, size):
    """字ではなく形で描く記号（汗・電球・きらきら）。紺のふち＋白のふち＋色。"""
    from PIL import ImageDraw
    ink, white = (23, 35, 58, 255), (255, 255, 255, 255)
    im = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)

    def drop(cx, cy, r):  # しずく：上がとがった丸
        for pad, col in ((9, ink), (5, white), (0, color + (255,))):
            dr.ellipse((cx - r - pad, cy - r - pad, cx + r + pad, cy + r + pad), fill=col)
            dr.polygon([(cx - r * 0.75 - pad * 0.8, cy - r * 0.45), (cx + r * 0.75 + pad * 0.8, cy - r * 0.45),
                        (cx, cy - r * 2.1 - pad * 1.4)], fill=col)

    def star(cx, cy, r, col):  # 4つの角のきらきら
        pts = []
        for j in range(8):
            ang = math.pi / 4 * j - math.pi / 2
            rr = r if j % 2 == 0 else r * 0.28
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        dr.polygon(pts, fill=col)

    if sym == "sweat":
        drop(size * 0.55, size * 1.0, size * 0.28)
        drop(size * 1.15, size * 1.3, size * 0.2)
    elif sym == "bulb":
        cx, cy, r = size, size * 0.85, size * 0.42
        for j in range(7):  # 光の線
            ang = math.pi + math.pi / 6 * j
            x1, y1 = cx + (r + 18) * math.cos(ang), cy + (r + 18) * math.sin(ang)
            x2, y2 = cx + (r + 48) * math.cos(ang), cy + (r + 48) * math.sin(ang)
            dr.line((x1, y1, x2, y2), fill=ink, width=16)
            dr.line((x1, y1, x2, y2), fill=color + (255,), width=8)
        for pad, col in ((9, ink), (5, white), (0, color + (255,))):
            dr.ellipse((cx - r - pad, cy - r - pad, cx + r + pad, cy + r + pad), fill=col)
            dr.rectangle((cx - r * 0.45 - pad, cy + r * 0.6, cx + r * 0.45 + pad, cy + r * 1.35 + pad), fill=col)
        dr.rectangle((cx - r * 0.45, cy + r * 1.0, cx + r * 0.45, cy + r * 1.35), fill=(150, 160, 175, 255))
    else:  # sparkle
        for (cx, cy, r) in ((size * 0.9, size * 0.9, size * 0.55), (size * 1.5, size * 0.45, size * 0.28),
                            (size * 1.45, size * 1.35, size * 0.2)):
            star(cx, cy, r + 10, ink)
            star(cx, cy, r + 5, white)
            star(cx, cy, r, color + (255,))
    return im.crop(im.getbbox())


# 10/9 本人「SE はついてる？小さめで自然にならしたい」→ 記号ごとの小さな音（sfx.emote）。mock_build が声に混ぜる。
EMOTE_SFX = False  # 見本に本人の OK が出たら True に
EMOTE_SOUND = {"？": "q", "！": "excl", "！？": "excl", "♪": "hehe", "…w": "hehe",
               "sweat": "drop", "bulb": "ding", "sparkle": "twinkle"}


def pick_emotes(lines, data):
    """台詞の番号 → (記号, 色, 付ける人)。出しすぎるとうるさいので、前に出してから4秒以上あいた台詞だけ（特別な記号は除く）。"""
    if not (EMOTE_DEFAULT if data.get("emote") is None else data["emote"]):
        return {}
    emo_ok, last = {}, -99.0
    for i, ln in enumerate(lines):
        prev = next((x for x in reversed(lines[:i]) if x.get("who")), None)  # 考える時間をとばした前の台詞
        e = emote_for(ln, prev, data.get("emote_extra"))
        if ln.get("who") and not ln["scene"].startswith("_") and e and (ln["start"] - last >= 4.0 or e[0] in SPECIAL):
            emo_ok[i] = e
            last = ln["start"]
    return emo_ok


def emote_cues(lines, data):
    """記号の音：(秒, 種類, 案, 追加の音量dB)。sound_mix.mix の cues に足す。"""
    if not (EMOTE_SFX if data.get("emote_sfx") is None else data["emote_sfx"]):
        return []
    return [(lines[i]["start"] + 0.05, "emote", EMOTE_SOUND[e[0]], -9.0)
            for i, e in pick_emotes(lines, data).items() if e[0] in EMOTE_SOUND]


_SPR = {}


def sprite(name, width):
    k = (name, width)
    if k not in _SPR:
        im = Image.open(ROOT / "assets" / "emotes" / f"{name}.png").convert("RGBA")
        _SPR[k] = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    return _SPR[k]


def _put(frame, im, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if scale <= 0.02 or alpha <= 0.01:
        return
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1) > 0.01:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 1:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    frame.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def paste_sprite(frame, name, t0, t, box, kind):
    """10/9 本人「汗・電球・きらきら もっと自然でデザインよく」→ SVG で描いた絵を、それぞれの動きで出す。
    box = (左, 上, 幅, 高さ, key)：立ち絵の位置。頭のまわりに置く。"""
    x0, y0, cw, chh, key = box
    k = 1.0 if kind == "long" else 1.2
    life = 1.6
    p = (t - t0) / life
    if p < 0 or p > 1:
        return
    fade = min(1.0, p / 0.12) * (1.0 if p < 0.65 else max(0.0, 1 - (p - 0.65) / 0.35))
    face = 1 if key == "zunda" else -1  # 顔の向き（ずんだもんは右、めたんは左を向く）
    hx = x0 + cw * (0.47 if key == "zunda" else 0.53)  # 頭のまんなか
    hy = y0 + chh * 0.17
    if name == "sweat":  # 頭の横（顔の向きと反対側の少し上）に1粒、少しずつ下へ
        _put(frame, sprite("sweat", int(78 * k)), hx - face * cw * 0.22, hy + chh * 0.03 + 26 * k * p, alpha=fade)
    elif name == "bulb":  # 顔の側の斜め上でぽんと出て、光がふわっと（真上だとショートで字幕にかかる）
        pop = 0.55 + p / 0.18 * 0.6 if p < 0.18 else (1.15 - (p - 0.18) / 0.1 * 0.15 if p < 0.28 else 1.0)
        pop *= 1 + 0.03 * math.sin(t * 12)
        _put(frame, sprite("bulb", int(130 * k)), hx + face * cw * 0.36, hy - chh * 0.06, pop, fade)
    else:  # きらきら：大きさの違う3つが、少しずつずれてまたたく
        for dx, dy, size, delay in ((-0.30, -0.10, 96, 0.0), (0.26, -0.20, 60, 0.12), (-0.08, -0.26, 44, 0.24)):
            q = (p - delay) / 0.62
            if not 0 <= q <= 1:
                continue
            tw = math.sin(math.pi * q)
            _put(frame, sprite("sparkle", int(size * k)), hx + face * cw * dx * -1 + 0, hy + chh * dy,
                 0.35 + 0.65 * tw, fade, rot=20 * q)


def paste_emote(frame, ln, e, t, x, y, w, kind, side="left"):
    """台詞 ln の始めの約0.9秒（「…w」は1.4秒）、(x, y) の近くに記号 e を出す。"""
    if not e or not ln.get("who"):
        return
    p = (t - ln["start"]) / (1.4 if e[0] in SPECIAL else 0.9)
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
    emo_ok = pick_emotes(lines, data)
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
            if speaking and li in emo_ok and emo_ok[li][2] == who and emo_ok[li][0] in ("sweat", "bulb", "sparkle"):
                paste_sprite(frame, emo_ok[li][0], L["start"], t, (xs[key], h - im.height, im.width, im.height, key), kind)
            elif speaking and li in emo_ok and emo_ok[li][2] == who:
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
