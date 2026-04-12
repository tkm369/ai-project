"""
text_improver.py - Gemini APIでThreadsの投稿テキストを少し改良する
"""
import os
import json
import re
import urllib.request


def remove_emoji(text: str) -> str:
    """絵文字・特殊記号を除去する"""
    # Unicode絵文字の範囲を除去
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # 顔文字
        "\U0001F300-\U0001F5FF"  # 記号・絵文字
        "\U0001F680-\U0001F6FF"  # 乗り物・場所
        "\U0001F700-\U0001F77F"  # 錬金術記号
        "\U0001F780-\U0001F7FF"  # 幾何学図形
        "\U0001F800-\U0001F8FF"  # 補助矢印
        "\U0001F900-\U0001F9FF"  # 補助記号・絵文字
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub("", text).strip()


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ---- キーワードベースの即NG判定（Gemini前に確実に弾く） ----
_NG_PATTERNS = [
    # 占い師・スピリチュアル業者の宣伝
    r"鑑定", r"霊視", r"占い師", r"セッション", r"視ます", r"視させて",
    r"鑑定士", r"スピリチュアルカウンセラー", r"カウンセリング",
    # 集客・誘導
    r"DMください", r"DM下さい", r"LINE登録", r"プロフのリンク", r"無料相談",
    r"フォローで", r"いいねで", r"RTで", r"リポストで",
    r"運気UP", r"運気アップ", r"恋愛成就率", r"成就率",
    # リプライ・反応系（短すぎる内容）
    r"^わかる$", r"^それな$", r"^泣ける$", r"^頑張れ$", r"^応援$",
    # 番号・日付のみ系
    r"^\d+/\d+\s",  # 「1/19 ○○占い」パターン
    # 無関係ジャンル
    r"副業", r"稼ぎ", r"月収", r"収益化", r"アフィリ",
    # 画像・スクリーンショット依存の投稿（テキストだけでは意味不明になる）
    r"送ってくれたLINE", r"くれたLINE", r"もらったLINE",
    r"このLINE", r"そのLINE", r"のLINE[。．\.\s]",
    r"このメッセージ", r"このDM", r"このスクリーンショット",
    r"この言葉[。．\.\s]", r"この一言[。．\.\s]",
    r"↓$", r"↓\s*$",  # 「↓」で終わる（画像を指している）
    r"写真$", r"画像$", r"スクショ",
    r"見てください$", r"見てほしい$",
]
_NG_REGEX = re.compile("|".join(_NG_PATTERNS))

# テキストが短すぎる（20文字未満）はNG
_MIN_TEXT_LENGTH = 20


def is_blocked_by_keyword(text: str) -> bool:
    """キーワード・パターンで即NGか判定（Gemini不要の確実フィルター）"""
    if len(text.strip()) < _MIN_TEXT_LENGTH:
        return True
    if _NG_REGEX.search(text):
        return True
    return False
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def _get_style_hint() -> str:
    try:
        import config
        return config.CONTENT_STYLE_HINT or ""
    except Exception:
        return ""


def improve_text(original_text: str) -> str:
    """
    Gemini APIで投稿テキストを改良して返す。
    APIキーがない場合はそのまま返す。
    """
    if not GEMINI_API_KEY:
        return original_text

    style_hint = _get_style_hint()
    style_section = f"\n- {style_hint}" if style_hint else ""

    prompt = f"""あなたはTikTokバズ専門のコピーライターです。
以下は復縁・恋愛ジャンルのSNS投稿テキストです。
TikTokの視聴者が思わず「わかる」「続きを見たい」と感じるような、感情に刺さる投稿文に書き直してください。

ルール：
- 核となる感情・体験は維持する
- 共感・感情的な言葉で書く（「わかる」「それな」「泣きそう」など）
- 読み手が自分のことのように感じる一人称・共感スタイルにする
- 150文字程度、改行を入れて読みやすく
- 必ず最後まで完結させる
- RTいいね懇願・占いURL・数字ランキングは削除する
- 絵文字・特殊記号は一切使わない{style_section}
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
            if not improved:
                return remove_emoji(original_text)
            improved = remove_emoji(improved)
            # 文末が句読点・感嘆符・疑問符で終わっていない場合は元テキストを使用
            if not improved or improved[-1] not in ("。", "！", "？", "!", "?", "…"):
                return remove_emoji(original_text)
            return improved
    except Exception:
        return original_text


def is_valid_post(text: str) -> bool:
    """
    投稿テキストが適切かを判定。
    1) キーワードフィルター（確実・即判定）
    2) Gemini判定（文脈・意味の判断）
    """
    # キーワードで即NG
    if is_blocked_by_keyword(text):
        return False

    if not GEMINI_API_KEY:
        return True

    prompt = f"""以下のテキストが、TikTok投稿として単体でコンテンツ価値があるか判定してください。

OK（価値あり）：
- 復縁・恋愛・感情・スピリチュアルに関する体験・気持ち・気づきが書かれている
- 読んだ人が共感・感情移入できる内容

NG（投稿しない）：
- 占い師・スピリチュアル系のサービス宣伝（「霊視します」「鑑定します」「占います」「視ます」「セッションします」「鑑定受付中」）
- 「いいね・RT・フォローで運気UP」などエンゲージメントバイト
- 「DMください」「LINE登録」「プロフのリンク」「無料相談」などリンク・集客誘導
- 一言の浅い質問（「眠れてますか？」「好きですか？」だけなど）
- 返信・リアクションのみ（「わかる」「頑張れ」「俺も」等）
- 意味不明・文脈なしでは理解できない断片
- 日付・番号・英数字のみ（「1/19」「No.1」等）
- 無関係ジャンル（グルメ・スポーツ・政治等）
- 自分のアカウント・サービスへの誘導を含む宣伝投稿

テキスト：
{text[:200]}

OKまたはNGの1単語だけ返してください。"""

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 5, "temperature": 0.1}
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
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
            return "OK" in result
    except Exception:
        return True  # エラー時はスキップしない


if __name__ == "__main__":
    sample = "自己中じゃ表しきれない無責任自己中な彼にムカついている。"
    print("元:", sample)
    print("改良:", improve_text(sample))
    print("判定:", is_valid_post(sample))
