"""
fetcher.py - Threads のハッシュタグ検索から伸びている投稿を収集してキューに追加
"""

import os
import sys
import json
import time
import logging
import re
import subprocess
from datetime import datetime

import config

logger = logging.getLogger(__name__)

QUEUE_FILE = config.QUEUE_FILE
SEEN_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_ids.json")
HASHTAG_INDEX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hashtag_index.json")


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
#  ハッシュタグローテーション
# ------------------------------------------------------------------ #

def get_next_hashtag() -> str:
    """毎回異なるハッシュタグを順番に返す"""
    hashtags = config.THREADS_HASHTAGS
    if not hashtags:
        return "スピリチュアル"

    index = 0
    if os.path.exists(HASHTAG_INDEX_FILE):
        with open(HASHTAG_INDEX_FILE, "r") as f:
            index = json.load(f).get("index", 0)

    tag = hashtags[index % len(hashtags)]
    with open(HASHTAG_INDEX_FILE, "w") as f:
        json.dump({"index": (index + 1) % len(hashtags)}, f)

    return tag


# ------------------------------------------------------------------ #
#  Threads ハッシュタグページをスクレイピング
# ------------------------------------------------------------------ #

FETCH_TIMEOUT = 90  # ハッシュタグ収集のタイムアウト（秒）
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetcher_worker.py")
PYTHON = sys.executable


def fetch_trending_threads(hashtag: str, limit: int = 10) -> list[dict]:
    """
    Threads のハッシュタグ検索ページから投稿URLを収集する。
    子プロセスで実行してタイムアウト時はプロセスごと強制終了する。
    戻り値: [{"url": ..., "id": ...}]
    """
    logger.info(f"Threads検索: #{hashtag}")
    try:
        result = subprocess.run(
            [PYTHON, WORKER, hashtag],
            timeout=FETCH_TIMEOUT,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip()
        if output.startswith("ERROR:"):
            logger.error(f"fetcher_worker失敗: {output}")
            return []
        posts = json.loads(output)[:limit]
        logger.info(f"#{hashtag} から {len(posts)} 件の投稿URLを収集")
        return posts
    except subprocess.TimeoutExpired:
        logger.error(f"Threads収集が{FETCH_TIMEOUT}秒でタイムアウト (#{hashtag})")
        return []
    except Exception as e:
        logger.error(f"Threads収集エラー: {e}")
        return []


# ------------------------------------------------------------------ #
#  メイン: 新着をキューに追加
# ------------------------------------------------------------------ #

def fetch_and_enqueue() -> int:
    """
    Threads のハッシュタグ検索から伸びている投稿を収集してキューに追加。
    戻り値: 新規追加件数
    """
    seen  = load_seen()
    queue = load_queue()

    hashtag = get_next_hashtag()
    posts = fetch_trending_threads(hashtag, limit=config.THREADS_FETCH_LIMIT)

    added = 0
    for post in posts:
        post_id = post["id"]
        if post_id in seen:
            continue

        queue.append({
            "url":              post["url"],
            "caption_override": "",
            "added_at":         datetime.now().isoformat(),
            "status":           "pending",
        })
        seen.add(post_id)
        added += 1
        logger.info(f"キューに追加: {post['url']}")

    if added > 0:
        save_queue(queue)
        save_seen(seen)
        logger.info(f"合計 {added} 件を追加しました (#{hashtag})")
    else:
        logger.info(f"新着投稿なし (#{hashtag})")

    return added


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    n = fetch_and_enqueue()
    print(f"追加: {n} 件")
