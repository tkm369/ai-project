"""
投稿ログの実績データを収集するスクリプト
GitHub Actionsから毎日実行される
"""
import json
import os
import re
from datetime import datetime, timedelta
import pytz
from logger import load_log, save_log
from analytics import fetch_post_insights


def collect():
    log = load_log()
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst)
    updated = 0

    for entry in log:
        if entry.get("metrics_collected"):
            continue
        if entry.get("platform") != "threads":
            continue

        # 2時間以上経過しているか確認（GitHub Actionsの実行間隔と合わせる）
        try:
            posted_at = datetime.fromisoformat(entry["timestamp"])
            if posted_at.tzinfo is None:
                posted_at = jst.localize(posted_at)
            if now - posted_at < timedelta(hours=2):
                continue
        except Exception:
            continue

        print(f"  収集中: {entry['id']} ({entry['timestamp'][:10]})")
        metrics = fetch_post_insights(entry["id"])
        if metrics:
            entry["metrics"] = metrics
            entry["metrics_collected"] = True
            updated += 1
            print(f"    views={metrics.get('views', 0)}, likes={metrics.get('likes', 0)}, "
                  f"engagement={metrics.get('engagement_rate', 0):.2%}")

    if updated > 0:
        save_log(log)
        print(f"\n{updated}件の実績を更新しました")
    else:
        print("更新対象なし")

    # ハッシュタグ集計
    analyze_hashtags()


def analyze_hashtags():
    """ハッシュタグごとのエンゲージメント率を集計してhashtag_stats.jsonに保存"""
    log = load_log()
    hashtag_data = {}

    for entry in log:
        if not entry.get("metrics_collected"):
            continue
        rate = entry.get("metrics", {}).get("engagement_rate", 0)
        content = entry.get("content", "")
        # 日本語ハッシュタグ対応
        tags = re.findall(r'#[\w\u3041-\u9FFF\u30A1-\u30F6\u4E00-\u9FFF]+', content)
        for tag in tags:
            hashtag_data.setdefault(tag, []).append(rate)

    stats = {}
    for tag, rates in hashtag_data.items():
        if len(rates) >= 2:
            stats[tag] = {
                "avg_rate": sum(rates) / len(rates),
                "count": len(rates),
            }

    # エンゲージ率降順ソート
    sorted_stats = dict(
        sorted(stats.items(), key=lambda x: x[1]["avg_rate"], reverse=True)
    )

    output_path = os.path.join(os.path.dirname(__file__), "hashtag_stats.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_stats, f, ensure_ascii=False, indent=2)

    print(f"\nハッシュタグ分析完了 ({len(sorted_stats)}タグ)")
    top5 = list(sorted_stats.items())[:5]
    if top5:
        print("  トップ5:")
        for tag, v in top5:
            print(f"    {tag}: {v['avg_rate']:.2%} (n={v['count']})")
    return sorted_stats


if __name__ == "__main__":
    collect()
