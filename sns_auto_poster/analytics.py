import requests
from config import THREADS_ACCESS_TOKEN

def fetch_post_insights(post_id):
    """Threadsの投稿インサイトを取得（threads_read_engagement権限が必要）"""
    url = f"https://graph.threads.net/v1.0/{post_id}/insights"
    params = {
        "metric": "views,likes,replies,reposts,quotes",
        "access_token": THREADS_ACCESS_TOKEN,
    }
    try:
        res = requests.get(url, params=params)
        data = res.json()
        if "data" not in data:
            print(f"  インサイト取得失敗: {data.get('error', {}).get('message', data)}")
            return None
        metrics = {}
        for item in data["data"]:
            val = item.get("total_value", item.get("values", [{}])[0].get("value", 0))
            metrics[item["name"]] = val
        views = max(metrics.get("views", 1), 1)
        interactions = metrics.get("likes", 0) + metrics.get("replies", 0) + metrics.get("reposts", 0)
        metrics["engagement_rate"] = round(interactions / views, 4)
        return metrics
    except Exception as e:
        print(f"  インサイト取得エラー: {e}")
        return None
