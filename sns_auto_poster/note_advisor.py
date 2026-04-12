"""
Note販売アドバイザー
- Threadsのフォロワー数・エンゲージデータを自動分析
- 「今週売れそうなNote」を3件提案してDiscordに通知
- 選ばれた提案からNote記事全文を生成
"""
import json
import os
import requests
from datetime import datetime
import pytz

from config import THREADS_ACCESS_TOKEN, THREADS_USER_ID, GEMINI_API_KEY
from logger import load_log
from discord_notifier import _send

PROPOSALS_FILE = os.path.join(os.path.dirname(__file__), "note_proposals.json")


# ─────────────────────────────────────────
# Threads フォロワー数取得
# ─────────────────────────────────────────
def fetch_follower_count() -> int:
    """Threads APIからフォロワー数を取得"""
    try:
        url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}"
        res = requests.get(url, params={
            "fields": "followers_count",
            "access_token": THREADS_ACCESS_TOKEN,
        }, timeout=10)
        data = res.json()
        count = data.get("followers_count", 0)
        print(f"  フォロワー数: {count}人")
        return count
    except Exception as e:
        print(f"  フォロワー取得失敗: {e}")
        return 0


# ─────────────────────────────────────────
# 高エンゲージ投稿の分析
# ─────────────────────────────────────────
def get_top_posts_for_note(n=10):
    """エンゲージ上位の投稿を返す"""
    log = load_log()
    scored = []
    for p in log:
        if p.get("platform") != "threads":
            continue
        if not p.get("metrics"):
            continue
        views = p["metrics"].get("views", 0)
        likes = p["metrics"].get("likes", 0)
        score = views + likes * 5
        if score > 0:
            scored.append({
                "text": p.get("content", ""),
                "views": views,
                "likes": likes,
                "score": score,
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:n]


# ─────────────────────────────────────────
# Note提案を生成
# ─────────────────────────────────────────
def generate_note_proposals(top_posts: list, follower_count: int) -> list:
    """高エンゲージ投稿を分析して3件のNote提案を生成"""
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    posts_text = "\n".join([
        f"- [{p['views']}views {p['likes']}likes] {p['text'][:80]}"
        for p in top_posts[:5]
    ])

    prompt = f"""あなたはスピリチュアル系コンテンツのマーケターです。

以下はThreadsで高エンゲージメントを得た投稿です：
{posts_text}

フォロワー数: {follower_count}人

この投稿を見ているユーザーが「お金を払ってでも読みたい」と思うnote記事を3件提案してください。

各提案をJSON配列で返してください：
[
  {{
    "title": "記事タイトル（魅力的で具体的に）",
    "description": "どんな内容か2〜3行で説明",
    "target": "こんな人に刺さる（ターゲット読者）",
    "price": 推奨価格（数字のみ、300〜980の範囲）,
    "why": "なぜ今これが売れるか（1行）"
  }},
  ...
]

JSONのみ返してください。説明不要。"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        text = response.text.strip()
        # JSONブロックを抽出
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        proposals = json.loads(text.strip())
        return proposals
    except Exception as e:
        print(f"  提案生成失敗: {e}")
        return []


# ─────────────────────────────────────────
# Discord に提案を通知
# ─────────────────────────────────────────
def notify_note_proposals(proposals: list, follower_count: int, top_posts: list):
    """Discord に今週のNote提案を送信"""
    if not proposals:
        return

    fields = []
    for i, p in enumerate(proposals, 1):
        fields.append({
            "name": f"💡 提案{i}：{p['title']}",
            "value": (
                f"📖 {p['description']}\n"
                f"👤 {p['target']}\n"
                f"💰 推奨価格: ¥{p['price']}\n"
                f"🔥 {p['why']}"
            ),
        })

    # 最高エンゲージ投稿サマリー
    if top_posts:
        best = top_posts[0]
        fields.append({
            "name": "📊 今週のトップ投稿",
            "value": f"{best['views']}views / {best['likes']}likes\n「{best['text'][:60]}…」",
        })

    payload = {
        "embeds": [{
            "title": f"📝 今週のNote販売提案（フォロワー {follower_count}人）",
            "color": 0x9B59B6,
            "fields": fields,
            "footer": {
                "text": f"作りたい提案があれば「提案Nを作って」と言ってください • {datetime.now().strftime('%Y-%m-%d')}"
            },
        }]
    }
    _send(payload)
    print("  Discord にNote提案を送信しました")


# ─────────────────────────────────────────
# 提案を保存・読み込み
# ─────────────────────────────────────────
def save_proposals(proposals: list):
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)


def load_proposals() -> list:
    if not os.path.exists(PROPOSALS_FILE):
        return []
    with open(PROPOSALS_FILE, encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────
# Note記事全文生成
# ─────────────────────────────────────────
def generate_note_article(proposal_index: int) -> str:
    """選ばれた提案からnote記事全文を生成"""
    proposals = load_proposals()
    if not proposals or proposal_index > len(proposals):
        return "提案が見つかりません。先に分析を実行してください。"

    proposal = proposals[proposal_index - 1]

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""あなたはスピリチュアル系コンテンツライターです。

以下の企画でnote記事を書いてください：

タイトル: {proposal['title']}
内容: {proposal['description']}
ターゲット: {proposal['target']}
推奨価格: ¥{proposal['price']}

【条件】
- 文字数: 2000〜3000文字
- 冒頭で読者の悩みに深く共感する（200文字）
- 具体的なアドバイス・方法を3〜5つ提示
- 各アドバイスに「なぜそうなのか」のスピリチュアルな根拠を添える
- 締めは希望を感じさせる言葉で
- 有料パートは「ここから有料」と書いた後に続ける（無料部分700文字 + 有料部分1500文字）
- 絵文字は控えめに
- 押しつけがましくない、寄り添うトーン

記事本文のみ返してください。"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        article = response.text.strip()
        return article
    except Exception as e:
        # quota超過時はgemini-2.0-flashで再試行
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash", contents=prompt
            )
            return response.text.strip()
        except Exception as e2:
            return f"記事生成失敗: {e2}"


def notify_note_article(proposal_index: int, article: str, proposal: dict):
    """生成した記事をDiscordに送信（長いので分割）"""
    title = proposal.get("title", f"提案{proposal_index}")
    price = proposal.get("price", "500")

    # 記事が長いのでDiscordの2000文字制限に合わせて分割
    chunks = [article[i:i+1800] for i in range(0, len(article), 1800)]

    # 1通目: タイトルと冒頭
    payload = {
        "embeds": [{
            "title": f"✍️ Note記事生成完了：{title}",
            "color": 0x2ECC71,
            "description": chunks[0],
            "footer": {"text": f"推奨価格: ¥{price} | note.comにコピペして公開してください"},
        }]
    }
    _send(payload)

    # 2通目以降
    for chunk in chunks[1:]:
        _send({"embeds": [{"description": chunk, "color": 0x2ECC71}]})

    print(f"  Discord にNote記事（{len(article)}文字）を送信しました")


# ─────────────────────────────────────────
# メイン実行
# ─────────────────────────────────────────
def run_weekly_analysis():
    """週次分析・提案生成（GitHub Actionsから呼ぶ）"""
    print("\n=== Note販売アドバイザー ===")

    follower_count = fetch_follower_count()
    top_posts = get_top_posts_for_note()

    if not top_posts:
        print("  エンゲージデータ不足 → スキップ")
        return

    print(f"  分析対象: {len(top_posts)}件の投稿")
    proposals = generate_note_proposals(top_posts, follower_count)

    if proposals:
        save_proposals(proposals)
        notify_note_proposals(proposals, follower_count, top_posts)
        print(f"  {len(proposals)}件の提案を生成・保存しました")
    else:
        print("  提案生成失敗")


def run_article_generation(proposal_index: int):
    """指定した提案でNote記事を生成（on demand）"""
    print(f"\n=== Note記事生成: 提案{proposal_index} ===")
    proposals = load_proposals()
    if not proposals:
        print("  提案なし。先に weekly_analysis を実行してください")
        return
    if proposal_index < 1 or proposal_index > len(proposals):
        print(f"  提案{proposal_index}は存在しません（1〜{len(proposals)}）")
        return

    proposal = proposals[proposal_index - 1]
    print(f"  タイトル: {proposal['title']}")
    article = generate_note_article(proposal_index)
    notify_note_article(proposal_index, article, proposal)
