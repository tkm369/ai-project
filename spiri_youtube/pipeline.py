"""
pipeline.py — スピ系YouTube自動生成パイプライン オーケストレーター

使い方:
    # 型一覧を表示
    python pipeline.py --list-types

    # 型を指定して通常動画を生成（16:9）
    python pipeline.py --topic "守護霊のサイン" --type message

    # ショート動画を生成（9:16・60秒以内）
    python pipeline.py --topic "守護霊のサイン" --type trivia --shorts

    # ランダムトピック × アファメーション × ショート
    python pipeline.py --random --type affirmation --shorts

    # 台本だけ確認（音声・動画なし）
    python pipeline.py --topic "引き寄せ実践" --type howto --script-only

    # 動画生成 → YouTube自動投稿
    python pipeline.py --topic "癒しの瞑想" --type healing --upload --privacy public

    # ショートを投稿（#Shorts タグ自動付与）
    python pipeline.py --topic "波動を上げる方法" --type howto --shorts --upload --privacy public

    # 既存script.jsonから動画だけ再生成
    python pipeline.py --from-script output/xxx/script.json

利用可能な型 (--type):
    affirmation  ✨ アファメーション
    education    📖 スピ教育系
    message      👼 守護霊・天使メッセージ
    howto        🌟 引き寄せ実践How-to
    healing      🌙 癒し・瞑想誘導
    trivia       🔮 スピ雑学・不思議話
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR
from video_types import TYPES, VideoType, get_type, list_types
from script_generator import ScriptResult, generate_script, split_script_to_sentences
from tts_wrapper import generate_audio_segments, concatenate_audio_files
from subtitle_gen import generate_subtitles
from video_composer import compose_video
from youtube_uploader import upload_video

TOPICS_FILE = Path(__file__).parent / "topics.json"


# ────────────────────────────────────────────────────────
# データクラス
# ────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    topic:         str
    title:         str
    video_type_id: str
    video_path:    str
    srt_path:      str
    script_path:   str
    is_shorts:     bool = False
    youtube_id:    str  = ""
    created_at:    str  = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ────────────────────────────────────────────────────────
# パイプライン本体
# ────────────────────────────────────────────────────────

def run_pipeline(
    topic: str,
    video_type: VideoType,
    duration_min: int | None = None,
    tts_voice: str | None = None,
    upload: bool = False,
    privacy: str | None = None,
    script_only: bool = False,
    from_script: str | None = None,
    is_shorts: bool = False,
) -> PipelineResult:
    """
    1本のスピ系YouTube動画をエンドツーエンドで生成する。

    Args:
        topic:        動画テーマ
        video_type:   VideoType インスタンス
        duration_min: 目標動画尺（None → 型のデフォルト値）
        tts_voice:    TTS音声名（None → 型の推奨音声）
        upload:       True でYouTube自動アップロード
        privacy:      "public" / "unlisted" / "private"
        script_only:  台本生成のみで終了
        from_script:  既存のscript.jsonパスを指定して台本生成スキップ
        is_shorts:    True の場合は縦型(9:16)・60秒以内のショート動画を生成
    """
    fmt_tag = "_shorts" if is_shorts else ""
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(OUTPUT_DIR) / f"{ts}_{video_type.id}{fmt_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)

    fmt_label = "📱 ショート (9:16・60秒)" if is_shorts else "🖥️  通常動画 (16:9)"
    print(f"\n{'='*60}")
    print(f"スピ系YouTube パイプライン開始")
    print(f"  型:       {video_type.label}")
    print(f"  フォーマット: {fmt_label}")
    print(f"  トピック: {topic}")
    print(f"  出力:     {run_dir}")
    print(f"{'='*60}\n")

    # ── STEP 1: 台本生成 ────────────────────────────────
    script_json_path = str(run_dir / "script.json")

    if from_script:
        print("[Step 1/5] 台本読み込み中...")
        with open(from_script, "r", encoding="utf-8") as f:
            data = json.load(f)
        script = ScriptResult(**data)
    else:
        print(f"[Step 1/5] 台本生成中 ({video_type.label}{'・ショート' if is_shorts else ''})")
        script = generate_script(
            topic,
            video_type   = video_type,
            duration_min = duration_min,
            is_shorts    = is_shorts,
        )
        with open(script_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "title":             script.title,
                "description":       script.description,
                "tags":              script.tags,
                "thumbnail_keyword": script.thumbnail_keyword,
                "bgm_keyword":       script.bgm_keyword,
                "script":            script.script,
                "raw_topic":         script.raw_topic,
                "video_type_id":     script.video_type_id,
            }, f, ensure_ascii=False, indent=2)
        print(f"  タイトル:  {script.title}")
        print(f"  台本文字数: {len(script.script)}")

    if script_only:
        print(f"\n台本を保存しました: {script_json_path}")
        return PipelineResult(
            topic         = script.raw_topic,
            title         = script.title,
            video_type_id = video_type.id,
            video_path    = "",
            srt_path      = "",
            script_path   = script_json_path,
            is_shorts     = is_shorts,
            created_at    = ts,
        )

    # ── STEP 2: TTS 音声生成 ─────────────────────────────
    # ショートの場合は型の shorts_tts_rate を優先使用
    voice = tts_voice or video_type.tts_voice
    rate  = video_type.shorts_tts_rate if is_shorts else video_type.tts_rate

    print(f"\n[Step 2/5] 音声生成中 (音声: {voice}, 速度: {rate})")
    sentences = split_script_to_sentences(script.script)
    print(f"  センテンス数: {len(sentences)}")

    seg_dir   = run_dir / "segments"
    seg_paths = generate_audio_segments(
        sentences,
        out_dir = seg_dir,
        voice   = voice,
        rate    = rate,
    )

    narration_path = str(run_dir / "narration.mp3")
    concatenate_audio_files(seg_paths, narration_path)
    print(f"  ナレーション: {narration_path}")

    # ── STEP 3: 字幕生成 ────────────────────────────────
    print(f"\n[Step 3/5] 字幕生成中 (Whisper)")
    sub_style = video_type.shorts_subtitle_style if is_shorts else video_type.subtitle_style
    srt_path, ass_path = generate_subtitles(
        narration_path,
        output_dir     = str(run_dir / "subtitles"),
        subtitle_style = sub_style,
        is_shorts      = is_shorts,
    )
    print(f"  SRT: {srt_path}")

    # ── STEP 4: 動画合成 ────────────────────────────────
    print(f"\n[Step 4/5] 動画合成中 (FFmpeg {'縦型9:16' if is_shorts else '横型16:9'})")
    video_filename = "final_shorts.mp4" if is_shorts else "final.mp4"
    video_path = str(run_dir / video_filename)
    t_style = video_type.shorts_title_style if is_shorts else video_type.title_style
    compose_video(
        narration_audio = narration_path,
        ass_subtitle    = ass_path,
        output_path     = video_path,
        title           = script.title,
        bg_keyword      = script.thumbnail_keyword or video_type.random_bg_keyword(),
        work_dir        = run_dir / "_work",
        title_style     = t_style,
        is_shorts       = is_shorts,
    )

    # ── STEP 5: YouTubeアップロード（オプション） ──────────
    youtube_id = ""
    if upload:
        print(f"\n[Step 5/5] YouTubeアップロード中...")
        youtube_id = upload_video(
            video_path  = video_path,
            title       = script.title,
            description = script.description,
            tags        = script.tags,
            privacy     = privacy,
        )
    else:
        print(f"\n[Step 5/5] アップロードスキップ (--upload なし)")

    # ── DB 登録（PDCA追跡用） ─────────────────────────────
    try:
        from pdca_db import save_video
        save_video(
            title         = script.title,
            topic         = script.raw_topic,
            video_type_id = video_type.id,
            is_shorts     = is_shorts,
            output_path   = video_path,
            created_at    = ts,
            video_id      = youtube_id or None,
            uploaded_at   = datetime.now().isoformat() if youtube_id else None,
            privacy       = privacy or "private",
        )
    except Exception as e:
        print(f"[DB] 記録エラー（続行）: {e}")

    result = PipelineResult(
        topic         = script.raw_topic,
        title         = script.title,
        video_type_id = video_type.id,
        video_path    = video_path,
        srt_path      = srt_path,
        script_path   = script_json_path,
        is_shorts     = is_shorts,
        youtube_id    = youtube_id,
        created_at    = ts,
    )

    with open(run_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"完了!")
    print(f"  動画:  {video_path}")
    if youtube_id:
        print(f"  YouTube: https://www.youtube.com/watch?v={youtube_id}")
    print(f"{'='*60}\n")
    return result


# ────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────

def _load_random_topic() -> str:
    if not TOPICS_FILE.exists():
        return "引き寄せの法則と宇宙のサイン"
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        topics = json.load(f)
    used_file = Path(OUTPUT_DIR) / "used_topics.json"
    used = []
    if used_file.exists():
        with open(used_file, "r", encoding="utf-8") as f:
            used = json.load(f)
    unused = [t for t in topics if t not in used]
    if not unused:
        used   = []
        unused = topics
    topic = random.choice(unused)
    used.append(topic)
    with open(used_file, "w", encoding="utf-8") as f:
        json.dump(used, f, ensure_ascii=False, indent=2)
    return topic


def main():
    parser = argparse.ArgumentParser(
        description="スピ系YouTube自動生成パイプライン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list-types",  action="store_true",  help="利用可能な動画の型を一覧表示して終了")
    parser.add_argument("--topic",       type=str,             help="動画テーマ")
    parser.add_argument("--random",      action="store_true",  help="topics.json からランダム選択")
    parser.add_argument("--type",        type=str, default="education",
                        choices=list(TYPES.keys()),
                        metavar="TYPE",
                        help=f"動画の型 ({', '.join(TYPES.keys())})")
    parser.add_argument("--shorts",      action="store_true",
                        help="ショート動画モード (9:16縦型・60秒以内・#Shorts自動付与)")
    parser.add_argument("--duration",    type=int,             help="通常動画の目標尺（分）。省略時は型のデフォルト")
    parser.add_argument("--tts-voice",   type=str,             help="TTS音声名（省略時は型の推奨音声）")
    parser.add_argument("--upload",      action="store_true",  help="YouTube自動アップロード")
    parser.add_argument("--privacy",     choices=["public", "unlisted", "private"], default="private")
    parser.add_argument("--script-only", action="store_true",  help="台本生成のみ（音声・動画なし）")
    parser.add_argument("--from-script", type=str,             help="既存script.jsonから動画のみ再生成")
    args = parser.parse_args()

    if args.list_types:
        list_types()
        return

    video_type = get_type(args.type)

    if args.from_script:
        topic = "（既存台本）"
    elif args.random:
        topic = _load_random_topic()
        print(f"ランダムトピック: {topic}")
    elif args.topic:
        topic = args.topic
    else:
        parser.error("--topic、--random、--from-script のいずれかが必要です")

    run_pipeline(
        topic        = topic,
        video_type   = video_type,
        duration_min = args.duration,
        tts_voice    = args.tts_voice,
        upload       = args.upload,
        privacy      = args.privacy,
        script_only  = args.script_only,
        from_script  = args.from_script,
        is_shorts    = args.shorts,
    )


if __name__ == "__main__":
    main()
