import json
import time
from datetime import datetime
import pytz
from google import genai
from config import GEMINI_API_KEY, AFFILIATE_LINK, AFFILIATE_TEXT

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash"
# Free tier: 5 RPM → 12秒以上の間隔を空ける
_CALL_INTERVAL = 13  # seconds between API calls


def _generate(prompt, max_retries=3):
    """レート制限を考慮してAPIを呼び出す（リトライ付き）"""
    time.sleep(_CALL_INTERVAL)
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL, contents=prompt)
            return response.text.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # retry_delay をエラーメッセージから抽出
                import re
                m = re.search(r"retry in (\d+)", err_str)
                wait = int(m.group(1)) + 5 if m else 65
                print(f"  レート制限 (429)、{wait}秒待機後リトライ ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    # 最終試行
    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text.strip()


def get_time_theme():
    """時間帯に応じたテーマを返す"""
    jst = pytz.timezone("Asia/Tokyo")
    hour = datetime.now(jst).hour

    if 5 <= hour < 12:
        return "朝", "今日の恋愛運・朝の開運メッセージ・今日意識すべきこと"
    elif 12 <= hour < 18:
        return "昼", "午後の恋愛エネルギー・今日の星座運勢・気になる人との関係"
    else:
        return "夜", "明日の恋愛運・夜の浄化メッセージ・魂が求めているもの"


def generate_and_score_posts(platform="x"):
    """3つの投稿案を生成してスコアリングも一回のAPI呼び出しで行う"""
    _, theme = get_time_theme()
    max_chars = 240 if platform == "x" else 450

    prompt = f"""あなたはフォロワーを惹きつける人気SNS占い師です。
「{theme}」というテーマで、{platform}用の投稿を3案作成し、各案のエンゲージメントスコア(0-100)を付けてください。

【投稿必須条件】
- 占い・スピリチュアル・恋愛運に関する内容
- 1行目で読者がスクロールを止めるような「フック」を入れる
- 読者が「自分のことだ」と感じる共感ワードを使う
- 最後に「{AFFILIATE_TEXT} {AFFILIATE_LINK}」を自然に含める
- {max_chars}文字以内
- 絵文字を効果的に使う（多すぎない）
- ハッシュタグを末尾に4〜6個（#占い #恋愛運 #スピリチュアル #開運 など）

以下のJSON形式のみで返してください（説明不要）:
[
  {{"score": 数字, "post": "投稿内容"}},
  {{"score": 数字, "post": "投稿内容"}},
  {{"score": 数字, "post": "投稿内容"}}
]"""

    text = _generate(prompt)
    try:
        start = text.find("[")
        end = text.rfind("]") + 1
        results = json.loads(text[start:end])
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        best_score = results[0].get("score", 50)
        best_post = results[0].get("post", "")
        print(f"  [{platform}] 最高スコア: {best_score}/100")
        return best_post
    except Exception:
        # JSON解析失敗時は生テキストをそのまま使う
        print(f"  [{platform}] スコアリング解析失敗、生テキスト使用")
        return text


def improve_post(post, platform="x"):
    """最高スコア投稿をさらに磨く"""
    max_chars = 240 if platform == "x" else 450

    prompt = f"""以下のSNS占い投稿をより魅力的に改善してください。

【改善ポイント】
- 1行目のフックをさらに強烈にする（数字・疑問・断言のどれかを使う）
- 中間部分に「共感→希望」の流れを作る
- CTAをより自然で背中を押す表現にする
- {max_chars}文字以内に必ず収める
- ハッシュタグは末尾にまとめる

【元の投稿】
{post}

改善後の投稿のみ返してください（説明・コメント不要）:"""

    return _generate(prompt)


def get_best_post(platform="x"):
    """生成→スコアリング→改善の全フローを実行（API呼び出し2回）"""
    print(f"  [{platform}] 投稿案を生成・スコアリング中...")
    best_post = generate_and_score_posts(platform)

    print(f"  [{platform}] 投稿を改善中...")
    final_post = improve_post(best_post, platform)

    return final_post
