# ============================================================
#  TikTok 自動投稿システム - 設定ファイル
# ============================================================

# ---- Threads 検索ハッシュタグ（伸びてる他人の投稿を収集）-----
# 1回の実行で収集する最大URL数
THREADS_FETCH_LIMIT = 10
# 検索するハッシュタグ（ローテーションで1つずつ使用）
THREADS_HASHTAGS = [
    "復縁",
    "復縁したい",
    "復縁引き寄せ",
    "復縁占い",
    "復縁スピリチュアル",
]

# ---- TikTok セッションID (後述の取得方法を参照) ----------
# ブラウザでTikTokにログイン後、DevTools > Application >
# Cookies > https://www.tiktok.com > "sessionid" の値をコピー
TIKTOK_SESSION_ID = "your_tiktok_session_id"

# ---- TikTok 投稿キャプション設定 -------------------------
# 投稿に自動で付けるハッシュタグ・テキスト
TIKTOK_CAPTION_TEMPLATE = """{text}

#復縁 #復縁したい #復縁引き寄せ #復縁占い #復縁スピリチュアル #引き寄せの法則 #潜在意識 #恋愛"""

# アフィリエイトリンクや固定文言を追加したい場合はここに
AFFILIATE_FOOTER = ""  # 例: "プロフのリンクから詳細チェック✨"

# ---- スケジュール設定 ------------------------------------
# 1日3投稿の時刻 (24時間表記 "HH:MM")
POST_TIMES = ["09:00", "15:00", "21:00"]

# ---- PDCA自動最適化パラメータ（strategy_optimizer.pyが更新）----
# 動画の長さ（秒）
VIDEO_DURATION = 30.0
# コンテンツスタイルのヒント（Gemini改良プロンプトに追加される）
CONTENT_STYLE_HINT = ""  # 例: "感情に寄り添う共感系が伸びている。体験談・告白スタイルを意識して。"

# ---- 動画設定 --------------------------------------------
# TikTok推奨: 1080x1920 (9:16縦型)
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920

# スクショのオーバーレイ位置・サイズ (画面幅に対する割合)
SCREENSHOT_WIDTH_RATIO = 0.88   # 画面幅の88%
SCREENSHOT_Y_RATIO     = 0.40   # 上から40%の位置に配置

# 角丸の半径 (px)
CORNER_RADIUS = 30

# 影の設定
SHADOW_OFFSET = 12
SHADOW_BLUR   = 20
SHADOW_OPACITY = 140  # 0-255

# ---- ファイルパス ----------------------------------------
import os
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
BACKGROUNDS_DIR = r"C:\tiktok_backgrounds"  # 背景動画を置くフォルダ
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")   # 一時保存
OUTPUT_DIR      = os.path.join(BASE_DIR, "output")        # 完成動画
QUEUE_FILE      = os.path.join(BASE_DIR, "queue.json")    # 投稿キュー
LOG_FILE        = os.path.join(BASE_DIR, "tiktok_auto.log")
