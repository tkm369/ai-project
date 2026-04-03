import json
import time
from datetime import datetime
import pytz
from google import genai
from config import GEMINI_API_KEY, AFFILIATE_LINK, AFFILIATE_TEXT
from logger import get_top_posts, get_time_slot_performance
from trends import load_trends

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
                # 日次クォータ超過（PerDay）はリトライしても無意味なので即re-raise
                if "PerDay" in err_str or "per_day" in err_str.lower() or "GenerateRequestsPerDay" in err_str:
                    print(f"  日次クォータ超過のため処理を終了します")
                    raise
                # RPM制限の場合はwaitしてリトライ
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
    """現在時刻を2時間バケットのスロットキーに変換しテーマを返す（12スロット対応）"""
    jst = pytz.timezone("Asia/Tokyo")
    hour = datetime.now(jst).hour
    bucket = (hour // 2) * 2  # 偶数時刻に丸める
    slot_key = f"{bucket:02d}"  # "00","02"..."22"

    themes = {
        "00": "深夜の気づき・潜在意識のメッセージ・魂が囁くこと",
        "02": "夜明け前の覚醒・運命の転換期・スピリチュアルな目醒め",
        "04": "夜明けの開運・新しい一日へのメッセージ",
        "06": "朝の光の恋愛運・今日を制するキーワード",
        "08": "朝活エネルギー・星座運勢・気になる人へのアクション",
        "10": "午前の引き寄せサイン・今日のターニングポイント",
        "12": "昼の恋愛エネルギー・午後の流れを読む",
        "14": "午後の開運タイム・ハートを開くメッセージ",
        "16": "夕方前のエネルギー・今日の振り返り・夕暮れのサイン",
        "18": "夕暮れの恋愛運・今夜の出会い・引き寄せの時間帯",
        "20": "夜の星占い・明日の恋愛運・夜のスピリチュアルメッセージ",
        "22": "夜の浄化・深夜前のメッセージ・魂が求めているもの",
    }
    theme = themes.get(slot_key, "恋愛運・スピリチュアルメッセージ・開運")
    return slot_key, theme


def generate_and_score_posts(platform="x", top_posts=None):
    """3つの投稿案を生成してスコアリングも一回のAPI呼び出しで行う"""
    time_slot, theme = get_time_theme()
    max_chars = 240 if platform == "x" else 450

    top_posts_section = ""
    if top_posts:
        lines = ["【参考：過去に高エンゲージメントを記録した投稿パターン】"]
        for p in top_posts:
            rate = p["metrics"].get("engagement_rate", 0)
            lines.append(f'{p["content"][:100]}... (engagement_rate: {rate:.2%})')
        lines.append("これらの投稿の特徴（書き出し・構成・トーン）を参考にしてください。")
        top_posts_section = "\n" + "\n".join(lines) + "\n"

    # 時間帯別パフォーマンスを注入
    time_perf = get_time_slot_performance()
    time_perf_section = ""
    if time_perf:
        sorted_slots = sorted(time_perf.items(), key=lambda x: x[1], reverse=True)
        best = sorted_slots[0]
        current_avg = time_perf.get(time_slot)
        lines = ["【時間帯別エンゲージメント実績】"]
        for slot, avg in sorted_slots:
            marker = " ← 現在" if slot == time_slot else ""
            lines.append(f"  {slot}: 平均 {avg:.2%}{marker}")
        if current_avg is not None:
            if time_slot == best[0]:
                lines.append(f"この時間帯（{time_slot}）は最もエンゲージが高い。その強みを活かして。")
            else:
                lines.append(f"この時間帯（{time_slot}）のエンゲージを{best[0]}並みに引き上げるよう工夫してください。")
        time_perf_section = "\n" + "\n".join(lines) + "\n"

    # トレンド注入
    trends = load_trends()
    trends_section = ""
    if trends:
        lines = ["【今日のトレンド（投稿に自然に絡めるとバズりやすい）】"]
        if trends.get("genre_trends"):
            lines.append(f"占い・恋愛ジャンルの注目ワード: {', '.join(trends['genre_trends'][:6])}")
        if trends.get("trending_now"):
            lines.append(f"日本のトレンド（フックに使えそうなもの）: {', '.join(trends['trending_now'][:5])}")
        lines.append("※ 無理に全部入れず、自然に絡められるものだけ使うこと")
        trends_section = "\n" + "\n".join(lines) + "\n"

    if AFFILIATE_LINK:
        cta_instruction = f'- 最後に「{AFFILIATE_TEXT} {AFFILIATE_LINK}」を自然に含める'
    else:
        cta_instruction = "- 末尾にCTAやプロフ誘導は入れない。代わりに「あなたはどうですか？」「コメントで教えて」など読者が反応したくなる一言で締める（URLもリンクもプレースホルダーも絶対に入れない）"

    prompt = f"""あなたはフォロワーを惹きつける人気SNS占い師です。
「{theme}」というテーマで、{platform}用の投稿を3案作成し、各案のエンゲージメントスコア(0-100)を付けてください。
{top_posts_section}{time_perf_section}{trends_section}
【投稿必須条件】
- 占い・スピリチュアル・恋愛運に関する内容
- 1行目で読者がスクロールを止めるような「フック」を入れる
- 読者が「自分のことだ」と感じる共感ワードを使う
{cta_instruction}
- {max_chars}文字以内
- 絵文字を効果的に使う（多すぎない）
- ハッシュタグを末尾に4〜6個（#占い #恋愛運 #スピリチュアル #開運 など）

【NG条件（必ず守ること）】
- 実在の芸能人・著名人・一般人の名前を出さない
- 特定の宗教・宗派・団体名を出さない
- 「必ず○○になる」「100%」など断定的すぎる運勢の保証をしない
- 違法行為・危険な行為を連想させる表現を使わない
- 差別・誹謗中傷につながる表現を使わない

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

    if AFFILIATE_LINK:
        cta_improve = "- CTAのアフィリリンクへの誘導をより自然で背中を押す表現にする"
    else:
        cta_improve = "- CTAやプロフ誘導は入れない。末尾を「あなたはどう？」「コメントで教えて」など読者が反応・保存したくなる締め方に変える（URLもリンクもプレースホルダーも絶対に入れない）"

    prompt = f"""以下のSNS占い投稿をより魅力的に改善してください。

【改善ポイント】
- 1行目のフックをさらに強烈にする（数字・疑問・断言のどれかを使う）
- 中間部分に「共感→希望」の流れを作る
{cta_improve}
- {max_chars}文字以内に必ず収める
- ハッシュタグは末尾にまとめる

【元の投稿】
{post}

【NG条件（改善後も必ず守ること）】
- 実在の芸能人・著名人の名前を出さない / 特定宗教・団体名を出さない
- 「必ず○○になる」など断定的すぎる保証をしない / 違法・差別的表現を使わない

改善後の投稿のみ返してください（説明・コメント不要）:"""

    return _generate(prompt)


def get_best_post(platform="x"):
    """生成→スコアリング→改善の全フローを実行（API呼び出し2回）"""
    print(f"  [{platform}] 投稿案を生成・スコアリング中...")

    top_posts = get_top_posts(n=3, has_affiliate=bool(AFFILIATE_LINK))
    best_post = generate_and_score_posts(platform, top_posts=top_posts)

    print(f"  [{platform}] 投稿を改善中...")
    final_post = improve_post(best_post, platform)

    return final_post
