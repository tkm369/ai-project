"""
script_generator.py — Claude APIでスピ系YouTube台本を生成
video_types.VideoType を受け取って型別プロンプトで生成する
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from config import ANTHROPIC_API_KEY, GEMINI_API_KEY, LLM_BACKEND

if TYPE_CHECKING:
    from video_types import VideoType


# ── ベース system プロンプト ────────────────────────────
_BASE_SYSTEM = """あなたはスピリチュアル系YouTubeチャンネルの人気脚本家です。
視聴者は20〜50代の女性が中心で、引き寄せの法則・宇宙の意志・魂の成長・波動・
守護霊・前世・ライトワーカーなどのテーマに関心があります。

台本作成の基本ルール：
- 語りかける口調（「あなた」に直接語りかける）
- 1文を短く（読み上げやすい長さ）
- 神秘的・癒し系のトーンを維持
- 科学的主張はしない（「〜と言われています」「〜を感じる方も」などの表現を使う）
- ナレーション本文のみ出力（BGM指示・カット指示等は不要）
- 各パートは空行で区切る
"""

_USER_TEMPLATE = """テーマ：{topic}
動画の型：{type_label}
フォーマット：{format_label}
対象動画尺：{duration_label}
台本構成の指示：
{script_structure}
追加指示：{extra}

以下のJSON形式で出力してください：
{{
  "title": "YouTube動画タイトル（クリック率重視、{title_len}文字以内）",
  "description": "YouTube概要欄（{desc_note}）",
  "tags": ["タグ1", "タグ2", ...],
  "thumbnail_keyword": "Pexels検索用英語キーワード（背景画像向け、1〜3語）",
  "bgm_keyword": "Pexels BGM検索キーワード（英語、例: meditation ambient）",
  "script": "ナレーション全文（空行で段落を区切る）"
}}"""


@dataclass
class ScriptResult:
    title:             str
    description:       str
    tags:              list[str]
    thumbnail_keyword: str
    bgm_keyword:       str
    script:            str
    raw_topic:         str
    video_type_id:     str = "education"


def _call_llm(system_prompt: str, user_msg: str, model: Optional[str] = None) -> str:
    """LLMバックエンドを自動選択してテキストを返す"""
    backend = LLM_BACKEND

    if backend == "gemini" and GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        m = model or "gemini-2.0-flash"
        gm = genai.GenerativeModel(
            model_name   = m,
            system_instruction = system_prompt,
        )
        resp = gm.generate_content(user_msg)
        return resp.text.strip()

    # fallback: Claude
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    m = model or "claude-opus-4-6"
    message = client.messages.create(
        model     = m,
        max_tokens= 4096,
        system    = system_prompt,
        messages  = [{"role": "user", "content": user_msg}],
    )
    return message.content[0].text.strip()


def generate_script(
    topic: str,
    video_type: Optional["VideoType"] = None,
    duration_min: Optional[int] = None,
    extra: str = "",
    model: Optional[str] = None,
    is_shorts: bool = False,
) -> ScriptResult:
    """
    トピック + 動画の型 からスピ系台本を生成してScriptResultを返す。

    Args:
        topic:        動画テーマ
        video_type:   VideoType インスタンス（None の場合は education を使用）
        duration_min: 目標動画尺（分）。None の場合は型のデフォルト値を使用
        extra:        追加プロンプト指示
        model:        使用するClaudeモデル
        is_shorts:    True の場合はショート動画向け台本を生成
    """
    if video_type is None:
        from video_types import get_type
        video_type = get_type("education")

    if is_shorts:
        script_structure = video_type.get_shorts_script_structure()
        duration_label   = f"約{video_type.shorts_duration_sec}秒（YouTubeショート）"
        format_label     = "YouTube ショート（縦型 9:16、60秒以内）"
        title_len        = "25"
        desc_note        = "150文字以内、末尾に #Shorts を含める"
        # ショートの場合は system にショート専用ルールを追加
        shorts_extra = """
【YouTube ショート専用ルール（最優先）】
- 台本全体で読み上げ時間が50〜58秒に収まる文字数にする（目安: 250〜300文字）
- 冒頭3秒で視聴者を掴む一文を必ず置く
- 「保存して」「コメントで教えて」など短い行動喚起で締める
- 長い説明・前置きは一切不要、結論から入る
"""
        system_prompt = _BASE_SYSTEM.rstrip() + "\n" + video_type.system_prompt_extra.strip() + shorts_extra
    else:
        dur              = duration_min if duration_min is not None else video_type.default_duration_min
        script_structure = video_type.script_structure.strip()
        duration_label   = f"{dur}分"
        format_label     = "通常動画（横型 16:9）"
        title_len        = "30"
        desc_note        = "200文字、キーワード含む"
        system_prompt    = _BASE_SYSTEM.rstrip() + "\n" + video_type.system_prompt_extra.strip()

    user_msg = _USER_TEMPLATE.format(
        topic            = topic,
        type_label       = video_type.label,
        format_label     = format_label,
        duration_label   = duration_label,
        script_structure = script_structure,
        extra            = extra or "特になし",
        title_len        = title_len,
        desc_note        = desc_note,
    )

    print(f"[Script] LLMバックエンド: {LLM_BACKEND}")
    raw = _call_llm(system_prompt, user_msg, model=model)

    # JSON部分を抽出（```json ... ``` ブロック or 生JSON）
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        start    = raw.find("{")
        end      = raw.rfind("}") + 1
        json_str = raw[start:end] if start != -1 else raw

    data = json.loads(json_str)

    # 背景キーワードは型のデフォルトにフォールバック
    thumb_kw = data.get("thumbnail_keyword") or video_type.random_bg_keyword()

    # ショートの場合はタイトル・説明欄に #Shorts を自動付与
    title_out = data["title"]
    desc_out  = data["description"]
    if is_shorts:
        if "#Shorts" not in title_out and "#shorts" not in title_out:
            title_out = title_out.rstrip() + " #Shorts"
        if "#Shorts" not in desc_out and "#shorts" not in desc_out:
            desc_out  = desc_out.rstrip() + "\n#Shorts"

    return ScriptResult(
        title             = title_out,
        description       = desc_out,
        tags              = data.get("tags", []),
        thumbnail_keyword = thumb_kw,
        bgm_keyword       = data.get("bgm_keyword", "meditation ambient"),
        script            = data["script"],
        raw_topic         = topic,
        video_type_id     = video_type.id,
    )


def split_script_to_sentences(script: str) -> list[str]:
    """台本を読み上げ単位の文に分割する（空行 or 句点で区切り）"""
    sentences = []
    for para in script.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        parts = re.split(r"(?<=[。！？])", para)
        for p in parts:
            p = p.strip()
            if p:
                sentences.append(p)
    return sentences


if __name__ == "__main__":
    import sys
    from video_types import list_types, get_type

    if "--list" in sys.argv:
        list_types()
        sys.exit(0)

    topic     = sys.argv[1] if len(sys.argv) > 1 else "守護霊からのメッセージ"
    type_id   = sys.argv[2] if len(sys.argv) > 2 else "message"
    vt        = get_type(type_id)
    result    = generate_script(topic, video_type=vt)
    print(f"型:      {vt.label}")
    print(f"タイトル: {result.title}")
    print(f"タグ:    {', '.join(result.tags[:5])}...")
    print(f"台本（先頭200文字）:\n{result.script[:200]}...")
