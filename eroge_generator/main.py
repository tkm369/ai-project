#!/usr/bin/env python3
"""
エロゲ自動生成パイプライン
ジャンル・形式・長さを選んでRen'Pyゲームを全自動生成する
"""
import argparse
import os
import random
import sys
from pathlib import Path

# Windows CP932 対策
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import google.generativeai as genai
from presets import GENRES, FORMATS, LENGTHS, ADULT_OPTIONS, ART_STYLES
from generator import generate_concept, generate_outline, generate_char_defs, generate_all_scenes, generate_assets
from renpy_writer import write_project
from voice_generator import generate_voices, VOICE_REFS

MODEL_NAME = "gemini-2.0-flash"


# ── API キー初期化 ──────────────────────────────────────────────
def init_gemini() -> genai.GenerativeModel:
    api_key = None
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "ここにキーを貼り付け":
        print("ERROR: GEMINI_API_KEY が設定されていません。")
        print("  .env に GEMINI_API_KEY=your_key を記入してください。")
        print("  無料キー取得: https://aistudio.google.com/")
        sys.exit(1)
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)


# ── インタラクティブ選択 ─────────────────────────────────────────
def _choose(label: str, options: dict, default: str = "1") -> dict:
    print(f"\n{'='*40}")
    print(f"  {label}")
    print(f"{'='*40}")
    for k, v in options.items():
        name = v["name"]
        desc = v.get("description", v.get("atmosphere", v.get("setting", "")))
        print(f"  [{k}] {name} — {desc}")
    print(f"  [r] ランダム")
    while True:
        ans = input(f"\n選択 (デフォルト: {default}): ").strip() or default
        if ans == "r":
            return random.choice(list(options.values()))
        if ans in options:
            return options[ans]
        print("  無効な入力です。もう一度選んでください。")


def interactive_select() -> dict:
    print("\n" + "="*50)
    print("  エロゲ自動生成パイプライン")
    print("="*50)
    genre     = _choose("ジャンルを選択", GENRES)
    fmt       = _choose("形式を選択", FORMATS)
    length    = _choose("長さを選択", LENGTHS)
    adult     = _choose("対象年齢を選択", ADULT_OPTIONS)
    art_style = _choose("アートスタイルを選択", ART_STYLES)
    return {
        "genre":     genre,
        "format":    fmt,
        "num_scenes": length["scenes"],
        "adult":     adult["adult"],
        "art_style": art_style,
    }


# ── argparse ───────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="エロゲ自動生成パイプライン")
    p.add_argument("--genre",  choices=list(GENRES.keys()),     help="ジャンル番号 (1-6)")
    p.add_argument("--format", choices=list(FORMATS.keys()),   help="形式番号 (1-6)")
    p.add_argument("--length", choices=list(LENGTHS.keys()),   help="長さ番号 (1=短, 2=中, 3=長)")
    p.add_argument("--art",    choices=list(ART_STYLES.keys()), help="アートスタイル (1=2D, 2=3D)")
    p.add_argument("--adult",  action="store_true",             help="成人向け (R18)")
    p.add_argument("--auto",   action="store_true",             help="全設定をランダム自動選択")
    p.add_argument("--voice",  action="store_true",             help="Qwen3 TTS でボイスを自動生成")
    return p.parse_args()


def resolve_settings(args) -> dict:
    if args.auto:
        return {
            "genre":      random.choice(list(GENRES.values())),
            "format":     random.choice(list(FORMATS.values())),
            "num_scenes": random.choice(list(LENGTHS.values()))["scenes"],
            "art_style":  random.choice(list(ART_STYLES.values())),
            "adult":      args.adult,
        }
    # 引数が全部揃っていればインタラクティブ選択をスキップ
    if args.genre and args.format and args.length and args.art:
        return {
            "genre":      GENRES[args.genre],
            "format":     FORMATS[args.format],
            "num_scenes": LENGTHS[args.length]["scenes"],
            "art_style":  ART_STYLES[args.art],
            "adult":      args.adult,
        }
    # 未指定項目だけインタラクティブに補完
    genre     = GENRES[args.genre]       if args.genre  else _choose("ジャンルを選択", GENRES)
    fmt       = FORMATS[args.format]     if args.format else _choose("形式を選択", FORMATS)
    length    = LENGTHS[args.length]     if args.length else _choose("長さを選択", LENGTHS)
    art_style = ART_STYLES[args.art]     if args.art    else _choose("アートスタイルを選択", ART_STYLES)
    adult_opt = ADULT_OPTIONS["2"]       if args.adult  else _choose("対象年齢を選択", ADULT_OPTIONS)
    return {
        "genre":      genre,
        "format":     fmt,
        "num_scenes": length["scenes"],
        "art_style":  art_style,
        "adult":      adult_opt["adult"],
    }


# ── メイン ─────────────────────────────────────────────────────
def main():
    args = parse_args()
    model = init_gemini()
    cfg = resolve_settings(args)

    genre      = cfg["genre"]
    fmt        = cfg["format"]
    num_scenes = cfg["num_scenes"]
    art_style  = cfg["art_style"]
    adult      = cfg["adult"]
    use_voice  = args.voice

    print(f"\n生成設定:")
    print(f"  ジャンル     : {genre['name']}")
    print(f"  形式         : {fmt['name']}")
    print(f"  シーン数     : {num_scenes}")
    print(f"  アートスタイル: {art_style['name']}")
    print(f"  対象年齢     : {'R18（成人向け）' if adult else '全年齢'}")
    print("\n生成を開始します...\n")

    # Step 1: コンセプト（タイトル・キャラ・設定）
    concept = generate_concept(model, genre, fmt, adult)
    print(f"\nタイトル: {concept['title']}")
    print(f"  ヒロイン: {', '.join(h['name'] for h in concept['heroines'])}\n")

    # Step 2: あらすじ・シーン構成
    outline = generate_outline(model, concept, genre, fmt, num_scenes, adult)

    # Step 3a: キャラ define
    char_defs = generate_char_defs(model, concept)

    # Step 3b: 全シーン生成
    scenes = generate_all_scenes(model, concept, outline, char_defs, num_scenes, adult)

    # Step 3c: 画像素材プロンプト / 3D設定生成
    assets = generate_assets(model, concept, outline, art_style, adult)

    # Step 4: Ren'Py プロジェクト出力
    print("\n[4/4] Ren'Py プロジェクト出力中...")
    project_dir = write_project(concept, char_defs, scenes, art_style, assets)

    # Step 5 (任意): Qwen3 TTS でボイス生成
    if use_voice:
        print("\n[5/5] ボイス生成中（Qwen3 TTS）...")
        _print_voice_refs_guide(concept)
        generate_voices(project_dir, concept)
    else:
        print("\n  ヒント: --voice を付けると Qwen3 TTS でボイスを自動生成します")

    print(f"\n完成! -> {project_dir}")
    print("Ren'Py SDK (https://www.renpy.org/) で開いて遊べます。")


def _print_voice_refs_guide(concept: dict):
    """voice_refs フォルダの使い方をガイド表示"""
    VOICE_REFS.mkdir(exist_ok=True)
    vars_ = ["narrator"] + [h["var_name"] for h in concept.get("heroines", [])]
    missing = [v for v in vars_ if not (VOICE_REFS / f"{v}.wav").exists()
               and not (VOICE_REFS / "default.wav").exists()]
    if missing:
        print(f"\n  参照音声が未設定のキャラ: {', '.join(missing)}")
        print(f"  voice_refs/ フォルダに以下を配置してください:")
        for v in vars_:
            print(f"    voice_refs/{v}.wav  （{v} の声の参照音声）")
        print(f"  または voice_refs/default.wav を置けば全キャラ共通で使用されます。\n")


if __name__ == "__main__":
    main()
