"""
config.py — 環境変数読み込みと設定集約
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── API Keys ──────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY", "")

# Gemini（無料枠: gemini-2.0-flash で1日1500回）
# eroge_generator の .env からも自動読み込み
def _load_gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        # 隣接プロジェクトの .env から探す
        for sibling in [
            Path(__file__).parent.parent / "eroge_generator" / ".env",
            Path(__file__).parent.parent / "sns_auto_poster" / ".env",
        ]:
            if sibling.exists():
                for line in sibling.read_text(encoding="utf-8").splitlines():
                    if line.startswith("GEMINI_API_KEY="):
                        found = line.split("=", 1)[1].strip()
                        if found and found != "ここにキーを貼り付け":
                            return found
    return key

GEMINI_API_KEY = _load_gemini_key()

# LLMバックエンド: "gemini"（無料）or "claude"（有料・高品質）
LLM_BACKEND = os.getenv("LLM_BACKEND", "gemini" if GEMINI_API_KEY else "claude")

# ── TTS ───────────────────────────────────────────────
TTS_ENGINE          = os.getenv("TTS_ENGINE", "edge")           # "edge" or "qwen3"
EDGE_TTS_VOICE      = os.getenv("EDGE_TTS_VOICE", "ja-JP-NanamiNeural")
QWEN3_TTS_URL       = os.getenv("QWEN3_TTS_URL", "http://127.0.0.1:7860")

# ── YouTube ───────────────────────────────────────────
YOUTUBE_CLIENT_SECRET_PATH = os.getenv("YOUTUBE_CLIENT_SECRET_PATH", "client_secret.json")
YOUTUBE_CATEGORY_ID        = os.getenv("YOUTUBE_CATEGORY_ID", "27")
YOUTUBE_PRIVACY            = os.getenv("YOUTUBE_PRIVACY", "private")

# ── 出力 ──────────────────────────────────────────────
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", Path(__file__).parent / "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 動画 ──────────────────────────────────────────────
VIDEO_WIDTH      = int(os.getenv("VIDEO_WIDTH", 1920))
VIDEO_HEIGHT     = int(os.getenv("VIDEO_HEIGHT", 1080))
VIDEO_FPS        = int(os.getenv("VIDEO_FPS", 30))
SUBTITLE_FONTSIZE = int(os.getenv("SUBTITLE_FONTSIZE", 52))
BGM_VOLUME       = float(os.getenv("BGM_VOLUME", 0.15))
BGM_DIR          = Path(os.getenv("BGM_DIR", Path(__file__).parent / "bgm"))
