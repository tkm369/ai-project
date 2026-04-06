"""
競合アカウントの自動管理モジュール
- 高エンゲージ投稿をreference_posts.jsonに自動追加
- アカウントごとのエンゲージ推移を記録
- エンゲージが低下したアカウントを自動削除
- Geminiウェブ検索で新しいバズアカウントを自動発見
"""
import json
import os
import time
import re
import requests
from datetime import datetime, timezone
from urllib.parse import quote
from config import THREADS_ACCESS_TOKEN, GEMINI_API_KEY

# ─── 設定 ────────────────────────────────────────────────
INITIAL_USERNAMES = [
    "lilia_stones7",
    "shirowa_shizu",
    "tsukuyomi_rei.official",
    "hikiyose_sniper",
    "twinray_enmusubi",
]

POSTS_PER_USER       = 15    # 1アカウントから取得する最新投稿数
MIN_LIKE_TO_ADD      = 3     # 新規アカウント追加に必要な平均いいね数
MIN_LIKE_REFERENCE   = 5     # reference_postsに採用するいいね数
MAX_REFERENCE_POSTS  = 60    # reference_posts.jsonの最大保持件数
MIN_TEXT_LENGTH      = 30    # 短すぎる投稿は除外
DECLINE_THRESHOLD    = 0.4   # 直近avg ÷ ピークavg がこの値未満 → 削除候補
DECLINE_STRIKES      = 2     # この回数連続で低下したら削除
MAX_ACCOUNTS         = 20    # 監視アカウントの上限
SEARCH_KEYWORDS      = ["復縁 Threads バズ", "占い スピリチュアル Threads フォロワー増", "引き寄せ 恋愛 Threads 人気アカウント"]

STATS_PATH = os.path.join(os.path.dirname(__file__), "account_stats.json")
REF_PATH   = os.path.join(os.path.dirname(__file__), "reference_posts.json")
BASE_URL   = "https://graph.threads.net/v1.0"


# ─── account_stats.json 管理 ─────────────────────────────
def load_stats():
    if os.path.exists(STATS_PATH):
        try:
            with open(STATS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # 初回: 初期アカウントを登録
    stats = {"accounts": {}}
    for u in INITIAL_USERNAMES:
        stats["accounts"][u] = _new_account_entry("manual")
    save_stats(stats)
    return stats


def save_stats(stats):
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def _new_account_entry(source="auto_discovered"):
    return {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "checks": [],        # {"date": ..., "avg_likes": ..., "post_count": ...}
        "decline_strikes": 0,
        "status": "active",  # active / declining / removed
    }


# ─── Threads API ─────────────────────────────────────────
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
    data = _get(f"{BASE_URL}/{quote(username)}", {
        "fields": "id,username",
        "access_token": THREADS_ACCESS_TOKEN,
    })
    if data.get("id"):
        return data["id"]
    data = _get(f"{BASE_URL}/", {
        "type": "username", "id": username,
        "fields": "id",
        "access_token": THREADS_ACCESS_TOKEN,
    })
    if data.get("id"):
        return data["id"]
    print(f"    ユーザーID取得失敗: @{username}")
    return None


def get_user_posts(user_id, limit=15):
    data = _get(f"{BASE_URL}/{user_id}/threads", {
        "fields": "id,text,timestamp,like_count",
        "limit": limit,
        "access_token": THREADS_ACCESS_TOKEN,
    })
    return data.get("data", [])


def fetch_account_data(username):
    """アカウントの投稿を取得して統計を返す"""
    user_id = get_user_id(username)
    if not user_id:
        return None, []

    posts = get_user_posts(user_id, limit=POSTS_PER_USER)
    valid_posts = []
    for post in posts:
        text = (post.get("text") or "").strip()
        if len(text) < MIN_TEXT_LENGTH:
            continue
        body_lines = [l for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
        if not body_lines:
            continue
        valid_posts.append({
            "text": text,
            "like_count": post.get("like_count", 0) or 0,
        })

    time.sleep(1.5)
    return user_id, valid_posts


# ─── エンゲージ推移チェック・自動削除 ────────────────────
def update_account_stats(stats):
    """各アカウントのエンゲージ推移を記録し、低下したものを削除"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    removed = []

    for username, entry in list(stats["accounts"].items()):
        if entry["status"] == "removed":
            continue

        print(f"  チェック中: @{username}")
        _, posts = fetch_account_data(username)

        if not posts:
            print(f"    投稿取得失敗 → スキップ")
            continue

        avg_likes = sum(p["like_count"] for p in posts) / len(posts)
        entry["checks"].append({
            "date": today,
            "avg_likes": round(avg_likes, 2),
            "post_count": len(posts),
        })

        # 直近2回分のみで判断（メモリ節約のため古いチェックは10件に制限）
        entry["checks"] = entry["checks"][-10:]

        # エンゲージ低下判定
        checks = entry["checks"]
        if len(checks) >= 2:
            peak_likes = max(c["avg_likes"] for c in checks)
            latest_likes = checks[-1]["avg_likes"]
            if peak_likes > 0 and latest_likes / peak_likes < DECLINE_THRESHOLD:
                entry["decline_strikes"] += 1
                print(f"    ⚠️  エンゲージ低下検知 (ピーク:{peak_likes:.1f} → 直近:{latest_likes:.1f}) strikes={entry['decline_strikes']}")
                if entry["decline_strikes"] >= DECLINE_STRIKES:
                    entry["status"] = "removed"
                    removed.append(username)
                    print(f"    ❌ @{username} を監視リストから削除")
            else:
                entry["decline_strikes"] = 0  # 回復したらリセット
                entry["status"] = "active"

        print(f"    avg_likes={avg_likes:.1f} / {len(posts)}件")

    if removed:
        print(f"\n削除したアカウント: {removed}")
    return removed


# ─── Geminiによる新規アカウント自動発見 ──────────────────
def discover_new_accounts(existing_usernames):
    """GeminiのWeb検索で新しいバズアカウントを発見"""
    if not GEMINI_API_KEY:
        return []

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        keyword = SEARCH_KEYWORDS[datetime.now().day % len(SEARCH_KEYWORDS)]

        prompt = f"""{keyword} で検索して、Threadsで復縁・占い・スピリチュアル・引き寄せジャンルで最近バズっているアカウントのusernameを最大10個リストアップしてください。

条件:
- Threads（threads.net）のアカウントのみ
- @は除いてusernameだけ記載
- 1行1アカウント形式で返す
- 説明不要、usernameのリストのみ返す"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text or ""
        # usernameっぽい文字列を抽出（英数字・アンダースコア・ドット）
        candidates = re.findall(r'[@]?([a-zA-Z0-9_.]{3,30})', text)
        # 重複・既存・短すぎるものを除外
        new_ones = [
            u for u in dict.fromkeys(candidates)  # 重複除去
            if u not in existing_usernames
            and len(u) >= 4
            and not u.isdigit()
        ]
        print(f"  Gemini発見候補: {new_ones[:10]}")
        return new_ones[:10]

    except Exception as e:
        print(f"  Gemini検索失敗: {e}")
        return []


def validate_and_add_accounts(stats, candidates):
    """候補アカウントを検証して追加"""
    existing = set(stats["accounts"].keys())
    active_count = sum(1 for e in stats["accounts"].values() if e["status"] == "active")
    added = []

    for username in candidates:
        if username in existing:
            continue
        if active_count >= MAX_ACCOUNTS:
            print(f"  上限({MAX_ACCOUNTS}件)に達しているためスキップ")
            break

        print(f"  検証中: @{username}")
        _, posts = fetch_account_data(username)
        if not posts:
            continue

        avg_likes = sum(p["like_count"] for p in posts) / len(posts)
        if avg_likes >= MIN_LIKE_TO_ADD:
            stats["accounts"][username] = _new_account_entry("auto_discovered")
            existing.add(username)
            active_count += 1
            added.append(username)
            print(f"    ✅ 追加: @{username} (avg_likes={avg_likes:.1f})")
        else:
            print(f"    ❌ スキップ: @{username} (avg_likes={avg_likes:.1f} < {MIN_LIKE_TO_ADD})")

    return added


# ─── reference_posts.json 更新 ────────────────────────────
def update_reference_posts(stats):
    """アクティブなアカウントの高エンゲージ投稿をreference_posts.jsonに反映"""
    all_posts = []
    active_accounts = [u for u, e in stats["accounts"].items() if e["status"] == "active"]

    print(f"\n--- 参考投稿収集 ({len(active_accounts)}アカウント) ---")
    for username in active_accounts:
        _, posts = fetch_account_data(username)
        for p in posts:
            all_posts.append({"username": username, **p})

    # いいね数でフィルタ・ソート
    with_likes = sorted(
        [p for p in all_posts if p["like_count"] >= MIN_LIKE_REFERENCE],
        key=lambda x: x["like_count"], reverse=True
    )
    selected_texts = [p["text"] for p in with_likes[:40]]

    # like_countが取れない場合は全件
    if not selected_texts:
        selected_texts = [p["text"] for p in all_posts]

    # 既存とマージ
    existing = []
    if os.path.exists(REF_PATH):
        try:
            with open(REF_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing_set = set(existing)
    added = [t for t in selected_texts if t not in existing_set]
    combined = added + existing
    combined = combined[:MAX_REFERENCE_POSTS]

    with open(REF_PATH, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"  参考投稿: 新規+{len(added)}件 / 合計{len(combined)}件")


# ─── メイン ──────────────────────────────────────────────
def run():
    print("\n===== 競合アカウント自動管理 =====")
    stats = load_stats()
    active = [u for u, e in stats["accounts"].items() if e["status"] == "active"]
    print(f"監視中アカウント: {len(active)}件")

    # 1. エンゲージ推移チェック・自動削除
    print("\n--- エンゲージチェック ---")
    update_account_stats(stats)

    # 2. Geminiで新規アカウント発見
    print("\n--- 新規アカウント探索 ---")
    existing_names = set(stats["accounts"].keys())
    candidates = discover_new_accounts(existing_names)
    if candidates:
        added = validate_and_add_accounts(stats, candidates)
        if added:
            print(f"新規追加: {added}")

    # 3. 参考投稿を更新
    update_reference_posts(stats)

    # 4. 統計を保存
    save_stats(stats)

    # サマリー表示
    active_after = [u for u, e in stats["accounts"].items() if e["status"] == "active"]
    removed_all  = [u for u, e in stats["accounts"].items() if e["status"] == "removed"]
    print(f"\n✅ 完了 | アクティブ: {len(active_after)}件 | 累計削除: {len(removed_all)}件")


if __name__ == "__main__":
    run()
