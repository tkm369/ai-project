"""
競合アカウントの投稿を取得し、高エンゲージ投稿をreference_posts.jsonに自動追加する
"""
import json
import os
import time
import requests
from urllib.parse import quote
from config import THREADS_ACCESS_TOKEN

# ─── 監視する競合アカウント ────────────────────────────────
COMPETITOR_USERNAMES = [
    "lilia_stones7",
    "shirowa_shizu",
    "tsukuyomi_rei.official",
    "hikiyose_sniper",
    "twinray_enmusubi",
]

POSTS_PER_USER = 15       # 1アカウントから取得する最新投稿数
MIN_LIKE_COUNT = 5        # 採用するいいね数の最低ライン（取得できた場合）
MAX_REFERENCE_POSTS = 50  # reference_posts.jsonの最大保持件数
MIN_TEXT_LENGTH = 30      # 短すぎる投稿は除外

BASE_URL = "https://graph.threads.net/v1.0"


def _get(url, params, retries=2):
    for i in range(retries + 1):
        try:
            res = requests.get(url, params=params, timeout=15)
            return res.json()
        except Exception as e:
            if i < retries:
                time.sleep(3)
            else:
                print(f"    リクエスト失敗: {e}")
                return {}


def get_user_id(username):
    """usernameからThreads ユーザーIDを取得"""
    # 方法①: usernameを直接パスに使う
    data = _get(f"{BASE_URL}/{quote(username)}", {
        "fields": "id,username",
        "access_token": THREADS_ACCESS_TOKEN,
    })
    if data.get("id"):
        return data["id"]

    # 方法②: typeパラメータで検索
    data = _get(f"{BASE_URL}/", {
        "type": "username",
        "id": username,
        "fields": "id",
        "access_token": THREADS_ACCESS_TOKEN,
    })
    if data.get("id"):
        return data["id"]

    print(f"    ユーザーID取得失敗: @{username} → {data.get('error', {}).get('message', '')}")
    return None


def get_user_posts(user_id, limit=15):
    """ユーザーの最新投稿を取得（like_countを含む）"""
    data = _get(f"{BASE_URL}/{user_id}/threads", {
        "fields": "id,text,timestamp,like_count",
        "limit": limit,
        "access_token": THREADS_ACCESS_TOKEN,
    })
    return data.get("data", [])


def fetch_all_competitor_posts():
    """全競合アカウントの投稿を収集"""
    all_posts = []

    for username in COMPETITOR_USERNAMES:
        print(f"  @{username} を取得中...")
        user_id = get_user_id(username)
        if not user_id:
            continue

        posts = get_user_posts(user_id, limit=POSTS_PER_USER)
        count = 0
        for post in posts:
            text = (post.get("text") or "").strip()
            if len(text) < MIN_TEXT_LENGTH:
                continue
            # ハッシュタグのみの行を除いた本文チェック
            body_lines = [l for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
            if not body_lines:
                continue
            all_posts.append({
                "username": username,
                "text": text,
                "like_count": post.get("like_count", 0) or 0,
                "timestamp": post.get("timestamp", ""),
            })
            count += 1

        print(f"    → {count}件取得")
        time.sleep(1.5)  # レート制限対策

    return all_posts


def select_best_posts(posts):
    """いいね数でソートし上位を選定"""
    # like_countが取れている投稿と取れていない投稿を分ける
    with_likes = [p for p in posts if p["like_count"] >= MIN_LIKE_COUNT]
    without_likes = [p for p in posts if p["like_count"] < MIN_LIKE_COUNT]

    if with_likes:
        # いいね数で降順ソート
        with_likes.sort(key=lambda x: x["like_count"], reverse=True)
        selected = with_likes[:30]
        print(f"  いいね{MIN_LIKE_COUNT}以上: {len(with_likes)}件 → 上位{len(selected)}件を採用")
    else:
        # like_countが取れない場合は全件採用（アカウント自体が良質なので）
        selected = posts
        print(f"  like_count未取得のため全{len(selected)}件を採用")

    return [p["text"] for p in selected]


def update_reference_posts():
    """競合投稿をreference_posts.jsonに自動マージ"""
    print("\n=== 競合アカウント投稿収集 ===")
    posts = fetch_all_competitor_posts()

    if not posts:
        print("投稿を取得できませんでした")
        return

    new_texts = select_best_posts(posts)

    # 既存のreference_posts.jsonを読み込み
    ref_path = os.path.join(os.path.dirname(__file__), "reference_posts.json")
    existing = []
    if os.path.exists(ref_path):
        try:
            with open(ref_path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    # マージ（重複排除・競合投稿を先頭に配置して学習優先度を上げる）
    existing_set = set(existing)
    added = [t for t in new_texts if t not in existing_set]
    combined = added + existing  # 新規を先頭に
    combined = combined[:MAX_REFERENCE_POSTS]  # 最大件数に制限

    with open(ref_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 新規追加: {len(added)}件 / 合計: {len(combined)}件 → reference_posts.json 更新完了")
    return combined


if __name__ == "__main__":
    update_reference_posts()
