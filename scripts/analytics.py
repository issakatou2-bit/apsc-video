#!/usr/bin/env python3
"""チャンネルの数字（再生・見られた長さ・どこから来たか・登録）をまとめて表示する。

なぜ要るのか:
  2026-10-09 本人「今アナリティクスどう？」。Studio を開かなくても、動画ごとの数字と、
  題の B 型・C 型の比べ（10/8 から日ごとに交互）を見られるようにする。
  注意：YouTube Analytics の数字は2〜3日遅れて入る。再生回数（Data API）はほぼ今の値。

使い方:
  python scripts/analytics.py [開始日 2026-10-07]
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def main(start="2026-10-07"):
    from googleapiclient.discovery import build
    import upload_youtube
    cred = upload_youtube.credentials()
    yt = build("youtube", "v3", credentials=cred)
    ya = build("youtubeAnalytics", "v2", credentials=cred)
    end = datetime.date.today().isoformat()
    ch = yt.channels().list(part="statistics,snippet", mine=True).execute()["items"][0]
    print(f"# {ch['snippet']['title']}  登録 {ch['statistics'].get('subscriberCount')}・再生 {ch['statistics'].get('viewCount')}・動画 {ch['statistics'].get('videoCount')}")
    # 公開済みの動画（アップロードの一覧）
    up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=50, pageToken=tok).execute()
        ids += [x["contentDetails"]["videoId"] for x in r["items"]]
        tok = r.get("nextPageToken")
        if not tok:
            break
    vids = []
    for i in range(0, len(ids), 50):
        vids += yt.videos().list(part="snippet,statistics,contentDetails,status", id=",".join(ids[i:i + 50])).execute()["items"]
    pub = [v for v in vids if v["status"]["privacyStatus"] == "public"]
    print(f"公開中 {len(pub)}本・予約/非公開 {len(vids) - len(pub)}本")
    # 動画ごとの Analytics（遅れあり）
    rows = {}
    try:
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="video",
                               metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained",
                               sort="-views", maxResults=200).execute()
        rows = {x[0]: x[1:] for x in r.get("rows", [])}
    except Exception as e:
        print("[warn] Analytics:", e)
    print("\n| 公開 | 種類 | 再生 | いいね | 平均視聴(秒) | 平均視聴率% | 登録+ | 題 |")
    print("|---|---|---|---|---|---|---|---|")
    for v in sorted(pub, key=lambda v: v["snippet"]["publishedAt"]):
        dur = v["contentDetails"]["duration"]
        kind = "ショート" if ("M" not in dur.replace("PT", "") or dur in ("PT1M",)) else "長編"
        a = rows.get(v["id"], [None] * 5)
        print(f"| {v['snippet']['publishedAt'][5:16]} | {kind} | {v['statistics'].get('viewCount', 0)} | "
              f"{v['statistics'].get('likeCount', 0)} | {a[2]} | {a[3] and round(a[3], 1)} | {a[4]} | {v['snippet']['title'][:40]} |")
    for dim, name in (("insightTrafficSourceType", "どこから来たか"), ("day", "日ごと")):
        try:
            r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions=dim,
                                   metrics="views,estimatedMinutesWatched", sort=dim if dim == "day" else "-views").execute()
            print(f"\n## {name}")
            for x in r.get("rows", []):
                print(" ", x)
        except Exception as e:
            print("[warn]", name, e)


if __name__ == "__main__":
    main(*sys.argv[1:])
