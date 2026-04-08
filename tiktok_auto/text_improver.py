"""
text_improver.py - Gemini APIでThreadsの投稿テキストを少し改良する
"""
import os
import json
import urllib.request


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def improve_text(original_text: str) -> str:
    """
    Gemini APIで投稿テキストを改良して返す。
    APIキーがない場合はそのまま返す。
    """
    if not GEMINI_API_KEY:
        return original_text

    prompt = f"""以下は復縁・恋愛ジャンルのSNS投稿テキストです。
元の意味・感情・口調を維持したまま、TikTokで読まれやすいように少しだけ改良してください。

ルール：
- 元のテキストの意味を変えない
- 文体・口調はそのまま
- 読みやすく自然な日本語に整える
- 必ず文章を最後まで完結させること（途中で切らない）
- 150文字程度を目安にする
- 改行は適切に入れる
- 改良後のテキストだけを返す（説明不要）

元のテキスト：
{original_text[:400]}"""

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.7}
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read())
            improved = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return improved if improved else original_text
    except Exception:
        return original_text


if __name__ == "__main__":
    sample = "自己中じゃ表しきれない無責任自己中な彼にムカついている。"
    print("元:", sample)
    print("改良:", improve_text(sample))
