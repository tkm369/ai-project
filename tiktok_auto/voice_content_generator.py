"""
voice_content_generator.py - 占い・相手の気持ち解説・アドバイス系の音声スクリプトを生成

対応フォーマット:
  fortune    - 占い・スピリチュアル系
  psychology - 相手の気持ち解説・心理分析系
  advice     - 恋愛アドバイス・ちゃんとした系
"""
import os
import json
import re
import random
import urllib.request
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

VOICE_FORMATS = ["fortune", "psychology", "advice"]

# フォーマット別のカテゴリ対応
VOICE_FORMAT_CATEGORIES = {
    "fortune":    ["片思い", "復縁", "好きな人", "恋愛あるある"],
    "psychology": ["元カレ元カノ", "失恋", "復縁", "好きな人"],
    "advice":     ["失恋", "片思い", "復縁", "寂しい夜"],
}

# フォーマット別タイトル一覧（voice_title カードに表示される）
TITLE_TEMPLATES = {
    "fortune": [
        "今週の恋愛運",
        "あなたの恋、こう動きます",
        "恋愛タロット占い",
        "今の恋が進展するサイン",
        "復縁できる人の特徴",
        "恋愛エネルギーの流れ",
        "今すぐ手放すべき恋愛のブロック",
    ],
    "psychology": [
        "元カレ・元カノが連絡しない本当の理由",
        "好きな人があなたを意識しているサイン",
        "復縁したい相手の心理",
        "既読スルーの本当の意味",
        "未練がある人がとる行動",
        "冷めたと思ったときの相手の本音",
        "好きな人が送るLINEの本当の意味",
    ],
    "advice": [
        "失恋から立ち直る方法",
        "片思いを成功させるコツ",
        "好きな人に連絡するタイミング",
        "復縁を引き寄せる考え方",
        "恋愛で傷ついた心の癒し方",
        "自分を好きになることが恋愛を変える",
        "依存しない恋愛のすすめ",
    ],
}

# フォーマット別ハッシュタグ
VOICE_HASHTAGS = {
    "fortune":    ["恋愛占い", "占い", "タロット", "恋愛運", "スピリチュアル", "恋愛", "深夜"],
    "psychology": ["恋愛心理", "心理学", "相手の気持ち", "恋愛あるある", "恋愛", "深夜"],
    "advice":     ["恋愛アドバイス", "失恋", "片思い", "恋愛相談", "共感", "恋愛", "深夜"],
}


def _call_gemini(prompt: str) -> str:
    from gemini_client import call_gemini
    return call_gemini(prompt, max_tokens=1500, temperature=0.85)


def _build_prompt(fmt: str, title: str, style_hint: str = "") -> str:
    """フォーマット別のGeminiプロンプトを組み立てる"""
    common = (
        f"あなたはTikTok向けの恋愛系音声コンテンツ（ナレーション脚本）を書くプロです。\n"
        f"テーマ: 「{title}」\n"
        f"{'スタイルのヒント: ' + style_hint if style_hint else ''}\n\n"
        "【絶対条件】\n"
        "- 自然な話し言葉（読み上げたとき60〜90秒になる量: 220〜360文字）\n"
        "- 感情に寄り添う温かいトーンで書く\n"
        "- 箇条書き・記号・改行多用は禁止（読み上げ用なので文章として繋がっていること）\n"
        "- タイトルや説明は不要、脚本テキストのみ出力\n\n"
    )

    if fmt == "fortune":
        return (
            common +
            "【スタイル: 占い・スピリチュアル系】\n"
            "スピリチュアルな世界観で、聴いた人が希望を感じられるナレーションを書いてください。\n"
            "「あなたの恋愛には〜のエネルギーが流れています」\n"
            "「宇宙があなたに〜を示しています」のような表現を自然に使いながら、\n"
            "最後は前向きなメッセージで締めてください。\n"
            "脚本テキストのみ出力してください。"
        )
    elif fmt == "psychology":
        return (
            common +
            "【スタイル: 相手の気持ち解説・心理分析系】\n"
            "心理学・行動分析の視点から、相手の気持ちをわかりやすく解説するナレーションを書いてください。\n"
            "「〜という行動には、実は〜という心理があります」という構成を意識し、\n"
            "聴き手が「あ、そういうことか」と腑に落ちる内容にしてください。\n"
            "共感できる具体的なエピソードを1つ入れてください。\n"
            "脚本テキストのみ出力してください。"
        )
    else:  # advice
        return (
            common +
            "【スタイル: 恋愛アドバイス・ちゃんとした系】\n"
            "温かく寄り添うアドバイザーとして、実践的で心に刺さるアドバイスを書いてください。\n"
            "「〜で悩んでいるあなたへ」から始め、具体的なアドバイスを2つ伝えて、\n"
            "最後は「あなたなら大丈夫」という励ましで締めてください。\n"
            "脚本テキストのみ出力してください。"
        )


def _pick_voice_format(strategy: dict) -> str:
    """strategy の voice_format_weights を使ってフォーマットを選ぶ"""
    weights = strategy.get("voice_format_weights", {}) if strategy else {}
    w = [max(weights.get(f, 1.0), 0.1) for f in VOICE_FORMATS]
    total = sum(w)
    r = random.random() * total
    cum = 0.0
    for fmt, wi in zip(VOICE_FORMATS, w):
        cum += wi
        if r < cum:
            return fmt
    return VOICE_FORMATS[-1]


def generate_voice_content(strategy: dict = None, voice_format: str = None) -> dict:
    """
    音声コンテンツのスクリプトを生成して返す。

    Returns:
        {
            "content_type":  "voice",
            "voice_format":  "fortune" | "psychology" | "advice",
            "title":         "タイトルカードに表示する文字列",
            "script":        "読み上げ用テキスト（220〜360文字）",
            "category":      "TikTokカテゴリ（ハッシュタグ用）",
        }
    """
    if voice_format is None:
        voice_format = _pick_voice_format(strategy)

    category = random.choice(VOICE_FORMAT_CATEGORIES.get(voice_format, ["失恋"]))
    title    = random.choice(TITLE_TEMPLATES.get(voice_format, ["恋愛について"]))

    style_hint = ""
    if strategy:
        style_hint = strategy.get("generation_params", {}).get("content_style_hint", "")

    prompt = _build_prompt(voice_format, title, style_hint)

    logger.info(f"音声スクリプト生成: [{voice_format}] {title}")
    script = _call_gemini(prompt)

    # 不要な記号・マークダウンを除去
    script = re.sub(r'[#＃*＊「」【】\[\]（）()]', '', script)
    script = re.sub(r'\n{3,}', '\n\n', script).strip()

    logger.info(f"スクリプト生成完了: {len(script)}文字")
    if len(script) < 50:
        raise ValueError(f"スクリプトが短すぎる: {len(script)}文字")

    return {
        "content_type": "voice",
        "voice_format": voice_format,
        "title":        title,
        "script":       script,
        "category":     category,
    }


def get_voice_hashtags(voice_format: str, category: str) -> str:
    """音声投稿用のハッシュタグ文字列を返す"""
    tags = list(VOICE_HASHTAGS.get(voice_format, ["恋愛", "深夜"]))
    return " ".join(f"#{t}" for t in tags)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    fmt = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        result = generate_voice_content(voice_format=fmt)
        print(f"\n=== フォーマット: {result['voice_format']} ===")
        print(f"タイトル: {result['title']}")
        print(f"カテゴリ: {result['category']}")
        print(f"スクリプト ({len(result['script'])}文字):")
        print(result['script'])
    except Exception as e:
        print(f"エラー: {e}")
