"""
投稿ログの実績データを収集するスクリプト
GitHub Actionsから毎日実行される
"""
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

        # 24時間以上経過しているか確認
        try:
            posted_at = datetime.fromisoformat(entry["timestamp"])
            if posted_at.tzinfo is None:
                posted_at = jst.localize(posted_at)
            if now - posted_at < timedelta(hours=24):
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


if __name__ == "__main__":
    collect()
