import json
from datetime import datetime
import pytz
from google import genai
from config import GEMINI_API_KEY, AFFILIATE_LINK, AFFILIATE_TEXT

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash"


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


def generate_posts(platform="x"):
    """3つの投稿案を生成"""
    _, theme = get_time_theme()
    max_chars = 240 if platform == "x" else 450

    prompt = f"""あなたはフォロワーを惹きつける人気SNS占い師です。
「{theme}」というテーマで、{platform}用の投稿を3案作成してください。

【必須条件】
- 占い・スピリチュアル・恋愛運に関する内容
- 1行目で読者がスクロールを止めるような「フック」を入れる
- 読者が「自分のことだ」と感じる共感ワードを使う
- 最後に「{AFFILIATE_TEXT} {AFFILIATE_LINK}」を自然に含める
- {max_chars}文字以内
- 絵文字を効果的に使う（多すぎない）
- ハッシュタグを末尾に4〜6個（#占い #恋愛運 #スピリチュアル #開運 など）

【投稿3案を「---」で区切って出力してください】"""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    posts = response.text.strip().split("---")
    posts = [p.strip() for p in posts if len(p.strip()) > 20]
    return posts[:3]


def score_post(post):
    """エンゲージメントスコアを0〜100で評価"""
    prompt = f"""以下のSNS占い投稿のエンゲージメント予測スコアを評価してください。

【評価基準】
- 感情的共鳴度（読者が「わかる」と感じるか）
- 拡散されやすさ（保存・シェアしたくなるか）
- コメント誘発度（返信したくなるか）
- アフィリンクへの誘導の自然さ

【投稿】
{post}

以下のJSON形式のみで返してください（説明不要）:
{{"score": 数字, "reason": "一言"}}"""

    response = client.models.generate_content(model=MODEL, contents=prompt)
    try:
        text = response.text
        start = text.find("{")
        end = text.rfind("}") + 1
        result = json.loads(text[start:end])
        return result.get("score", 50)
    except Exception:
        return 50


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

    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text.strip()


def get_best_post(platform="x"):
    """生成→スコアリング→改善の全フローを実行"""
    print(f"  [{platform}] 投稿案を3つ生成中...")
    posts = generate_posts(platform)

    print(f"  [{platform}] スコアリング中...")
    scored = [(post, score_post(post)) for post in posts]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_post, best_score = scored[0]
    print(f"  [{platform}] 最高スコア: {best_score}/100")

    print(f"  [{platform}] 投稿を改善中...")
    final_post = improve_post(best_post, platform)

    return final_post
