#!/usr/bin/env python3
"""長編のサムネ（1280×720 の JPEG）を台本から作り、必要なら YouTube に設定する。

なぜ要るのか:
  2026-10-08 本人「サムネ、めたんとずんだもん両方入れる感じに。ならんでタイトルの方を向いてる感じで、
  笑顔系でランダムに表情つかって」。表情は動画の id から決める（作り直しても同じ表情になる）。

文字の決め方（台本に "thumb": {"main", "sub", "no", "badge"} があればそれを使う）:
  main … upload.title の「｜」より前（【…】は外す）。「 ― 」があれば前を main、後ろを sub。
  tag  … topic（例：応用情報｜経営戦略）。no … 題の「第N回」。badge … 午後の回は「午後の解き方」、クイズがあれば「過去問つき」。

使い方:
  python scripts/make_thumb.py 台本.json 出力.jpg
"""
import hashlib
import json
import os
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SMILES = [  # 笑顔系の組み合わせ（目・眉・口）
    {"eye": "smile", "brow": "base", "mouth": "open"},
    {"eye": "open", "brow": "base", "mouth": "smile"},
    {"eye": "smile", "brow": "base", "mouth": "smile"},
    {"eye": "open", "brow": "up", "mouth": "open"},
    {"eye": "wide", "brow": "up", "mouth": "big"},
]


def texts(d):
    t = dict(d.get("thumb") or {})
    title = re.sub(r"【[^】]*】", "", d["upload"]["title"]).split("｜")[0].strip()
    if "main" not in t:
        if " ― " in title:
            t["main"], sub = title.split(" ― ", 1)
            t.setdefault("sub", sub)
        else:
            m = re.match(r"(.+?)（(.+)）$", title)
            t["main"] = m.group(1) if m else title
            if m:
                t.setdefault("sub", m.group(2))
    head, _, field = (d.get("topic") or "応用情報｜").partition("｜")
    t.setdefault("tag", f"{head}｜{field}" if field else head)
    m = re.search(r"第(\d+)回", d["upload"]["title"])
    t.setdefault("no", f"第{m.group(1)}回" if m else "")
    if "badge" not in t:
        if "午後" in (d.get("topic") or ""):
            t["badge"] = "午後の解き方"
        elif any(s.get("type") == "quiz" for s in d.get("scenes", {}).values()):
            t["badge"] = "過去問つき"
    rng = random.Random(int(hashlib.md5(d["id"].encode()).hexdigest(), 16))
    t["metan"], t["zunda"] = rng.choice(SMILES), rng.choice(SMILES)
    return t


def kind(ch):
    if re.match(r"[ァ-ヶー]", ch):
        return "k"
    if re.match(r"[ぁ-ん]", ch):
        return "h"
    if re.match(r"[一-龥々]", ch):
        return "c"
    return "o"


def wrap(text, limit=5):
    """言葉の途中で折り返さないように、2行に分ける位置を決める（「の」「で」などの後、文字の種類の切れ目）。"""
    plain = re.sub(r"[［］]", "", text)
    if len(plain) <= limit:
        return text
    cands = []
    for i in range(2, len(plain) - 1):
        a, b = plain[i - 1], plain[i]
        if a in "のでをがとはにへ・":
            cands.append((abs(i - len(plain) / 2), i))
        elif kind(a) != kind(b) and kind(a) in "kc" and kind(b) in "kc":
            cands.append((abs(i - len(plain) / 2) + 2, i))  # 文字の種類の切れ目は、助詞の後より後回し
    if not cands:
        return text
    cut = min(cands)[1]
    # ［］を含む元の文字列の、同じ位置で切る（［ の直前で切るときは ［ の前に入れる）
    n = 0
    for j, ch in enumerate(text):
        if ch in "［］":
            if ch == "［" and n == cut:
                return text[:j] + "¦" + text[j:]
            continue
        if n == cut:
            return text[:j] + "¦" + text[j:]
        n += 1
    return text


def render(d, out, style=None):
    from playwright.sync_api import sync_playwright
    t = texts(d)
    t["main"] = wrap(t["main"])
    t["style"] = style or t.get("style") or os.environ.get("APSC_THUMB_STYLE", "note")
    img_dir = (ROOT / "build" / "thumbparts")
    if not img_dir.exists():
        make_parts(img_dir)
    ch = os.environ.get("APSC_BROWSER", "msedge")
    with sync_playwright() as p:
        b = p.chromium.launch(channel=ch) if ch != "chromium" else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.goto((ROOT / "video" / "thumb.html").as_uri())
        pg.evaluate(f"window.IMG={json.dumps(img_dir.as_uri())}")
        pg.evaluate("d => window.draw(d)", t)
        pg.wait_for_timeout(300)
        png = pathlib.Path(out).with_suffix(".png")
        pg.locator(".t").screenshot(path=str(png))
        b.close()
    from PIL import Image
    Image.open(png).convert("RGB").save(out, quality=90)
    png.unlink()
    return out


def make_parts(d):
    """立ち絵の部品を、サムネ用の大きさの webp にしておく（モックの img2 と同じ切り方）。"""
    from PIL import Image
    d.mkdir(parents=True, exist_ok=True)
    name = {"体": "body", "右腕": "ra", "左腕": "la", "目": "eye", "眉": "brow", "口": "mouth"}
    val = {"基本": "base", "上げ": "up", "考え": "think", "指": "point", "開": "open", "閉": "close", "笑": "smile",
           "見開": "wide", "ジト": "jito", "困り": "trouble", "大": "big"}
    for key, (folder, box) in {"metan": ("四国めたん", (60, 0, 1022, 1080)), "zunda": ("ずんだもん", (150, 0, 1062, 1000))}.items():
        for f in (ROOT / "assets" / "portraits" / folder).glob("*.png"):
            g, _, v = f.stem.partition("_")
            im = Image.open(f).convert("RGBA").crop(box)
            im = im.resize((540, round(im.height * 540 / im.width)), Image.LANCZOS)
            im.save(d / (f"{key}_{name[g]}" + (f"_{val[v]}" if v else "") + ".webp"), quality=90)


def set_thumbnail(video_id, path):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    sys.path.insert(0, str(ROOT / "scripts"))
    import upload_youtube
    yt = build("youtube", "v3", credentials=upload_youtube.credentials())
    yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(path), mimetype="image/jpeg")).execute()


if __name__ == "__main__":
    d = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(render(d, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
