"""
競合アカウントの画像をGemini Visionで分析してデザインパターンを抽出する
→ style_guide.json に蓄積し、image_gen.py がそれを参照して画像生成
"""
import json
import os
import time
import requests
from config import THREADS_ACCESS_TOKEN, GEMINI_API_KEY

STYLE_GUIDE_PATH = os.path.join(os.path.dirname(__file__), "style_guide.json")
BASE_URL = "https://graph.threads.net/v1.0"
MAX_STYLES = 30       # 保持するデザインパターンの最大数
MIN_LIKES_IMAGE = 3   # 分析対象にする最低いいね数


# ─── Threads API: 画像付き投稿を取得 ──────────────────────
def _get(url, params, retries=2):
    for i in range(retries + 1):
        try:
            res = requests.get(url, params=params, timeout=15)
            return res.json()
        except Exception as e:
            if i < retries:
                time.sleep(3)
            else:
                return {}


def fetch_image_posts(user_id, limit=20):
    """ユーザーの画像投稿を取得"""
    data = _get(f"{BASE_URL}/{user_id}/threads", {
        "fields": "id,text,media_type,media_url,like_count,timestamp",
        "limit": limit,
        "access_token": THREADS_ACCESS_TOKEN,
    })
    posts = data.get("data", [])
    # IMAGE タイプのみ・media_urlあり・いいね数フィルタ
    return [
        p for p in posts
        if p.get("media_type") == "IMAGE"
        and p.get("media_url")
        and (p.get("like_count") or 0) >= MIN_LIKES_IMAGE
    ]


# ─── Gemini Vision: 画像デザイン分析 ─────────────────────
def analyze_image_style(image_url, post_text=""):
    """画像をGemini Visionで分析してデザイン仕様を返す"""
    if not GEMINI_API_KEY:
        return None
    try:
        # 画像をダウンロード
        res = requests.get(image_url, timeout=20)
        if res.status_code != 200 or len(res.content) < 5000:
            return None
        image_bytes = res.content

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = """この画像はThreadsの占い・スピリチュアル・復縁ジャンルの投稿画像です。
まず最初に、この画像が「スキップすべき画像」かどうかを判定してください。

スキップすべき画像の条件（1つでも当てはまればskip: true）:
- 商品・サービスの宣伝・販売訴求（価格表示、「詳しくはこちら」など）
- アカウント固有のロゴ・名前・URLが大きく入っている（ブランディング画像）
- プロフィール紹介・自己紹介カード
- 予約・申し込みの告知バナー
- 特定の人物の顔写真がメインで占めている（スピリチュアル感がない）

上記に該当しない「純粋なコンテンツ投稿画像」のみデザイン分析してください。

以下のJSON形式で返してください（説明文不要、JSONのみ）:

{
  "skip": true_or_false,
  "skip_reason": "スキップする場合の理由（該当しない場合はnull）",
  "background_type": "gradient|solid_dark|solid_light|real_photo|ai_art|abstract_art",
  "dominant_colors": ["#色1", "#色2", "#色3"],
  "text_color": "#色",
  "text_lines_count": 数字,
  "text_size": "very_large|large|medium|small",
  "text_position": "center|top|bottom|left|right",
  "font_style": "bold|thin|calligraphy|standard",
  "has_person": true_or_false,
  "has_nature": true_or_false,
  "atmosphere": "dark_mystical|bright_dreamy|minimal_clean|warm_emotional|cosmic|romantic",
  "key_visual_elements": ["要素1", "要素2"],
  "text_decoration": "shadow|outline|plain|glow",
  "overall_quality_score": 1から10の数字,
  "why_it_works": "一言で"
}"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ]
        )

        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        result = json.loads(text[start:end])
        result["source_url"] = image_url
        result["post_text_preview"] = post_text[:50]
        return result

    except Exception as e:
        print(f"    画像分析失敗: {e}")
        return None


# ─── style_guide.json 管理 ────────────────────────────────
def load_style_guide():
    if os.path.exists(STYLE_GUIDE_PATH):
        try:
            with open(STYLE_GUIDE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"styles": [], "summary": {}}


def save_style_guide(guide):
    with open(STYLE_GUIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(guide, f, ensure_ascii=False, indent=2)


def _summarize_styles(styles):
    """蓄積したスタイルから最頻出パターンを集計"""
    if not styles:
        return {}

    from collections import Counter

    bg_types = Counter(s.get("background_type") for s in styles if s.get("background_type"))
    atmospheres = Counter(s.get("atmosphere") for s in styles if s.get("atmosphere"))
    text_sizes = Counter(s.get("text_size") for s in styles if s.get("text_size"))
    font_styles = Counter(s.get("font_style") for s in styles if s.get("font_style"))

    # 高スコアのスタイルだけ抽出
    high_quality = [s for s in styles if s.get("overall_quality_score", 0) >= 7]

    return {
        "top_background_type": bg_types.most_common(1)[0][0] if bg_types else "gradient",
        "top_atmosphere": atmospheres.most_common(1)[0][0] if atmospheres else "dark_mystical",
        "top_text_size": text_sizes.most_common(1)[0][0] if text_sizes else "large",
        "top_font_style": font_styles.most_common(1)[0][0] if font_styles else "bold",
        "has_person_rate": sum(1 for s in styles if s.get("has_person")) / len(styles),
        "high_quality_count": len(high_quality),
        "total_analyzed": len(styles),
        "best_why": [s.get("why_it_works") for s in high_quality[:5] if s.get("why_it_works")],
    }


# ─── メイン実行 ───────────────────────────────────────────
def run(competitor_stats):
    """
    competitor_stats: account_stats.jsonのaccountsデータ
    アクティブアカウントの画像を分析してstyle_guide.jsonを更新
    """
    print("\n=== 競合画像スタイル分析 ===")
    guide = load_style_guide()
    existing_urls = {s.get("source_url") for s in guide["styles"]}

    analyzed_count = 0
    from urllib.parse import quote
    from competitor_tracker import get_user_id

    active_accounts = [
        u for u, e in competitor_stats.items()
        if e.get("status") == "active"
    ]

    for username in active_accounts[:8]:  # 最大8アカウント（API節約）
        print(f"  @{username} の画像を取得中...")
        user_id = get_user_id(username)
        if not user_id:
            continue

        image_posts = fetch_image_posts(user_id, limit=15)
        if not image_posts:
            print(f"    画像投稿なし")
            time.sleep(1)
            continue

        # いいね順にソートして上位3件を分析
        image_posts.sort(key=lambda p: p.get("like_count", 0) or 0, reverse=True)

        for post in image_posts[:3]:
            url = post.get("media_url")
            if not url or url in existing_urls:
                continue

            print(f"    分析中 (likes={post.get('like_count', 0)})...")
            style = analyze_image_style(url, post.get("text", ""))
            if not style:
                continue

            # 商品宣伝・アカウントブランディング画像をスキップ
            if style.get("skip"):
                reason = style.get("skip_reason", "不明")
                print(f"    ⏭️  スキップ: {reason}")
                existing_urls.add(url)  # 再分析しないようURLは記録
                continue

            style["like_count"] = post.get("like_count", 0)
            style["username"] = username
            guide["styles"].append(style)
            existing_urls.add(url)
            analyzed_count += 1
            print(f"    ✅ {style.get('atmosphere')} / {style.get('background_type')} / score={style.get('overall_quality_score')}")

            time.sleep(13)  # Gemini API レート制限 (5RPM)

        time.sleep(2)

    # 古いものを削除して最大件数を維持
    guide["styles"] = sorted(
        guide["styles"],
        key=lambda s: s.get("like_count", 0),
        reverse=True
    )[:MAX_STYLES]

    # サマリー更新
    guide["summary"] = _summarize_styles(guide["styles"])

    save_style_guide(guide)
    print(f"\n✅ {analyzed_count}件分析 / 合計{len(guide['styles'])}件蓄積")
    print(f"   主要スタイル: {guide['summary'].get('top_background_type')} / {guide['summary'].get('top_atmosphere')}")
    return guide


if __name__ == "__main__":
    # テスト実行
    guide = load_style_guide()
    print(json.dumps(guide.get("summary", {}), ensure_ascii=False, indent=2))
