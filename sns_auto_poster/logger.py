import json
import os
from datetime import datetime
import pytz

LOG_FILE = os.path.join(os.path.dirname(__file__), "posts_log.json")
MAX_ENTRIES = 90  # 約30日分

def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def save_log(log):
    # 古いエントリを削除して最大件数を維持
    log = log[-MAX_ENTRIES:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def add_post(post_id, platform, content, time_slot):
    log = load_log()
    jst = pytz.timezone("Asia/Tokyo")
    entry = {
        "id": post_id,
        "platform": platform,
        "timestamp": datetime.now(jst).isoformat(),
        "content": content,
        "time_slot": time_slot,
        "metrics": None,
        "metrics_collected": False
    }
    log.append(entry)
    save_log(log)

def get_top_posts(n=3):
    """エンゲージメント率が高い上位N件を返す（Threads投稿のみ）"""
    log = load_log()
    scored = [
        p for p in log
        if p.get("metrics_collected") and p.get("metrics") and p.get("platform") == "threads"
    ]
    scored.sort(key=lambda x: x["metrics"].get("engagement_rate", 0), reverse=True)
    return scored[:n]
