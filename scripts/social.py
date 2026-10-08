#!/usr/bin/env python3
"""ショートを TikTok・Instagram（リール）・X に、Buffer で予約投稿する。

なぜ要るのか:
  2026-10-08 本人「バッファーアカウント２個目作るのも手だな？TikTokとInstagram、Xの３つってちょうどバッファーの１個で足りる」。
  コレスポ（C:/Users/issak/Desktop/pwa-mvp）の Buffer の使い方を写した（コレスポ側のファイルは変えない）：
  動画は GitHub のリリースに置いて URL を渡す、投稿の前に台帳へ「予約した」を書いて二重投稿を防ぐ。

動くのは、Secrets に BUFFER_API_KEY があるときだけ（無ければ何もしない）。
どの媒体に出すかは、Buffer につないだ先（channels）をそのまま使う（tiktok・instagram・twitter）。
投稿の時刻は YouTube の公開と同じ（customScheduled、dueAt＝publish_at）。

使い方:
  publish_queue.py が、ショートを YouTube に予約したあとに schedule(d, mp4) を呼ぶ。
  python scripts/social.py --check        # キーがあれば、つないだ先の一覧を出すだけ（投稿しない）
"""
import datetime
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "issakatou2-bit/apsc-video")
LEDGER = ROOT / "data" / "social_ledger.json"
SERVICES = ("tiktok", "instagram", "twitter")
CHANNEL_URL = "https://www.youtube.com/channel/UCFPlgxr-u00RDIXYtQfKA2g"


def enabled():
    return bool(os.environ.get("BUFFER_API_KEY"))


def graphql(query, variables=None):
    token = os.environ["BUFFER_API_KEY"]
    req = urllib.request.Request("https://api.buffer.com", data=json.dumps(
        {"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "apsc-video/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Buffer HTTP {e.code}") from None  # 鍵を出さない
    if res.get("errors"):
        raise RuntimeError("; ".join(x.get("message", "error") for x in res["errors"]).replace(token, "[redacted]"))
    return res["data"]


def channels():
    """Buffer につないだ先：{service: channelId}"""
    out = {}
    for org in graphql("{ account { organizations { id } } }")["account"]["organizations"]:
        for c in graphql("{ channels(input: { organizationId: " + json.dumps(org["id"]) + " }) { id name service } }")["channels"]:
            if c["service"] in SERVICES:
                out.setdefault(c["service"], c["id"])
    return out


def github(path, method="GET", body=None, data=None, ctype="application/json", base="https://api.github.com"):
    req = urllib.request.Request(base + path, method=method,
                                 data=data if data is not None else (json.dumps(body).encode() if body else None),
                                 headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Content-Type": ctype,
                                          "Accept": "application/vnd.github+json", "User-Agent": "apsc-video/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def host(mp4, d):
    """動画を GitHub のリリース（日ごと）に置いて、ダウンロードの URL を返す。"""
    day = d["publish_at"][:10]
    tag = f"social-{day}"
    try:
        rel = github(f"/repos/{REPO}/releases/tags/{tag}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        rel = github(f"/repos/{REPO}/releases", "POST", {
            "tag_name": tag, "target_commitish": "main", "name": f"{day} ショート（SNS 用）", "make_latest": "false",
            "body": "めたん先生のIT試験ゼミのショート。TikTok・Instagram・X への予約投稿（Buffer）に使う動画です。"})
    name = f"{d['id']}.mp4"
    for a in rel.get("assets", []):
        if a["name"] == name:
            return a["browser_download_url"]
    a = github(f"/repos/{REPO}/releases/{rel['id']}/assets?name={name}", "POST", data=pathlib.Path(mp4).read_bytes(),
               ctype="video/mp4", base="https://uploads.github.com")
    return a["browser_download_url"]


def text_for(d, service):
    up = d["upload"]
    head = up.get("title_b") or up["title"]
    head = head.split("｜")[0]
    tags = "#応用情報技術者試験 #応用情報 #資格勉強 #ずんだもん #四国めたん"
    if service == "twitter":  # X は文字数が厳しい
        return f"{head}\n解説はYouTubeで {CHANNEL_URL}\n#応用情報 #資格勉強"
    return f"{head}\n\n{up.get('summary', '')}\n\nくわしい解説はYouTube「めたん先生のIT試験ゼミ」で。\n{tags}"


def schedule(d, mp4):
    """ショート1本を、つないだ先それぞれに YouTube の公開と同じ時刻で予約する。失敗しても YouTube の投稿は止めない。"""
    if not enabled() or d.get("format") != "short":
        return
    led = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    chans = channels()
    if not chans:
        print("[info] Buffer につないだ先がまだ無い")
        return
    url = None
    for service, cid in chans.items():
        key = f"{d['id']}:{service}"
        if key in led:
            continue
        url = url or host(mp4, d)
        payload = {"channelId": cid, "text": text_for(d, service), "schedulingType": "automatic",
                   "mode": "customScheduled", "dueAt": d["publish_at"],
                   "assets": [{"video": {"url": url, "metadata": {"thumbnailOffset": 1500}}}],
                   "needsApproval": False, "aiAssisted": True}
        if service == "instagram":
            payload["metadata"] = {"instagram": {"type": "reel", "shouldShareToFeed": True, "isAiGenerated": True}}
        elif service == "tiktok":
            payload["metadata"] = {"tiktok": {"isAiGenerated": True}}
        led[key] = {"state": "reserved", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                    "due": d["publish_at"], "sha256": hashlib.sha256(pathlib.Path(mp4).read_bytes()).hexdigest()}
        LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # 投稿の前に書く
        r = graphql("mutation($input: CreatePostInput!) { createPost(input:$input) { __typename "
                    "... on PostActionSuccess { post { id status } } ... on MutationError { message } } }",
                    {"input": payload})["createPost"]
        if r.get("__typename") != "PostActionSuccess":
            led[key] = {**led[key], "state": "rejected", "message": r.get("message", "")}
            print(f"[warn] Buffer が断った（{service}）: {r.get('message', '')}")
        else:
            led[key] = {**led[key], "state": r["post"]["status"], "post_id": r["post"]["id"]}
            print(f"[info] {service} に予約した（{d['publish_at']}）")
        LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--check" in sys.argv:
        if not enabled():
            print("[info] BUFFER_API_KEY が無い")
        else:
            print(json.dumps(channels(), ensure_ascii=False, indent=1))
