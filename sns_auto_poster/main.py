import sys
import json
import os
import random
from datetime import datetime
import pytz

from generator import get_best_post, get_time_theme
from poster import post_to_x, post_to_threads
from logger import add_post, count_posts_today, get_time_slot_stats, get_image_vs_text_stats, get_length_stats, get_image_style_stats, get_image_content_stats
from config import AFFILIATE_LINK

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


def should_post_now(time_slot):
    """今この時間帯に投稿すべきか判断する（PDCAベース）"""
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


def decide_use_image():
    """画像を使うかどうかをエンゲージデータで判断する
    - データ不足: 50/50でランダム（A/B探索）
    - データあり: 勝者を70%、敗者を30%の確率で選ぶ
    """
    stats = get_image_vs_text_stats()
    img = stats["image"]
    txt = stats["text"]

    img_ok = img["count"] >= AB_MIN_SAMPLES
    txt_ok = txt["count"] >= AB_MIN_SAMPLES

    if not img_ok or not txt_ok:
        # どちらかデータ不足 → 交互にA/Bテスト（50/50）
        use_image = random.random() < 0.5
        reason = (f"A/B探索中 (画像:{img['count']}件, テキスト:{txt['count']}件) "
                  f"→ {'画像' if use_image else 'テキスト'}")
    else:
        image_rate = img["avg_rate"]
        text_rate = txt["avg_rate"]
        if image_rate > text_rate * 1.1:
            # 画像が10%以上上回る → 画像70%
            use_image = random.random() < 0.70
            reason = (f"画像優勢 ({image_rate:.2%} vs {text_rate:.2%}) "
                      f"→ 画像70%ルール → {'画像' if use_image else 'テキスト'}")
        elif text_rate > image_rate * 1.1:
            # テキストが10%以上上回る → テキスト70%
            use_image = random.random() < 0.30
            reason = (f"テキスト優勢 ({text_rate:.2%} vs {image_rate:.2%}) "
                      f"→ テキスト70%ルール → {'画像' if use_image else 'テキスト'}")
        else:
            # 差が小さい → 50/50継続
            use_image = random.random() < 0.5
            reason = (f"差なし (画像:{image_rate:.2%} vs テキスト:{text_rate:.2%}) "
                      f"→ 50/50 → {'画像' if use_image else 'テキスト'}")

    print(f"  [A/B] {reason}")
    return use_image


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
        if "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower() or "429" in err_str:
            print(f"⚠️  Gemini APIの日次クォータを超過しました")
            _save_pending({"skip": True, "reason": "Gemini quota exceeded"})
            return
        raise

    # Geminiが0-10スケールで返した場合は0-100に正規化
    if isinstance(score, (int, float)) and score <= 10:
        score = round(score * 10, 1)

    if score < SCORE_THRESHOLD:
        print(f"  スコア {score} < 閾値 {SCORE_THRESHOLD}、品質不足につきスキップ")
        _save_pending({"skip": True, "reason": f"score {score} < threshold {SCORE_THRESHOLD}"})
        return

    print(f"\n--- 投稿内容 (スコア: {score}/100) ---\n{post_content}\n")

    # 画像を使うか判断（A/Bテスト）
    use_image = decide_use_image()

    image_filename = None
    image_url = None
    image_style = None
    image_content_pattern = None
    if use_image:
        try:
            from image_gen import create_fortune_image, upload_image
            image_style = decide_image_style()
            image_content_pattern = decide_image_content()
            os.makedirs(IMAGES_DIR, exist_ok=True)
            jst = pytz.timezone("Asia/Tokyo")
            ts = datetime.now(jst).strftime("%Y%m%d_%H%M%S")
            image_filename = f"{ts}.png"
            image_path = os.path.join(IMAGES_DIR, image_filename)
            create_fortune_image(post_content, image_path,
                                 style=image_style,
                                 content_pattern=image_content_pattern)
            print(f"  画像生成: {image_filename} (スタイル:{image_style} / コンテンツ:{image_content_pattern})")
            image_url = upload_image(image_path)
            if image_url:
                print(f"  画像URL: {image_url}")
            else:
                print(f"  ⚠️ アップロード失敗 → テキスト投稿に変更")
                image_filename = None
                image_style = None
                image_content_pattern = None
        except Exception as e:
            print(f"  ⚠️ 画像生成失敗 (テキスト投稿に変更): {e}")
            image_filename = None
            image_url = None
            image_style = None
            image_content_pattern = None
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
        print(f"  スキップ: {pending.get('reason', '')}")
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
    if x_id:
        add_post(x_id, "x", post_content, time_slot, has_affiliate=has_affiliate, has_image=has_image, length_category=length_category, image_style=image_style, image_content_pattern=image_content_pattern)
    if threads_id:
        add_post(threads_id, "threads", post_content, time_slot, has_affiliate=has_affiliate, has_image=has_image, length_category=length_category, image_style=image_style, image_content_pattern=image_content_pattern)

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
