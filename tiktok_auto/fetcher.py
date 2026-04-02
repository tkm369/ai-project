"""
fetcher.py - X/Threads の新着投稿を自動取得してキューに追加

環境変数 (GitHub Secrets) から認証情報を読み取る:
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
  THREADS_ACCESS_TOKEN, THREADS_USER_ID
"""

import os
import json
import logging
import requests

import config

logger = logging.getLogger(__name__)

QUEUE_FILE = config.QUEUE_FILE
SEEN_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_ids.json")


# ------------------------------------------------------------------ #
#  既処理ID管理
# ------------------------------------------------------------------ #

def load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r") as f:
        return set(json.load(f))


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def load_queue() -> list:
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ #
#  X (Twitter) 新着取得
# ------------------------------------------------------------------ #

def fetch_x_posts(max_results: int = 5) -> list[dict]:
    """最新のX投稿URLリストを返す"""
    try:
        import tweepy

        api_key        = os.environ.get("X_API_KEY")
        api_secret     = os.environ.get("X_API_SECRET")
        access_token   = os.environ.get("X_ACCESS_TOKEN")
        access_secret  = os.environ.get("X_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_secret]):
            logger.warning("X API の認証情報が不足しています")
            return []

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )

        # 自分のuser_idを取得
        me = client.get_me()
        user_id = me.data.id

        tweets = client.get_users_tweets(
            id=user_id,
            max_results=max_results,
            tweet_fields=["id", "text"],
            exclude=["retweets", "replies"],
        )

        if not tweets.data:
            return []

        results = []
        for tweet in tweets.data:
            url = f"https://x.com/{config.X_USERNAME}/status/{tweet.id}"
            results.append({"url": url, "id": str(tweet.id), "platform": "x"})
        return results

    except Exception as e:
        logger.error(f"X投稿の取得に失敗: {e}")
        return []


# ------------------------------------------------------------------ #
#  Threads 新着取得
# ------------------------------------------------------------------ #

def fetch_threads_posts(limit: int = 5) -> list[dict]:
    """最新のThreads投稿URLリストを返す"""
    try:
        access_token = os.environ.get("THREADS_ACCESS_TOKEN")
        user_id      = os.environ.get("THREADS_USER_ID")

        if not access_token or not user_id:
            logger.warning("Threads API の認証情報が不足しています")
            return []

        resp = requests.get(
            f"https://graph.threads.net/v1.0/{user_id}/threads",
            params={
                "fields":       "id,permalink,media_type,text",
                "limit":        limit,
                "access_token": access_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        results = []
        for post in data:
            if post.get("permalink"):
                results.append({
                    "url":      post["permalink"],
                    "id":       post["id"],
                    "platform": "threads",
                })
        return results

    except Exception as e:
        logger.error(f"Threads投稿の取得に失敗: {e}")
        return []


# ------------------------------------------------------------------ #
#  メイン: 新着をキューに追加
# ------------------------------------------------------------------ #

def fetch_and_enqueue() -> int:
    """
    X/Threads の新着投稿を取得してキューに追加。
    戻り値: 新規追加件数
    """
    seen  = load_seen()
    queue = load_queue()

    all_posts = fetch_x_posts() + fetch_threads_posts()
    added = 0

    for post in all_posts:
        post_id = post["id"]
        if post_id in seen:
            continue

        queue.append({
            "url":              post["url"],
            "caption_override": "",
            "added_at":         __import__("datetime").datetime.now().isoformat(),
            "status":           "pending",
        })
        seen.add(post_id)
        added += 1
        logger.info(f"キューに追加: [{post['platform']}] {post['url']}")

    if added > 0:
        save_queue(queue)
        save_seen(seen)
        logger.info(f"合計 {added} 件を追加しました")
    else:
        logger.info("新着投稿なし")

    return added


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    n = fetch_and_enqueue()
    print(f"追加: {n} 件")
