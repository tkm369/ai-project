# ============================================================
#  TikTok 自動投稿システム - 設定ファイル
# ============================================================

# ---- Threads 検索ハッシュタグ（伸びてる他人の投稿を収集）-----
# 1回の実行で収集する最大URL数
THREADS_FETCH_LIMIT = 10
# 検索するハッシュタグ（ローテーションで1つずつ使用）
THREADS_HASHTAGS = [
    "占い",
    "スピリチュアル",
    "引き寄せの法則",
    "恋愛運",
    "タロット",
]

# ---- TikTok セッションID (後述の取得方法を参照) ----------
# ブラウザでTikTokにログイン後、DevTools > Application >
# Cookies > https://www.tiktok.com > "sessionid" の値をコピー
TIKTOK_SESSION_ID = "your_tiktok_session_id"

# ---- TikTok 投稿キャプション設定 -------------------------
# 投稿に自動で付けるハッシュタグ・テキスト
TIKTOK_CAPTION_TEMPLATE = """{text}

#占い #恋愛運 #スピリチュアル #引き寄せの法則 #恋愛 #運勢 #タロット #潜在意識 #開運"""

# アフィリエイトリンクや固定文言を追加したい場合はここに
AFFILIATE_FOOTER = ""  # 例: "プロフのリンクから詳細チェック✨"

# ---- スケジュール設定 ------------------------------------
# 1日3投稿の時刻 (24時間表記 "HH:MM")
POST_TIMES = ["09:00", "15:00", "21:00"]

# ---- 動画設定 --------------------------------------------
# TikTok推奨: 1080x1920 (9:16縦型)
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920

# スクショのオーバーレイ位置・サイズ (画面幅に対する割合)
SCREENSHOT_WIDTH_RATIO = 0.88   # 画面幅の88%
SCREENSHOT_Y_RATIO     = 0.25   # 上から25%の位置に配置

# 角丸の半径 (px)
CORNER_RADIUS = 30

# 影の設定
SHADOW_OFFSET = 12
SHADOW_BLUR   = 20
SHADOW_OPACITY = 140  # 0-255

# ---- ファイルパス ----------------------------------------
import os
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
BACKGROUNDS_DIR = os.path.join(BASE_DIR, "backgrounds")   # 背景動画を置くフォルダ
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")   # 一時保存
OUTPUT_DIR      = os.path.join(BASE_DIR, "output")        # 完成動画
QUEUE_FILE      = os.path.join(BASE_DIR, "queue.json")    # 投稿キュー
LOG_FILE        = os.path.join(BASE_DIR, "tiktok_auto.log")
