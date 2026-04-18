"""
pdca_analyzer.py - posts_log.jsonのパフォーマンスデータをGeminiで分析し
                   strategy.jsonを更新する（PDCA の Check → Act）

GitHub Actionsから定期実行される。
"""
import os
import sys
import json
import urllib.request
from datetime import datetime, timedelta

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
POSTS_LOG     = os.path.join(BASE_DIR, "posts_log.json")
STRATEGY_FILE = os.path.join(BASE_DIR, "strategy.json")

CATEGORIES = [
    "片思い", "失恋", "復縁", "恋愛あるある",
    "元カレ元カノ", "好きな人", "寂しい夜", "恋愛名言",
]
TONES   = ["共感型", "励まし型", "あるある型"]
FORMATS = ["独白", "問いかけ", "ストーリー"]


# ------------------------------------------------------------------ #
#  データ読み込み
# ------------------------------------------------------------------ #

def load_posts_log() -> list:
    if not os.path.exists(POSTS_LOG):
        return []
    with open(POSTS_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def load_strategy() -> dict:
    if os.path.exists(STRATEGY_FILE):
        with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_strategy(s: dict):
    with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ #
#  統計集計（Gemini不要な部分）
# ------------------------------------------------------------------ #

def compute_stats(posts: list) -> dict:
    """カテゴリ・トーン・フォーマット別の平均再生数/いいね数を計算
    likes が取れない場合は views を代替指標として使用"""
    # viewsかlikesがある投稿を対象（views優先）
    measured = [p for p in posts if p.get("views") is not None or p.get("likes") is not None]
    if not measured:
        return {}

    def metric(p):
        """いいね優先、なければ再生数を使う"""
        return p.get("likes") if p.get("likes") is not None else p.get("views", 0)

    def avg_by(key, choices):
        result = {}
        for val in choices:
            group = [metric(p) for p in measured if p.get(key) == val]
            if group:
                result[val] = round(sum(group) / len(group), 1)
        return result

    return {
        "total_measured": len(measured),
        "by_category": avg_by("category", CATEGORIES),
        "by_tone":     avg_by("tone", TONES),
        "by_format":   avg_by("format", FORMATS),
        "by_hour": {
            h: round(sum(metric(p) for p in measured if p.get("posting_hour") == h)
                     / len([p for p in measured if p.get("posting_hour") == h]), 1)
            for h in range(24)
            if any(p.get("posting_hour") == h for p in measured)
        },
        "recent_posts": [
            {
                "text": p.get("text", "")[:40],
                "category": p.get("category"),
                "tone": p.get("tone"),
                "format": p.get("format"),
                "likes": p.get("likes"),
                "views": p.get("views"),
                "posted_at": p.get("posted_at", "")[:10],
            }
            for p in sorted(measured, key=lambda x: x.get("posted_at", ""), reverse=True)[:20]
        ],
    }


# ------------------------------------------------------------------ #
#  Gemini 分析
# ------------------------------------------------------------------ #

def _call_gemini(prompt: str) -> str:
    import time
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY未設定")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            return resp["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                print(f"Gemini rate limit, 65秒待機... (attempt {attempt+1}/3)")
                time.sleep(65)
            else:
                raise


def analyze_with_gemini(stats: dict, current_strategy: dict) -> dict:
    """Geminiがパフォーマンスを分析して次の戦略を提案"""

    prompt = f"""あなたはTikTokコンテンツの戦略アナリストです。
以下のパフォーマンスデータを分析し、次の投稿戦略をJSONで出力してください。

【パフォーマンスデータ】
{json.dumps(stats, ensure_ascii=False, indent=2)}

【現在の戦略】
{json.dumps(current_strategy.get("generation_params", {}), ensure_ascii=False)}

分析して以下のJSONを出力してください：
{{
  "insights": "1〜2文で何が伸びているかの要約",
  "category_weights": {{
    "片思い": 数値(0.1〜3.0),
    "失恋": 数値,
    "復縁": 数値,
    "恋愛あるある": 数値,
    "元カレ元カノ": 数値,
    "好きな人": 数値,
    "寂しい夜": 数値,
    "恋愛名言": 数値
  }},
  "generation_params": {{
    "tone": "共感型 or 励まし型 or あるある型",
    "format": "独白 or 問いかけ or ストーリー",
    "length_range": [最小文字数, 最大文字数]
  }}
}}

データが少ない場合は全カテゴリweight=1.0・現状維持を推奨してください。
JSONのみ出力してください。"""

    raw = _call_gemini(prompt)
    # JSON抽出
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


# ------------------------------------------------------------------ #
#  メイン
# ------------------------------------------------------------------ #

def run():
    print("=== PDCA分析開始 ===")
    posts = load_posts_log()
    strategy = load_strategy()

    print(f"総投稿数: {len(posts)}")
    stats = compute_stats(posts)

    if not stats:
        print("メトリクスデータなし（投稿後24時間待機中）→ strategy.json更新スキップ")
        return

    print(f"計測済み投稿: {stats['total_measured']}件")
    print(f"カテゴリ別平均いいね: {stats.get('by_category', {})}")

    # カテゴリ統計を先に更新（Gemini失敗でも反映させる）
    by_cat = stats.get("by_category", {})
    for cat in CATEGORIES:
        if cat in strategy.get("categories", {}):
            if cat in by_cat:
                strategy["categories"][cat]["avg_likes"] = by_cat[cat]
            cnt = sum(1 for p in posts
                      if p.get("category") == cat and
                      (p.get("views") is not None or p.get("likes") is not None))
            strategy["categories"][cat]["post_count"] = cnt

    # Geminiで分析（失敗時はルールベースフォールバック）
    print("Gemini分析中...")
    result = None
    try:
        result = analyze_with_gemini(stats, strategy)
    except Exception as e:
        print(f"Gemini分析エラー（フォールバック使用）: {e}")

    if result is None:
        # ルールベース: 平均スコアが高いカテゴリのweightを上げる
        if by_cat:
            max_score = max(by_cat.values()) or 1
            new_weights = {cat: round(1.0 + (by_cat.get(cat, max_score/2) / max_score), 2)
                           for cat in CATEGORIES}
            top_cat = max(by_cat, key=by_cat.get)
            result = {
                "insights": f"views計測中（{stats['total_measured']}件）。{top_cat}が最高avg {by_cat[top_cat]:.0f}views",
                "category_weights": new_weights,
                "generation_params": strategy.get("generation_params", {}),
            }
            print(f"フォールバック結果: {top_cat}が最高（{by_cat[top_cat]:.0f} avg views）")

    # strategy.jsonを更新
    strategy["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    strategy["insights"] = result.get("insights", strategy.get("insights", ""))

    # カテゴリweightを更新
    new_weights = result.get("category_weights", {})
    for cat in CATEGORIES:
        if cat in new_weights and cat in strategy.get("categories", {}):
            strategy["categories"][cat]["weight"] = float(new_weights[cat])

    # 生成パラメータを更新
    new_params = result.get("generation_params", {})
    if new_params:
        strategy["generation_params"] = new_params

    save_strategy(strategy)
    print(f"strategy.json更新完了")
    print(f"insights: {strategy['insights']}")
    print(f"best tone: {strategy['generation_params'].get('tone')}")
    print(f"best format: {strategy['generation_params'].get('format')}")
    print("=== PDCA分析完了 ===")


if __name__ == "__main__":
    run()
