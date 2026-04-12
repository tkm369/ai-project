import sys
import json
import os
import random
from datetime import datetime
import pytz

from generator import get_best_post, get_time_theme
from poster import post_to_x, post_to_threads
from logger import add_post, count_posts_today, get_time_slot_stats, get_image_vs_text_stats, get_length_stats, get_image_style_stats, get_image_content_stats, get_post_type_stats, get_pure_image_style_stats
from config import AFFILIATE_LINK
from discord_notifier import notify_post_success, notify_post_skip, notify_quota_exceeded, notify_error

MAX_POSTS_PER_DAY = 6  # 上限（実際の当日投稿数は3〜6でランダム）


def get_today_post_limit():
    """当日の投稿上限を3〜6のランダムで決定（日付シードで1日固定）"""
    jst = pytz.timezone("Asia/Tokyo")
    today_seed = int(datetime.now(jst).strftime("%Y%m%d"))
    rng = random.Random(today_seed)
    limit = rng.randint(3, 6)
    return limit
MIN_DATA_POINTS = 5
SCORE_THRESHOLD = 50   # これ未満のスコアは投稿スキップ
AB_MIN_SAMPLES = 5     # 画像/テキスト各タイプのA/B判定に必要な最低サンプル数

PENDING_POST_FILE = os.path.join(os.path.dirname(__file__), "pending_post.json")
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "generated_images")


MIN_POST_INTERVAL_HOURS = 3  # 最低投稿間隔（時間）- スパム判定回避

def _get_last_post_hours_ago() -> float:
    """直近の投稿から何時間経過したか返す（投稿なしの場合は999）"""
    from logger import load_log
    import pytz
    log = load_log()
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst)
    threads_posts = [p for p in log if p.get("platform") == "threads" and p.get("timestamp")]
    if not threads_posts:
        return 999
    try:
        last = max(threads_posts, key=lambda p: p["timestamp"])
        last_time = datetime.fromisoformat(last["timestamp"])
        if last_time.tzinfo is None:
            last_time = jst.localize(last_time)
        diff = (now - last_time).total_seconds() / 3600
        return diff
    except Exception:
        return 999


def should_post_now(time_slot):
    """今この時間帯に投稿すべきか判断する（PDCAベース）"""
    # 直近投稿から最低3時間経過していなければスキップ（スパム判定回避）
    hours_ago = _get_last_post_hours_ago()
    if hours_ago < MIN_POST_INTERVAL_HOURS:
        return False, f"直近の投稿から{hours_ago:.1f}時間しか経過していません（最低{MIN_POST_INTERVAL_HOURS}時間必要）"

    posts_today = count_posts_today()
    today_limit = get_today_post_limit()
    if posts_today >= today_limit:
        return False, f"本日 {posts_today}/{today_limit} 回投稿済み（上限到達）"

    stats = get_time_slot_stats()
    slot_stat = stats.get(time_slot)

    # データ不足 → 探索フェーズ（必ず投稿してデータを集める）
    if not slot_stat or slot_stat["count"] < MIN_DATA_POINTS:
        count = slot_stat["count"] if slot_stat else 0
        return True, f"スロット {time_slot}: データ {count}件（探索フェーズ・投稿）"

    # 十分なデータがあるスロットのみ比較対象にする
    mature_rates = [s["avg_rate"] for s in stats.values() if s["count"] >= MIN_DATA_POINTS]
    overall_avg = sum(mature_rates) / len(mature_rates)
    threshold = overall_avg * 0.8  # 平均の80%以上なら投稿

    if slot_stat["avg_rate"] >= threshold:
        return True, (f"スロット {time_slot}: エンゲージ {slot_stat['avg_rate']:.2%} "
                      f"≥ 閾値 {threshold:.2%}（投稿）")
    else:
        return False, (f"スロット {time_slot}: エンゲージ {slot_stat['avg_rate']:.2%} "
                       f"< 閾値 {threshold:.2%}（低パフォーマンス・スキップ）")


# 文字数カテゴリ定義
LENGTH_CATEGORIES = {
    "short":  80,   # ~80文字
    "medium": 200,  # ~200文字
    "long":   380,  # ~380文字
}


def decide_post_length():
    """文字数カテゴリをエンゲージデータで判断する
    - データ不足: 均等ローテーション（探索）
    - データあり: 勝者60%、2位30%、3位10%
    Returns: (category_name, target_chars)
    """
    stats = get_length_stats()
    cats = list(LENGTH_CATEGORIES.keys())

    all_ready = all(stats.get(c, {}).get("count", 0) >= AB_MIN_SAMPLES for c in cats)

    if not all_ready:
        # 探索フェーズ: データが少ないカテゴリを優先的に選ぶ
        counts = {c: stats.get(c, {}).get("count", 0) for c in cats}
        least = min(cats, key=lambda c: counts[c])
        reason = (f"文字数探索中 (短:{counts['short']}件 中:{counts['medium']}件 長:{counts['long']}件) "
                  f"→ {least}")
        chosen = least
    else:
        # 成熟フェーズ: 上位優遇
        sorted_cats = sorted(cats, key=lambda c: stats[c]["avg_rate"], reverse=True)
        weights = [0.60, 0.30, 0.10]
        r = random.random()
        cumulative = 0
        chosen = sorted_cats[0]
        for cat, w in zip(sorted_cats, weights):
            cumulative += w
            if r < cumulative:
                chosen = cat
                break
        rates = {c: stats[c]["avg_rate"] for c in cats}
        reason = (f"文字数成熟 (短:{rates['short']:.2%} 中:{rates['medium']:.2%} 長:{rates['long']:.2%}) "
                  f"→ {chosen}")

    target = LENGTH_CATEGORIES[chosen]
    print(f"  [A/B] {reason} ({target}文字目標)")
    return chosen, target


def decide_image_style():
    """画像スタイルをエンゲージデータで判断する
    - style_guide.jsonがあれば競合分析結果を優先
    - データ不足: 未試験スタイルを優先（全スタイルを均等に探索）
    - データあり: 1位60% / 2位25% / 3位10% / 4位5%
    Returns: style_name (str)
    """
    from image_gen import ALL_STYLES, STYLES, get_recommended_style
    stats = get_image_style_stats()
    weights_mature = [0.60, 0.25, 0.10, 0.05]

    # 競合分析データが十分なら動的プロンプト生成を70%の確率で使う
    recommended = get_recommended_style()
    if recommended == "dynamic" and random.random() < 0.70:
        print(f"  [スタイル] 競合分析から動的プロンプトで画像生成")
        return "dynamic"

    all_ready = all(stats.get(s, {}).get("count", 0) >= AB_MIN_SAMPLES for s in ALL_STYLES)

    if not all_ready:
        # 未試験 or 少ないスタイルを優先
        least = min(ALL_STYLES, key=lambda s: stats.get(s, {}).get("count", 0))
        counts = {s: stats.get(s, {}).get("count", 0) for s in ALL_STYLES}
        count_str = " ".join(f"{s}:{counts[s]}" for s in ALL_STYLES)
        print(f"  [A/B] 画像スタイル探索中 ({count_str}) → {least}: {STYLES[least]['desc']}")
        return least
    else:
        sorted_styles = sorted(ALL_STYLES, key=lambda s: stats[s]["avg_rate"], reverse=True)
        r = random.random()
        cumulative = 0
        chosen = sorted_styles[0]
        for style, w in zip(sorted_styles, weights_mature):
            cumulative += w
            if r < cumulative:
                chosen = style
                break
        rates = {s: stats[s]["avg_rate"] for s in ALL_STYLES}
        rate_str = " ".join(f"{s}:{rates[s]:.2%}" for s in sorted_styles)
        print(f"  [A/B] 画像スタイル成熟 ({rate_str}) → {chosen}: {STYLES[chosen]['desc']}")
        return chosen


def decide_image_content():
    """画像コンテンツパターンをエンゲージデータで判断する"""
    from image_gen import ALL_CONTENT_PATTERNS, CONTENT_PATTERNS
    stats = get_image_content_stats()
    weights_mature = [0.60, 0.25, 0.10, 0.05]

    all_ready = all(stats.get(p, {}).get("count", 0) >= AB_MIN_SAMPLES for p in ALL_CONTENT_PATTERNS)

    if not all_ready:
        least = min(ALL_CONTENT_PATTERNS, key=lambda p: stats.get(p, {}).get("count", 0))
        counts = {p: stats.get(p, {}).get("count", 0) for p in ALL_CONTENT_PATTERNS}
        count_str = " ".join(f"{p}:{counts[p]}" for p in ALL_CONTENT_PATTERNS)
        print(f"  [A/B] 画像コンテンツ探索中 ({count_str}) → {least}: {CONTENT_PATTERNS[least]}")
        return least
    else:
        sorted_patterns = sorted(ALL_CONTENT_PATTERNS, key=lambda p: stats[p]["avg_rate"], reverse=True)
        r = random.random()
        cumulative = 0
        chosen = sorted_patterns[0]
        for pattern, w in zip(sorted_patterns, weights_mature):
            cumulative += w
            if r < cumulative:
                chosen = pattern
                break
        rates = {p: stats[p]["avg_rate"] for p in ALL_CONTENT_PATTERNS}
        rate_str = " ".join(f"{p}:{rates[p]:.2%}" for p in sorted_patterns)
        print(f"  [A/B] 画像コンテンツ成熟 ({rate_str}) → {chosen}: {CONTENT_PATTERNS[chosen]}")
        return chosen


def decide_post_type():
    """投稿タイプを3択で決める: text_only / image_text / pure_image
    - 探索フェーズ（各タイプ AB_MIN_SAMPLES 未満）: 最も少ないタイプを優先
    - 成熟フェーズ: エンゲージ率で重み付け (1位60% / 2位30% / 3位10%)
    Returns: "text_only" | "image_text" | "pure_image"
    """
    POST_TYPES = ["text_only", "image_text", "pure_image"]
    stats = get_post_type_stats()
    weights_mature = [0.60, 0.30, 0.10]

    all_ready = all(stats.get(t, {}).get("count", 0) >= AB_MIN_SAMPLES for t in POST_TYPES)

    if not all_ready:
        counts = {t: stats.get(t, {}).get("count", 0) for t in POST_TYPES}
        chosen = min(POST_TYPES, key=lambda t: counts[t])
        count_str = " ".join(f"{t}:{counts[t]}" for t in POST_TYPES)
        print(f"  [A/B] 投稿タイプ探索中 ({count_str}) → {chosen}")
    else:
        sorted_types = sorted(POST_TYPES, key=lambda t: stats[t]["avg_rate"], reverse=True)
        r = random.random()
        cumulative = 0
        chosen = sorted_types[0]
        for pt, w in zip(sorted_types, weights_mature):
            cumulative += w
            if r < cumulative:
                chosen = pt
                break
        rates = {t: stats[t]["avg_rate"] for t in POST_TYPES}
        rate_str = " ".join(f"{t}:{rates[t]:.2%}" for t in sorted_types)
        print(f"  [A/B] 投稿タイプ成熟 ({rate_str}) → {chosen}")

    return chosen


def decide_pure_image_style():
    """純粋画像スタイルをエンゲージデータで決める
    Returns: style_name (str) from ALL_PURE_STYLES
    """
    from image_gen import ALL_PURE_STYLES, PURE_IMAGE_STYLES
    stats = get_pure_image_style_stats()
    weights_mature = [0.60, 0.25, 0.10, 0.05]

    all_ready = all(stats.get(s, {}).get("count", 0) >= AB_MIN_SAMPLES for s in ALL_PURE_STYLES)

    if not all_ready:
        counts = {s: stats.get(s, {}).get("count", 0) for s in ALL_PURE_STYLES}
        min_count = min(counts.values())
        # 最少カウントのスタイルが複数あればランダム選択（同じスタイルに偏らないように）
        candidates = [s for s in ALL_PURE_STYLES if counts[s] == min_count]
        least = random.choice(candidates)
        count_str = " ".join(f"{s}:{counts[s]}" for s in ALL_PURE_STYLES)
        print(f"  [A/B] 純粋画像スタイル探索中 ({count_str}) → {least}: {PURE_IMAGE_STYLES[least]['desc']}")
        return least
    else:
        sorted_styles = sorted(ALL_PURE_STYLES, key=lambda s: stats[s]["avg_rate"], reverse=True)
        r = random.random()
        cumulative = 0
        chosen = sorted_styles[0]
        for style, w in zip(sorted_styles, weights_mature):
            cumulative += w
            if r < cumulative:
                chosen = style
                break
        rates = {s: stats[s]["avg_rate"] for s in ALL_PURE_STYLES}
        rate_str = " ".join(f"{s}:{rates[s]:.2%}" for s in sorted_styles[:4])
        print(f"  [A/B] 純粋画像スタイル成熟 ({rate_str}) → {chosen}: {PURE_IMAGE_STYLES[chosen]['desc']}")
        return chosen


def _save_pending(data):
    with open(PENDING_POST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_mode():
    """コンテンツ・画像を生成して pending_post.json に保存"""
    print("=" * 40)
    print("  [生成モード] SNS 自動投稿システム")
    print("=" * 40)

    time_slot, _ = get_time_theme()
    should_post, reason = should_post_now(time_slot)
    print(f"\n【投稿判断】{reason}")

    if not should_post:
        print("  → スキップします。")
        _save_pending({"skip": True, "reason": reason})
        return

    print("\n【投稿生成】")
    # 文字数A/Bテスト
    length_category, target_chars = decide_post_length()

    try:
        post_content, score = get_best_post(platform="threads", target_chars=target_chars)
    except Exception as e:
        err_str = str(e)
        notify_error(f"generate_mode エラー: {err_str[:500]}")
        raise

    # Geminiが0-10スケールで返した場合は0-100に正規化
    if isinstance(score, (int, float)) and score <= 10:
        score = round(score * 10, 1)

    if score < SCORE_THRESHOLD:
        print(f"  スコア {score} < 閾値 {SCORE_THRESHOLD}、品質不足につきスキップ")
        _save_pending({"skip": True, "reason": f"score {score} < threshold {SCORE_THRESHOLD}"})
        return

    print(f"\n--- 投稿内容 (スコア: {score}/100) ---\n{post_content}\n")

    # 投稿タイプを3択で決める（A/Bテスト）
    # text_only: テキストのみ
    # image_text: テキスト焼き込み画像
    # pure_image: テキストなしのスピリチュアル画像（キャプションは投稿本文）
    post_type = decide_post_type()

    image_filename = None
    image_url = None
    image_style = None
    image_content_pattern = None
    pure_image_style = None

    if post_type in ("image_text", "pure_image"):
        try:
            jst = pytz.timezone("Asia/Tokyo")
            ts = datetime.now(jst).strftime("%Y%m%d_%H%M%S")
            os.makedirs(IMAGES_DIR, exist_ok=True)

            if post_type == "image_text":
                from image_gen import create_fortune_image, upload_image
                image_style = decide_image_style()
                image_content_pattern = decide_image_content()
                image_filename = f"{ts}.png"
                image_path = os.path.join(IMAGES_DIR, image_filename)
                create_fortune_image(post_content, image_path,
                                     style=image_style,
                                     content_pattern=image_content_pattern)
                print(f"  テキスト付き画像生成: {image_filename} (スタイル:{image_style} / コンテンツ:{image_content_pattern})")

            else:  # pure_image
                from image_gen import create_pure_image, upload_image
                pure_image_style = decide_pure_image_style()
                image_filename = f"{ts}_pure.png"
                image_path = os.path.join(IMAGES_DIR, image_filename)
                create_pure_image(image_path, style=pure_image_style)
                print(f"  純粋スピ画像生成: {image_filename} (スタイル:{pure_image_style})")

            # ── Gemini Vision 安全チェック（アップロード前） ──
            from image_gen import check_image_safety, upload_image
            if not check_image_safety(image_path):
                print(f"  ⚠️ 安全チェックNG → テキスト投稿に変更")
                post_type = "text_only"
                image_filename = None
                image_style = None
                image_content_pattern = None
                pure_image_style = None
            else:
                image_url = upload_image(image_path)
                if image_url:
                    print(f"  画像URL: {image_url}")
                else:
                    # catbox.moe失敗 → GitHub raw URLにフォールバック
                    # commit+push後に有効になるため、post_modeで使用できる
                    image_url = (
                        "https://raw.githubusercontent.com/tkm369/sns-auto-poster"
                        f"/master/sns_auto_poster/generated_images/{image_filename}"
                    )
                    print(f"  catbox失敗 → GitHub raw URLにフォールバック: {image_url}")
        except Exception as e:
            print(f"  ⚠️ 画像生成失敗 (テキスト投稿に変更): {e}")
            post_type = "text_only"
            image_filename = None
            image_url = None
            image_style = None
            image_content_pattern = None
            pure_image_style = None
    else:
        print(f"  テキストのみで投稿")

    _save_pending({
        "skip": False,
        "content": post_content,
        "score": score,
        "time_slot": time_slot,
        "image_filename": image_filename,
        "image_url": image_url,
        "image_style": image_style,
        "image_content_pattern": image_content_pattern,
        "length_category": length_category,
        "post_type": post_type,
        "pure_image_style": pure_image_style,
    })
    print(f"  pending_post.json を保存しました")


def post_mode():
    """pending_post.json を読んで投稿実行"""
    print("=" * 40)
    print("  [投稿モード] SNS 自動投稿システム")
    print("=" * 40)

    if not os.path.exists(PENDING_POST_FILE):
        print("  pending_post.json が見つかりません。スキップ。")
        return

    with open(PENDING_POST_FILE, encoding="utf-8") as f:
        pending = json.load(f)

    if pending.get("skip"):
        reason = pending.get('reason', '')
        print(f"  スキップ: {reason}")
        if "quota" not in reason.lower():  # quota超過はgenerate側で通知済み
            notify_post_skip(reason)
        return

    post_content = pending["content"]
    time_slot = pending["time_slot"]
    image_filename = pending.get("image_filename")
    image_url = pending.get("image_url")  # catbox.moe にアップロード済みURL

    if image_url:
        print(f"  画像URL: {image_url}")

    print(f"\n--- 投稿内容 ---\n{post_content}\n")

    # 投稿実行
    print("\n【投稿実行】")
    x_id = post_to_x(post_content)
    threads_id = post_to_threads(post_content, image_url=image_url)

    # ログ記録
    has_affiliate = bool(AFFILIATE_LINK)
    has_image = bool(image_filename)
    length_category = pending.get("length_category")
    image_style = pending.get("image_style")
    image_content_pattern = pending.get("image_content_pattern")
    post_type = pending.get("post_type")
    pure_image_style = pending.get("pure_image_style")
    # 旧形式の pending_post.json との後方互換
    if post_type is None:
        post_type = "image_text" if has_image else "text_only"
    if x_id:
        add_post(x_id, "x", post_content, time_slot, has_affiliate=has_affiliate, has_image=has_image,
                 length_category=length_category, image_style=image_style,
                 image_content_pattern=image_content_pattern,
                 post_type=post_type, pure_image_style=pure_image_style)
    if threads_id:
        add_post(threads_id, "threads", post_content, time_slot, has_affiliate=has_affiliate, has_image=has_image,
                 length_category=length_category, image_style=image_style,
                 image_content_pattern=image_content_pattern,
                 post_type=post_type, pure_image_style=pure_image_style)

    # 古い画像を削除
    try:
        from image_gen import cleanup_old_images
        cleanup_old_images(IMAGES_DIR)
    except Exception:
        pass

    print("\n" + "=" * 40)
    print(f"  X       : {'✅ 成功' if x_id else '❌ 失敗/スキップ'}")
    print(f"  Threads : {'✅ 成功' if threads_id else '❌ 失敗/スキップ'}")
    print("=" * 40)

    # Discord通知
    if threads_id:
        notify_post_success("Threads", post_type or "unknown", post_content)
    elif not threads_id and not x_id:
        notify_error("投稿失敗: ThreadsもXも投稿できませんでした")


def main():
    mode = "post"
    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]

    if mode == "generate":
        generate_mode()
    elif mode == "post":
        post_mode()
    else:
        print(f"未知のモード: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
