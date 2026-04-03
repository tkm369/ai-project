import time
import requests
import tweepy
from config import (
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
    THREADS_ACCESS_TOKEN, THREADS_USER_ID,
)


def post_to_x(text):
    """Xに投稿する"""
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
        print("  [X] APIキーが未設定のためスキップ")
        return None
    try:
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )
        response = client.create_tweet(text=text)
        tweet_id = str(response.data["id"])
        print(f"  [X] 投稿成功 → https://x.com/i/web/status/{tweet_id}")
        return tweet_id
    except Exception as e:
        err_detail = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_detail += f" | body: {e.response.text[:300]}"
            except Exception:
                pass
        print(f"  [X] 投稿失敗: {err_detail}")
        return None


def post_to_threads(text):
    """Threadsに投稿する"""
    if not all([THREADS_ACCESS_TOKEN, THREADS_USER_ID]):
        print("  [Threads] APIキーが未設定のためスキップ")
        return None
    try:
        # Step1: メディアコンテナ作成
        container_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
        container_res = requests.post(container_url, params={
            "media_type": "TEXT",
            "text": text,
            "access_token": THREADS_ACCESS_TOKEN,
        })
        container_data = container_res.json()
        container_id = container_data.get("id")

        if not container_id:
            print(f"  [Threads] コンテナ作成失敗: {container_data}")
            return False

        # Step2: 公開 (API推奨の待機)
        time.sleep(3)

        publish_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish"
        publish_res = requests.post(publish_url, params={
            "creation_id": container_id,
            "access_token": THREADS_ACCESS_TOKEN,
        })

        if publish_res.status_code == 200:
            post_id = str(publish_res.json().get("id", ""))
            print(f"  [Threads] 投稿成功 (ID: {post_id})")
            return post_id if post_id else None
        else:
            print(f"  [Threads] 公開失敗: {publish_res.text}")
            return None

    except Exception as e:
        print(f"  [Threads] 投稿失敗: {e}")
        return None
