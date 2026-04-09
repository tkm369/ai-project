"""
strategy_optimizer.py - posts_log.jsonのデータをGeminiで分析してPDCAレポートを生成・config更新
"""
import os
import json
import urllib.request
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

POSTS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts_log.json")
CONFIG_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
REPORT_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdca_report.json")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def _gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return ""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.3}
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.loads(res.read())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Gemini失敗: {e}")
        return ""


def run_pdca():
    if not os.path.exists(POSTS_LOG_FILE):
        logger.info("posts_log.jsonなし。スキップ。")
        return

    with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
        log = json.load(f)

    # アナリティクスが取得済みのもののみ対象
    measured = [e for e in log if e.get("views") is not None]
    if len(measured) < 3:
        logger.info(f"データ不足 ({len(measured)}件)。3件以上必要です。")
        return

    # 統計
    avg_views    = sum(e["views"] for e in measured) / len(measured)
    avg_likes    = sum(e["likes"] or 0 for e in measured) / len(measured)
    top          = sorted(measured, key=lambda x: x["views"], reverse=True)[:3]
    bottom       = sorted(measured, key=lambda x: x["views"])[:3]

    summary = {
        "total_posts": len(log),
        "measured_posts": len(measured),
        "avg_views": round(avg_views),
        "avg_likes": round(avg_likes),
        "top_posts": [{"text": e["text"][:50], "views": e["views"], "likes": e["likes"]} for e in top],
        "bottom_posts": [{"text": e["text"][:50], "views": e["views"], "likes": e["likes"]} for e in bottom],
    }

    logger.info(f"平均再生数: {avg_views:.0f} / 平均いいね: {avg_likes:.0f}")

    # Geminiでレポート生成
    prompt = f"""TikTokアカウント（復縁・恋愛ジャンル）の投稿データを分析してください。

データ：
{json.dumps(summary, ensure_ascii=False, indent=2)}

以下をJSON形式で返してください：
{{
  "insight": "上位投稿と下位投稿の違いについての分析（日本語100文字以内）",
  "recommended_hashtags": ["推奨ハッシュタグ1", "推奨ハッシュタグ2", ...（5〜8個）"],
  "content_tip": "今後のコンテンツ改善のアドバイス（日本語100文字以内）"
}}

JSONのみ返してください。"""

    result = _gemini(prompt)
    if not result:
        logger.warning("Gemini応答なし")
        return

    try:
        # JSONを抽出
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            raise ValueError("JSONが見つかりません")
        recommendation = json.loads(json_match.group())
    except Exception as e:
        logger.error(f"レポートパース失敗: {e}\n{result}")
        return

    logger.info(f"分析: {recommendation.get('insight', '')}")
    logger.info(f"コンテンツTip: {recommendation.get('content_tip', '')}")

    # ハッシュタグを更新
    new_hashtags = recommendation.get("recommended_hashtags", [])
    if new_hashtags:
        _update_hashtags(new_hashtags)
        logger.info(f"ハッシュタグ更新: {new_hashtags}")

    # レポート保存
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "recommendation": recommendation,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"PDCAレポート保存: {REPORT_FILE}")


def _update_hashtags(new_hashtags: list):
    """config.pyのTHREADS_HASHTAGSを更新"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    import re
    hashtag_list = json.dumps(new_hashtags, ensure_ascii=False)
    # リスト形式に変換
    items = ',\n    '.join(f'"{h}"' for h in new_hashtags)
    new_block = f'THREADS_HASHTAGS = [\n    {items},\n]'
    content = re.sub(
        r'THREADS_HASHTAGS\s*=\s*\[.*?\]',
        new_block,
        content,
        flags=re.DOTALL
    )
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_pdca()
