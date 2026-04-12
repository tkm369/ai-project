"""
content_generator.py - GeminiでTikTok用オリジナルコンテンツを生成

Threadsスクレイピングを廃止し、AIが直接コンテンツを生成する。
strategy.jsonの学習結果を読み込み、伸びるパターンに最適化する。
"""
import os
import json
import random
import re
import urllib.request

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

STRATEGY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy.json")

# コンテンツカテゴリ
CATEGORIES = [
    "片思い",
    "失恋",
    "復縁",
    "恋愛あるある",
    "元カレ元カノ",
    "好きな人",
    "寂しい夜",
    "恋愛名言",
]

TONES   = ["共感型", "励まし型", "あるある型"]
FORMATS = ["独白", "問いかけ", "ストーリー"]


# ------------------------------------------------------------------ #
#  strategy.json の読み書き
# ------------------------------------------------------------------ #

def load_strategy() -> dict:
    if os.path.exists(STRATEGY_FILE):
        with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _default_strategy()


def save_strategy(strategy: dict):
    with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
        json.dump(strategy, f, ensure_ascii=False, indent=2)


def _default_strategy() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "categories": {
            c: {"weight": 1.0, "avg_likes": None, "post_count": 0}
            for c in CATEGORIES
        },
        "insights": "データ蓄積中",
        "generation_params": {
            "tone": "共感型",
            "format": "独白",
            "length_range": [50, 80],
        },
    }


# ------------------------------------------------------------------ #
#  カテゴリ選択（重み付きランダム）
# ------------------------------------------------------------------ #

def pick_category(strategy: dict) -> str:
    cats = strategy.get("categories", {})
    weights = [max(cats.get(c, {}).get("weight", 1.0), 0.1) for c in CATEGORIES]
    return random.choices(CATEGORIES, weights=weights, k=1)[0]


# ------------------------------------------------------------------ #
#  Gemini 呼び出し
# ------------------------------------------------------------------ #

def _call_gemini(prompt: str) -> str:
    import time as _time
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY未設定")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.92, "maxOutputTokens": 300},
    }).encode("utf-8")
    # レートリミット対策: 最大3回、指数バックオフ
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
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = 30 * (attempt + 1)  # 30秒, 60秒
                print(f"Gemini rate limit, {wait}秒待機...", flush=True)
                _time.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini API 3回リトライ失敗")


# ------------------------------------------------------------------ #
#  コンテンツ生成
# ------------------------------------------------------------------ #

def generate_content(strategy: dict = None) -> dict:
    """
    戦略に基づいてTikTok用コンテンツを生成する。

    Returns:
        {
            "text": str,       # 動画に表示するテキスト
            "category": str,   # カテゴリ
            "tone": str,       # トーン
            "format": str,     # フォーマット
        }
    """
    if strategy is None:
        strategy = load_strategy()

    category = pick_category(strategy)
    params   = strategy.get("generation_params", {})
    tone     = params.get("tone", random.choice(TONES))
    fmt      = params.get("format", random.choice(FORMATS))
    length_range = params.get("length_range", [50, 80])
    insights = strategy.get("insights", "")

    insight_line = ""
    if insights and insights not in ("データ蓄積中", ""):
        insight_line = f"\n【過去の傾向】{insights}"

    prompt = f"""あなたはTikTokで恋愛コンテンツを発信するクリエイターです。
以下の条件でTikTok動画に表示するテキストを1つ書いてください。

【カテゴリ】{category}
【トーン】{tone}（共感型＝感情に寄り添う、励まし型＝前向きなメッセージ、あるある型＝共感できる日常描写）
【スタイル】{fmt}（独白＝一人称の語り、問いかけ＝読者への問い、ストーリー＝短い場面描写）
【文字数】{length_range[0]}〜{length_range[1]}文字{insight_line}

必須条件：
- 絵文字・ハッシュタグを一切使わない
- 他の投稿・画像・URLへの言及なし
- 単体で完結する内容（続きを示唆しない）
- 10代後半〜30代女性が深夜に見て「わかる」と思える表現
- 業者・占い・勧誘の要素は絶対に含めない

テキストだけ出力（前置き・説明・かぎかっこ不要）："""

    text = _call_gemini(prompt)

    # クリーニング（万が一絵文字・ハッシュタグが入っても除去）
    text = re.sub(r"[#＃]\S+", "", text)
    text = re.sub(
        r"[\U0001F300-\U0001F64F\U0001F680-\U0001FAFF\u2600-\u27BF]",
        "", text
    )
    text = text.strip()

    return {
        "text": text,
        "category": category,
        "tone": tone,
        "format": fmt,
    }
