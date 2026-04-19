"""
strategy_optimizer.py - posts_log.jsonのデータをGeminiで分析してPDCA全項目を最適化
最適化対象: ハッシュタグ・動画尺・コンテンツスタイル・投稿時間（レポートのみ）
"""
import os
import re
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

MIN_POSTS = 5  # 最低この件数のデータがないと分析しない


def _gemini(prompt: str) -> str:
    try:
        from gemini_client import call_gemini, GeminiUnavailable, GeminiQuotaExhausted
        return call_gemini(prompt, max_tokens=1500, temperature=0.3)
    except (GeminiUnavailable, GeminiQuotaExhausted) as e:
        logger.warning(f"Gemini スキップ: {e}")
        return ""
    except Exception as e:
        logger.error(f"Gemini失敗: {e}")
        return ""


def _avg(lst):
    lst = [x for x in lst if x is not None]
    return round(sum(lst) / len(lst)) if lst else 0


def run_pdca():
    if not os.path.exists(POSTS_LOG_FILE):
        logger.info("posts_log.jsonなし。スキップ。")
        return

    with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
        log = json.load(f)

    measured = [e for e in log if e.get("views") is not None]
    if len(measured) < MIN_POSTS:
        logger.info(f"データ不足 ({len(measured)}/{MIN_POSTS}件)。スキップ。")
        return

    avg_views = _avg([e["views"] for e in measured])
    avg_likes = _avg([e["likes"] for e in measured])
    top    = sorted(measured, key=lambda x: x["views"], reverse=True)[:5]
    bottom = sorted(measured, key=lambda x: x["views"])[:5]

    # 投稿時間帯別の平均再生数
    hour_stats = {}
    for e in measured:
        h = e.get("posting_hour", -1)
        if h >= 0:
            hour_stats.setdefault(h, []).append(e["views"])
    hour_avg = {h: _avg(vs) for h, vs in hour_stats.items()}
    best_hours = sorted(hour_avg, key=hour_avg.get, reverse=True)[:3]

    # ハッシュタグ別の平均再生数
    tag_stats = {}
    for e in measured:
        tag = e.get("source_hashtag", "不明")
        tag_stats.setdefault(tag, []).append(e["views"])
    tag_avg = {t: _avg(vs) for t, vs in tag_stats.items()}

    # テキスト長別
    short = [e for e in measured if e.get("text_length", 0) < 40]
    long_  = [e for e in measured if e.get("text_length", 0) >= 40]
    short_avg = _avg([e["views"] for e in short])
    long_avg  = _avg([e["views"] for e in long_])

    # 動画尺別
    dur_stats = {}
    for e in measured:
        d = e.get("video_duration", 7.0)
        dur_stats.setdefault(d, []).append(e["views"])
    dur_avg = {d: _avg(vs) for d, vs in dur_stats.items()}

    summary = {
        "total_posts": len(log),
        "measured_posts": len(measured),
        "avg_views": avg_views,
        "avg_likes": avg_likes,
        "best_posting_hours": best_hours,
        "hour_avg_views": hour_avg,
        "tag_avg_views": tag_avg,
        "text_length_comparison": {"short_under40": short_avg, "long_over40": long_avg},
        "duration_avg_views": dur_avg,
        "top_posts": [{"text": e["text"][:60], "views": e["views"], "hour": e.get("posting_hour"), "tag": e.get("source_hashtag")} for e in top],
        "bottom_posts": [{"text": e["text"][:60], "views": e["views"], "hour": e.get("posting_hour"), "tag": e.get("source_hashtag")} for e in bottom],
    }

    logger.info(f"平均再生数: {avg_views} / 平均いいね: {avg_likes}")

    prompt = f"""TikTokアカウント（復縁・恋愛ジャンル）の投稿パフォーマンスデータを分析してください。

データ：
{json.dumps(summary, ensure_ascii=False, indent=2)}

以下をJSON形式で返してください：
{{
  "insight": "データ全体の分析コメント（日本語150文字以内）",
  "recommended_hashtags": ["検索に使うべきThreadsハッシュタグ（#なし）を5〜8個"],
  "optimal_video_duration": 数字（秒、8〜15の間）,
  "content_style_hint": "伸びているコンテンツのスタイル・特徴をGeminiへの指示形式で（日本語100文字以内）",
  "best_hours_note": "再生数が伸びやすい投稿時間帯のコメント（日本語50文字以内）"
}}

JSONのみ返してください。"""

    result = _gemini(prompt)
    if not result:
        logger.warning("Gemini応答なし")
        return

    try:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            raise ValueError("JSONが見つかりません")
        rec = json.loads(json_match.group())
    except Exception as e:
        logger.error(f"レポートパース失敗: {e}\n{result}")
        return

    logger.info(f"分析: {rec.get('insight', '')}")
    logger.info(f"最適動画尺: {rec.get('optimal_video_duration')}秒")
    logger.info(f"コンテンツTip: {rec.get('content_style_hint', '')}")
    logger.info(f"ベスト投稿時間: {rec.get('best_hours_note', '')}")

    # config.pyを更新
    _update_config(
        hashtags=rec.get("recommended_hashtags", []),
        video_duration=rec.get("optimal_video_duration"),
        content_style_hint=rec.get("content_style_hint", ""),
    )

    # レポート保存
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "recommendation": rec,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"PDCAレポート保存完了")


def _update_config(hashtags: list, video_duration, content_style_hint: str):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # THREADS_HASHTAGS更新
    if hashtags:
        items = ',\n    '.join(f'"{h}"' for h in hashtags)
        new_block = f'THREADS_HASHTAGS = [\n    {items},\n]'
        content = re.sub(r'THREADS_HASHTAGS\s*=\s*\[.*?\]', new_block, content, flags=re.DOTALL)
        logger.info(f"ハッシュタグ更新: {hashtags}")

    # VIDEO_DURATION更新
    if video_duration and 8 <= float(video_duration) <= 15:
        content = re.sub(r'VIDEO_DURATION\s*=\s*[\d.]+', f'VIDEO_DURATION = {float(video_duration)}', content)
        logger.info(f"動画尺更新: {video_duration}秒")

    # CONTENT_STYLE_HINT更新
    if content_style_hint:
        escaped = content_style_hint.replace('"', '\\"')
        content = re.sub(r'CONTENT_STYLE_HINT\s*=\s*".*?"', f'CONTENT_STYLE_HINT = "{escaped}"', content)
        logger.info(f"コンテンツスタイル更新: {content_style_hint}")

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_pdca()
