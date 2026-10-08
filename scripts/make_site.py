#!/usr/bin/env python3
"""公開した長編の台本から、読める記事（GitHub Pages 用の静的なページ）を作る。

なぜ要るのか:
  2026-10-08 本人「全部やります」（台本から記事）。動画を見られないとき・検索から来た人にも、
  同じ中身を文字で読めるようにする。台本は監査済みなので、記事の中身も同じ正しさ。
  記事は published/（動画の番号つき）の長編だけ。画面の札（場面）と台詞をそのまま並べ、過去問の答えは畳んでおく。

使い方:
  python scripts/make_site.py [出力先 site]          # published/ の長編すべて
  python scripts/make_site.py site --preview 台本.json  # 動画がまだの台本で見本を作る
"""
import datetime
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME = {"zundamon": "ずんだもん", "metan": "めたん"}
CHANNEL = "めたん先生のIT試験ゼミ"
CHANNEL_URL = "https://www.youtube.com/channel/UCFPlgxr-u00RDIXYtQfKA2g"

CSS = """
:root{--bg:#fbfaf6;--paper:#fff;--fg:#17233a;--sub:#4a5872;--line:#d9e0ea;--grid:#e9eef4;--mk:#ffe066;
  --z:#3f9a2e;--m:#c4508f;--zb:#eef8ea;--mb:#fbeef5;--accent:#2f5d9e}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11161d;--paper:#1a212b;--fg:#e6ebf1;--sub:#a3afbf;
  --line:#2c3644;--grid:#161c25;--mk:#8a7420;--z:#7fcf6a;--m:#ef8fc2;--zb:#1b2a1c;--mb:#2c1d27;--accent:#8db4ea;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11161d;--paper:#1a212b;--fg:#e6ebf1;--sub:#a3afbf;--line:#2c3644;--grid:#161c25;--mk:#8a7420;
  --z:#7fcf6a;--m:#ef8fc2;--zb:#1b2a1c;--mb:#2c1d27;--accent:#8db4ea;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:"Zen Kaku Gothic New","Hiragino Sans","Yu Gothic",sans-serif;
  line-height:1.8;font-size:16px;background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:32px 32px}
a{color:var(--accent)}
.wrap{max-width:780px;margin:0 auto;padding:24px 16px 64px}
header.top{display:flex;align-items:center;gap:10px;font-weight:900;margin-bottom:18px}
header.top a{color:var(--fg);text-decoration:none}
header.top .mk{background:linear-gradient(transparent 60%,var(--mk) 60%)}
.tag{display:inline-block;background:var(--fg);color:var(--bg);font-weight:900;font-size:13px;padding:2px 10px;border-radius:6px}
h1{font-size:28px;line-height:1.35;margin:10px 0 6px}
h2{font-size:21px;margin:36px 0 10px;padding-bottom:4px;border-bottom:3px solid var(--mk)}
.lead{color:var(--sub)}
.video{position:relative;aspect-ratio:16/9;margin:16px 0;border-radius:12px;overflow:hidden;border:2px solid var(--fg);background:#000}
.video iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.toc{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:12px 18px}
.toc ol{margin:0;padding-left:1.4em}
.board{background:var(--paper);border:2px solid var(--fg);border-radius:14px;padding:14px 18px;margin:18px 0;box-shadow:5px 5px 0 var(--fg)}
.board .hd{font-weight:900;font-size:18px;margin-bottom:6px}
.board .big{font-weight:900;font-size:24px;line-height:1.4}
.board .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.board .chips span{background:var(--mk);color:#17233a;font-weight:700;font-size:14px;padding:2px 10px;border-radius:999px}
.board ul,.board ol{margin:4px 0;padding-left:1.4em}
.board dl{margin:0}.board dt{font-weight:900;margin-top:6px}.board dd{margin:0 0 4px;color:var(--sub)}
.board table{border-collapse:collapse;width:100%;font-size:15px}
.board th,.board td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.board td b{display:block}
.src{font-size:12px;color:var(--sub);margin-top:8px}
.quiz .q{font-weight:900}
.quiz details{margin-top:8px;background:var(--bg);border-radius:8px;padding:6px 12px}
.quiz summary{cursor:pointer;font-weight:900;color:var(--accent)}
.say{display:flex;gap:10px;margin:10px 0;align-items:flex-start}
.say img{width:44px;height:44px;border-radius:50%;flex:none;background:var(--paper);border:2px solid var(--line);object-fit:cover}
.say .b{border-radius:12px;padding:8px 12px;max-width:100%}
.say .n{font-size:12px;font-weight:900}
.say.zundamon .b{background:var(--zb)}.say.zundamon .n{color:var(--z)}
.say.metan{flex-direction:row-reverse}.say.metan .b{background:var(--mb)}.say.metan .n{color:var(--m);text-align:right}
.foot{margin-top:40px;font-size:13px;color:var(--sub);border-top:1px solid var(--line);padding-top:14px}
.list a{display:block;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0;text-decoration:none;color:var(--fg)}
.list a b{display:block;font-size:17px}.list a span{font-size:13px;color:var(--sub)}
"""


def e(s):
    return html.escape(str(s))


def scene_html(s):
    t = s.get("type")
    out = []
    head = s.get("head")
    if head:
        out.append(f'<div class="hd">{e(head)}</div>')
    if t == "title":
        out.append('<div class="big">' + "".join(e(x) for x in s.get("lines", [])) + "</div>")
        if s.get("reveal"):
            out.append('<div class="chips">' + "".join(f"<span>{e(x)}</span>" for x in s["reveal"]) + "</div>")
    elif t == "list":
        out.append("<ol>" + "".join(f"<li>{e(x)}</li>" for x in s.get("items", [])) + "</ol>")
    elif t in ("cards", "levels"):
        out.append("<dl>" + "".join(f"<dt>{e(x.get('name', ''))}</dt><dd>{e(x.get('desc', ''))}</dd>"
                                    for x in s.get("items", [])) + "</dl>")
    elif t == "grid":
        cols, rows, cells = s.get("cols", []), s.get("rows", []), s.get("cells", [])
        tb = "<tr><th></th>" + "".join(f"<th>{e(c)}</th>" for c in cols) + "</tr>"
        for r, rn in enumerate(rows):
            tb += f"<tr><th>{e(rn)}</th>"
            for c in range(len(cols)):
                x = cells[r * len(cols) + c] if r * len(cols) + c < len(cells) else {}
                tb += f"<td><b>{e(x.get('tag', ''))}</b>{e(x.get('text', ''))}</td>"
            tb += "</tr>"
        out.append(f"<table>{tb}</table>")
    elif t == "quiz":
        ch = s.get("choices", [])
        out.append(f'<div class="q">{e(s.get("q", ""))}</div><ul>' + "".join(f"<li>{e(c)}</li>" for c in ch) + "</ul>")
        if isinstance(s.get("answer"), int) and s["answer"] < len(ch):
            out.append(f"<details><summary>答えを見る</summary>{e(ch[s['answer']])}</details>")
    else:  # forces など：中身の文字をそのまま
        for k, v in s.items():
            if k in ("type", "head", "src"):
                continue
            if isinstance(v, str):
                out.append(f"<div><b>{e(k)}</b>：{e(v)}</div>")
            elif isinstance(v, dict):
                out.append(f"<div><b>{e(v.get('name', k))}</b>：{e(v.get('desc', ''))}</div>")
    if s.get("src"):
        out.append(f'<div class="src">{e(s["src"])}</div>')
    cls = "board quiz" if t == "quiz" else "board"
    return f'<div class="{cls}">' + "".join(out) + "</div>"


def article(d, rel="."):
    up = d.get("upload") or {}
    title = up.get("title", d.get("title", ""))
    short_title = title.split("｜")[0]
    vid = d.get("video_id")
    lines = [ln for ln in d["lines"] if not ln.get("scene", "").startswith("_")]
    chapters = [ln["chapter"] for ln in lines if ln.get("chapter")]
    body, shown, chap_i = [], set(), 0
    for ln in lines:
        if ln.get("chapter"):
            chap_i += 1
            body.append(f'<h2 id="c{chap_i}">{e(ln["chapter"])}</h2>')
        sc = ln.get("scene")
        if sc and sc not in shown and sc in (d.get("scenes") or {}):
            shown.add(sc)
            body.append(scene_html(d["scenes"][sc]))
        if ln.get("who") and ln.get("text"):
            w = ln["who"]
            body.append(f'<div class="say {w}"><img src="{rel}/assets/{w}.webp" alt="{NAME[w]}">'
                        f'<div class="b"><div class="n">{NAME[w]}</div>{e(ln["text"])}</div></div>')
    toc = ("<nav class=\"toc\"><b>目次</b><ol>" + "".join(f'<li><a href="#c{i + 1}">{e(c)}</a></li>'
                                                       for i, c in enumerate(chapters)) + "</ol></nav>") if chapters else ""
    video = (f'<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{e(vid)}" title="{e(short_title)}" '
             f'loading="lazy" allowfullscreen></iframe></div>') if vid else ""
    srcs = "".join(f"<li>{e(s)}</li>" for s in up.get("sources", []))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(short_title)}｜{CHANNEL}</title>
<meta name="description" content="{e(up.get('summary', ''))}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@500;700;900&display=swap">
<style>{CSS}</style></head><body><div class="wrap">
<header class="top"><a href="{rel}/index.html"><span class="mk">{CHANNEL}</span></a></header>
<span class="tag">{e(d.get('topic', ''))}</span>
<h1>{e(short_title)}</h1>
<p class="lead">{e(up.get('summary', ''))}</p>
{video}{toc}
{''.join(body)}
<div class="foot"><b>出典</b><ul>{srcs}</ul>
この記事は、動画の台本（IPA の資料をもとに作り、別の AI で内容を確かめたもの）をそのまま文字にしたものです。IPA（情報処理推進機構）とは関係ありません。<br>
音声：VOICEVOX:ずんだもん／VOICEVOX:四国めたん　立ち絵：坂本アヒル様<br>
<a href="{CHANNEL_URL}">YouTube チャンネル {CHANNEL}</a></div>
</div></body></html>"""


def index(items):
    groups = {}
    for d in items:
        groups.setdefault(d.get("topic", "そのほか"), []).append(d)
    body = ""
    for topic in sorted(groups):
        body += f"<h2>{e(topic)}</h2><div class=\"list\">"
        for d in groups[topic]:
            up = d.get("upload") or {}
            body += (f'<a href="{e(d["id"])}.html"><b>{e(up.get("title", "").split("｜")[0])}</b>'
                     f'<span>{e(up.get("summary", "")[:80])}…</span></a>')
        body += "</div>"
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{CHANNEL}｜台本で読む</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@500;700;900&display=swap">
<style>{CSS}</style></head><body><div class="wrap">
<header class="top"><span class="mk" style="font-size:24px">{CHANNEL}</span></header>
<p class="lead">応用情報技術者試験・情報処理安全確保支援士試験の解説動画を、台本のまま文字で読めます。</p>
{body}
<div class="foot">IPA（情報処理推進機構）とは関係ありません。<a href="{CHANNEL_URL}">YouTube チャンネル</a></div>
</div></body></html>"""


def faces(out):
    """吹き出しの顔（立ち絵の頭のあたりを丸く切る）。"""
    from PIL import Image
    parts = ROOT / "build" / "thumbparts"
    if not parts.exists():
        sys.path.insert(0, str(ROOT / "scripts"))
        import make_thumb
        make_thumb.make_parts(parts)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for key, who, box in (("zunda", "zundamon", (110, 60, 400, 350)), ("metan", "metan", (165, 20, 405, 260))):
        im = None
        for p in ("body", "ra_base", "la_base", "brow_base", "eye_smile", "mouth_smile"):
            x = Image.open(parts / f"{key}_{p}.webp").convert("RGBA")
            im = x if im is None else Image.alpha_composite(im, x)
        im.crop(box).resize((96, 96), Image.LANCZOS).save(out / "assets" / f"{who}.webp", quality=90)


def main(argv):
    out = ROOT / (argv[0] if argv else "site")
    out.mkdir(parents=True, exist_ok=True)
    faces(out)
    items = []
    if "--preview" in argv:
        items = [json.loads(pathlib.Path(p).read_text(encoding="utf-8")) for p in argv[argv.index("--preview") + 1:]]
    now = datetime.datetime.now(datetime.timezone.utc)
    for f in sorted((ROOT / "published").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        # 予約公開の前は動画が非公開なので、公開の時刻を過ぎた分だけ記事にする
        if d.get("publish_at") and datetime.datetime.fromisoformat(d["publish_at"]) > now:
            continue
        if d.get("format") != "short" and d.get("video_id") and d.get("scenes"):
            items.append(d)
    seen = set()
    items = [d for d in items if not (d["id"] in seen or seen.add(d["id"]))]
    for d in items:
        (out / f"{d['id']}.html").write_text(article(d), encoding="utf-8")
    (out / "index.html").write_text(index(items), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"[info] 記事 {len(items)}本 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
