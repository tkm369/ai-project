import json
import os
import random
import time
from datetime import datetime
import pytz
from google import genai
from config import GEMINI_API_KEY, AFFILIATE_LINK, AFFILIATE_TEXT
from logger import get_top_posts, get_time_slot_performance, get_recent_posts_content, get_total_post_count
from trends import load_trends

# 12テーマのローテーション（累計投稿数 % 12 で順番に使い回す）
_CONTENT_CATEGORIES = [
    "復縁・別れた相手への未練と向き合い方",
    "片思い・好きな人の気持ちを読む方法",
    "運命の人・ソウルメイトとの出会いのサイン",
    "自己愛・自分を大切にすることで恋愛が変わる",
    "引き寄せ・願いを現実にするための思考法",
    "シンクロニシティ・繰り返し見る数字や出来事の意味",
    "別れと新しい始まり・前に進む勇気",
    "潜在意識・直感が教える本当の気持ち",
    "恋愛の不安と孤独・癒しのメッセージ",
    "開運・今すぐできる運気を上げる行動",
    "相手の本音・行動の裏に隠れた気持ち",
    "自分の魅力・まだ気づいていない内側の輝き",
]

# スパム防止：CTAをローテーションして毎回同じにならないようにする
_CTA_OPTIONS = [
    "あなたにも、こんな瞬間ありますか？",
    "この感覚、なんとなくわかる気がしませんか？",
    "今のあなたに、少しでも届いていたら嬉しいです。",
    "この言葉が、誰かの心に触れますように。",
    "今夜、自分の気持ちと向き合ってみてください。",
    "このメッセージ、あなたへのものかもしれません。",
    "あなたは今、どんな気持ちですか？",
    "ふと思い出したとき、また読み返してみてください。",
    "あなたの毎日が、少しでも穏やかでありますように。",
    "こんな気持ち、あなたにも覚えがありますか？",
    "今日も、あなたらしくいてください。",
    "この言葉が、今日の背中を少し押せたら嬉しいです。",
]

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _load_reference_posts():
    """ユーザーが手動で追加した参考投稿を読み込む"""
    path = os.path.join(os.path.dirname(__file__), "reference_posts.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if isinstance(p, str) and p.strip()]
    except Exception:
        return []


def _load_hashtag_stats():
    """ハッシュタグ実績データを読み込む"""
    path = os.path.join(os.path.dirname(__file__), "hashtag_stats.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
MODEL = "gemini-2.5-flash"
# Free tier: 5 RPM → 12秒以上の間隔を空ける
_CALL_INTERVAL = 13  # seconds between API calls


FALLBACK_MODEL = "gemini-2.0-flash"  # 2.5-flashが落ちたときのフォールバック


def _generate(prompt, max_retries=4):
    """レート制限・503を考慮してAPIを呼び出す（リトライ＋フォールバック付き）"""
    import re
    time.sleep(_CALL_INTERVAL)
    use_model = MODEL
    for attempt in range(max_retries):
        try:
            response = _get_client().models.generate_content(model=use_model, contents=prompt)
            return response.text.strip()
        except Exception as e:
            err_str = str(e)

            # 日次クォータ超過は即終了
            if ("PerDay" in err_str or "per_day" in err_str.lower()
                    or "GenerateRequestsPerDay" in err_str):
                print(f"  日次クォータ超過のため処理を終了します")
                raise

            # 429 RPM制限 → 待機してリトライ
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                m = re.search(r"retry in (\d+)", err_str)
                wait = int(m.group(1)) + 5 if m else 65
                print(f"  レート制限 (429)、{wait}秒待機後リトライ ({attempt+1}/{max_retries})")
                time.sleep(wait)

            # 503 高負荷 → まず同じモデルで2回待機リトライ、それでもダメならフォールバック
            # （503は一時的な過負荷のためフォールバックのクォータを使わない）
            elif "503" in err_str or "UNAVAILABLE" in err_str:
                if attempt < 2:
                    wait = 30 * (attempt + 1)
                    print(f"  Gemini 503 高負荷、{wait}秒待機後リトライ ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                elif use_model != FALLBACK_MODEL:
                    print(f"  Gemini 503 継続 → {FALLBACK_MODEL} にフォールバック")
                    use_model = FALLBACK_MODEL
                else:
                    time.sleep(30)

            else:
                raise

    raise RuntimeError(f"Gemini API {max_retries}回試行後も失敗しました")


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


def generate_and_score_posts(platform="x", top_posts=None, target_chars=None):
    """3つの投稿案を生成してスコアリングも一回のAPI呼び出しで行う"""
    time_slot, theme = get_time_theme()
    if platform == "x":
        max_chars = 240
    elif target_chars:
        max_chars = target_chars
    else:
        max_chars = 400

    # 参考投稿（ユーザー手動追加）
    reference_posts = _load_reference_posts()
    reference_section = ""
    if reference_posts:
        lines = ["【参考：他の人気投稿（書き出し・構成・トーンを学習すること）】"]
        for p in reference_posts:
            lines.append(f"---\n{p[:200]}")
        lines.append("---\nこれらの投稿のリズム・言葉選び・構成を参考にしつつ、内容は独自のものにしてください。")
        reference_section = "\n" + "\n".join(lines) + "\n"

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

    # ハッシュタグ実績注入
    hashtag_stats = _load_hashtag_stats()
    hashtag_section = ""
    if hashtag_stats:
        top_tags = [(t, v) for t, v in list(hashtag_stats.items())[:10]
                    if v.get("count", 0) >= 2]
        if top_tags:
            lines = ["【実績データに基づく効果的なハッシュタグ（エンゲージ率順）】"]
            for tag, v in top_tags[:8]:
                lines.append(f"  {tag}: 平均 {v['avg_rate']:.2%} (n={v['count']})")
            lines.append("→ これらのタグを優先使用し、実績のないタグは減らしてください。")
            hashtag_section = "\n" + "\n".join(lines) + "\n"

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

    # CTAをランダムに選んで毎回変える（スパム防止）
    chosen_cta = random.choice(_CTA_OPTIONS)
    jst = pytz.timezone("Asia/Tokyo")
    today_str = datetime.now(jst).strftime("%Y年%m月%d日")

    # テーマローテーション（累計投稿数で順番に切り替え）
    total = get_total_post_count()
    assigned_category = _CONTENT_CATEGORIES[total % len(_CONTENT_CATEGORIES)]

    # 直近の投稿を取得して重複回避指示に使う
    recent_contents = get_recent_posts_content(n=7)
    recent_section = ""
    if recent_contents:
        lines = ["【直近の投稿（これらと似た内容・書き出し・構成を使うことを厳禁）】"]
        for c in recent_contents:
            lines.append(f"・{c}…")
        recent_section = "\n" + "\n".join(lines) + "\n"

    if AFFILIATE_LINK:
        cta_instruction = f'- 最後に「{AFFILIATE_TEXT} {AFFILIATE_LINK}」を自然に含める'
    else:
        cta_instruction = f'- 末尾は必ずこのCTAで締める（変更厳禁）:「{chosen_cta}」\n- URLもリンクもプレースホルダーも絶対に入れない'

    prompt = f"""あなたはフォロワーを惹きつける人気SNS占い師です。
今日は{today_str}です。
今回のテーマ：「{assigned_category}」（時間帯の雰囲気：{theme}）
{platform}用の投稿を3案作成し、各案のエンゲージメントスコア(0-100)を付けてください。
{recent_section}{reference_section}{top_posts_section}{time_perf_section}{hashtag_section}{trends_section}
【投稿必須条件】
- テーマ「{assigned_category}」に沿った内容にする
- 1行目で読者がスクロールを止めるような「フック」を入れる
- 読者が「自分のことだ」と感じる共感ワードを使う
- 3案それぞれ、書き出し・構成・アプローチを完全に変える
{cta_instruction}
- {max_chars}文字以内
- 絵文字を効果的に使う（多すぎない）
- ハッシュタグは一切入れない

【コンテンツ多様性条件（最重要）】
- 直近の投稿リストと同じ書き出し・同じ構成・同じテーマを絶対に使わない
- 「コメントで教えてください」「コメントで教えてくださいね」は絶対に使わない
- 3案それぞれ異なる感情・角度・切り口で書く（同じトーンで3案書かない）

【NG条件（必ず守ること）】
- 実在の芸能人・著名人・一般人の名前を出さない
- 特定の宗教・宗派・団体名を出さない
- 「必ず○○になる」「100%」など断定的すぎる運勢の保証をしない
- 違法行為・危険な行為を連想させる表現を使わない
- 差別・誹謗中傷につながる表現を使わない

【スパム判定回避（最重要）】
- 「いいね」「フォロー」「保存」「シェア」を求める表現は絶対に使わない
- 「コメントで教えて」も絶対に使わない（エンゲージメントベイト）
- 冒頭を【】の括弧書きで始めない（例:【緊急】【確信】【警告】は全てNG）
- 毎回同じ書き出しパターンにならないよう、3案それぞれ全く異なる文体・切り口にする
- 宣伝・勧誘・販促を連想させる表現を避け、あくまで「個人の想いや気づきの共有」として書く

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
        return best_post, best_score
    except Exception:
        # JSON解析失敗時は生テキストをそのまま使う
        print(f"  [{platform}] スコアリング解析失敗、生テキスト使用")
        return text, 50


def improve_post(post, platform="x", target_chars=None):
    """最高スコア投稿をさらに磨く"""
    if platform == "x":
        max_chars = 240
    elif target_chars:
        max_chars = target_chars
    else:
        max_chars = 400

    chosen_cta = random.choice(_CTA_OPTIONS)
    if AFFILIATE_LINK:
        cta_improve = "- CTAのアフィリリンクへの誘導をより自然で背中を押す表現にする"
    else:
        cta_improve = f'- 末尾のCTAは必ず「{chosen_cta}」にする（他の表現に変えない）\n- URLもリンクもプレースホルダーも「コメントで教えてください」も絶対に入れない'

    prompt = f"""以下のSNS占い投稿をより魅力的に改善してください。

【改善ポイント】
- 1行目のフックをさらに強烈にする（数字・疑問・断言のどれかを使う）
- 中間部分に「共感→希望」の流れを作る
{cta_improve}
- {max_chars}文字以内に必ず収める
- ハッシュタグは一切入れない

【元の投稿】
{post}

【NG条件（改善後も必ず守ること）】
- 実在の芸能人・著名人の名前を出さない / 特定宗教・団体名を出さない
- 「必ず○○になる」など断定的すぎる保証をしない / 違法・差別的表現を使わない
- 「いいね」「フォロー」「保存」「シェア」「コメントで教えて」は絶対に入れない
- 冒頭を【】括弧書きで始めない / 宣伝・販促を連想させる表現を避ける

改善後の投稿のみ返してください（説明・コメント不要）:"""

    return _generate(prompt)


def get_best_post(platform="x", target_chars=None):
    """生成→スコアリング→改善の全フローを実行（API呼び出し2回）
    Gemini quota超過時はフォールバックテンプレートを使用して必ず投稿できるようにする
    """
    print(f"  [{platform}] 投稿案を生成・スコアリング中...")

    try:
        top_posts = get_top_posts(n=3, has_affiliate=bool(AFFILIATE_LINK))
        best_post, score = generate_and_score_posts(platform, top_posts=top_posts, target_chars=target_chars)
        print(f"  [{platform}] 投稿を改善中...")
        final_post = improve_post(best_post, platform, target_chars=target_chars)
        return final_post, score

    except Exception as e:
        err_str = str(e)
        is_quota = (
            "PerDay" in err_str or "per_day" in err_str.lower()
            or "GenerateRequestsPerDay" in err_str
            or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()
        )
        if is_quota:
            print(f"  ⚠️  Gemini quota超過 → フォールバックテンプレートを使用")
            from fallback_posts import get_fallback_post
            return get_fallback_post(), 70  # スコア70として扱う
        raise
