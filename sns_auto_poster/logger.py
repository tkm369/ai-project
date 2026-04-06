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

def add_post(post_id, platform, content, time_slot, has_affiliate=False, has_image=False, length_category=None, image_style=None, image_content_pattern=None):
    log = load_log()
    jst = pytz.timezone("Asia/Tokyo")
    entry = {
        "id": post_id,
        "platform": platform,
        "timestamp": datetime.now(jst).isoformat(),
        "content": content,
        "time_slot": time_slot,
        "has_affiliate": has_affiliate,
        "has_image": has_image,
        "image_style": image_style,
        "image_content_pattern": image_content_pattern,
        "length_category": length_category,
        "metrics": None,
        "metrics_collected": False
    }
    log.append(entry)
    save_log(log)

def count_posts_today():
    """今日すでに投稿した回数（time_slot単位でカウント、プラットフォーム問わず）"""
    log = load_log()
    jst = pytz.timezone("Asia/Tokyo")
    today = datetime.now(jst).strftime("%Y-%m-%d")
    seen_slots = set()
    for p in log:
        if p.get("timestamp", "").startswith(today):
            key = p.get("time_slot") or p.get("timestamp", "")[:16]
            seen_slots.add(key)
    return len(seen_slots)


def get_time_slot_stats():
    """時間帯別の投稿数と平均エンゲージメント率を返す {slot: {"count": N, "avg_rate": float}}"""
    from collections import defaultdict
    log = load_log()
    slot_data = defaultdict(list)
    for p in log:
        if p.get("metrics_collected") and p.get("metrics") and p.get("platform") == "threads":
            slot = p.get("time_slot")
            rate = p["metrics"].get("engagement_rate", 0)
            if slot:
                slot_data[slot].append(rate)
    return {
        slot: {"count": len(rates), "avg_rate": sum(rates) / len(rates)}
        for slot, rates in slot_data.items() if rates
    }


def get_time_slot_performance():
    """時間帯別の平均エンゲージメント率を返す {slot: avg_rate}（後方互換）"""
    return {slot: s["avg_rate"] for slot, s in get_time_slot_stats().items()}


def get_length_stats():
    """投稿の長さカテゴリ別エンゲージメント率を返す
    Returns: {"short": {"avg_rate": float, "count": int}, "medium": ..., "long": ...}
    """
    log = load_log()
    data = {"short": [], "medium": [], "long": []}
    for p in log:
        if not p.get("metrics_collected") or not p.get("metrics"):
            continue
        if p.get("platform") != "threads":
            continue
        rate = p["metrics"].get("engagement_rate", 0)
        cat = p.get("length_category")
        if cat in data:
            data[cat].append(rate)
    return {
        cat: {"avg_rate": sum(r) / len(r) if r else 0, "count": len(r)}
        for cat, r in data.items()
    }


def get_image_content_stats():
    """画像コンテンツパターン別エンゲージメント率を返す"""
    from image_gen import ALL_CONTENT_PATTERNS
    log = load_log()
    data = {p: [] for p in ALL_CONTENT_PATTERNS}
    for p in log:
        if not p.get("metrics_collected") or not p.get("metrics"):
            continue
        if p.get("platform") != "threads" or not p.get("has_image"):
            continue
        rate = p["metrics"].get("engagement_rate", 0)
        pattern = p.get("image_content_pattern")
        if pattern in data:
            data[pattern].append(rate)
    return {
        pt: {"avg_rate": sum(r) / len(r) if r else 0, "count": len(r)}
        for pt, r in data.items()
    }


def get_image_style_stats():
    """画像スタイル別エンゲージメント率を返す"""
    from image_gen import ALL_STYLES
    log = load_log()
    data = {s: [] for s in ALL_STYLES}
    for p in log:
        if not p.get("metrics_collected") or not p.get("metrics"):
            continue
        if p.get("platform") != "threads" or not p.get("has_image"):
            continue
        rate = p["metrics"].get("engagement_rate", 0)
        style = p.get("image_style")
        if style in data:
            data[style].append(rate)
    return {
        s: {"avg_rate": sum(r) / len(r) if r else 0, "count": len(r)}
        for s, r in data.items()
    }


def get_image_vs_text_stats():
    """画像あり/なし別の平均エンゲージメント率を返す
    Returns: {"image": {"avg_rate": float, "count": int}, "text": {...}}
    """
    log = load_log()
    image_rates, text_rates = [], []
    for p in log:
        if not p.get("metrics_collected") or not p.get("metrics"):
            continue
        if p.get("platform") != "threads":
            continue
        rate = p["metrics"].get("engagement_rate", 0)
        if p.get("has_image"):
            image_rates.append(rate)
        else:
            text_rates.append(rate)
    return {
        "image": {
            "avg_rate": sum(image_rates) / len(image_rates) if image_rates else 0,
            "count": len(image_rates),
        },
        "text": {
            "avg_rate": sum(text_rates) / len(text_rates) if text_rates else 0,
            "count": len(text_rates),
        },
    }


def get_recent_posts_content(n=7):
    """直近N件の投稿内容（本文の最初の80文字）を返す（重複防止用）"""
    log = load_log()
    threads_posts = [p for p in log if p.get("platform") == "threads" and p.get("content")]
    recent = threads_posts[-n:]
    return [p["content"][:80] for p in recent]


def get_total_post_count():
    """累計投稿数を返す（テーマローテーション用）"""
    log = load_log()
    return len([p for p in log if p.get("platform") == "threads"])


def get_top_posts(n=3, has_affiliate=False):
    """エンゲージメント率が高い上位N件を返す（Threads投稿のみ・同じモードの投稿から学習）"""
    log = load_log()
    scored = [
        p for p in log
        if p.get("metrics_collected")
        and p.get("metrics")
        and p.get("platform") == "threads"
        and p.get("has_affiliate", False) == has_affiliate  # アフィリあり/なしを分けて学習
    ]
    scored.sort(key=lambda x: x["metrics"].get("engagement_rate", 0), reverse=True)
    return scored[:n]
