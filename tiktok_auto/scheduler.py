"""
scheduler.py - メインスクリプト

【使い方】
1. キューに投稿を追加:
   python scheduler.py add <X or Threads の投稿URL> [任意のキャプション]

2. スケジューラー起動 (1日3回自動投稿):
   python scheduler.py run

3. キュー確認:
   python scheduler.py list

4. 今すぐ1件投稿 (テスト):
   python scheduler.py post-now
"""

import os
import sys
import json
import time
import hashlib
import logging
import argparse
from datetime import datetime

import schedule

import config
from scraper import screenshot_post, extract_text_from_post
from card_generator import generate_card
from text_improver import improve_text, is_valid_post
from composer import compose_video
from uploader import upload_to_tiktok

# ------------------------------------------------------------------ #
#  ログ設定
# ------------------------------------------------------------------ #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  キュー管理
# ------------------------------------------------------------------ #

def load_queue() -> list:
    if not os.path.exists(config.QUEUE_FILE):
        return []
    with open(config.QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list):
    with open(config.QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def add_to_queue(url: str, caption_override: str = ""):
    """投稿URLをキューに追加"""
    queue = load_queue()
    item = {
        "url":             url,
        "caption_override": caption_override,
        "added_at":        datetime.now().isoformat(),
        "status":          "pending",  # pending / done / failed
    }
    queue.append(item)
    save_queue(queue)
    logger.info(f"キューに追加: {url}  (合計 {len(queue)} 件)")


def get_next_pending() -> dict | None:
    """次のpending または failed アイテムを返す（2回以上failedはスキップ）"""
    queue = load_queue()
    for item in queue:
        if item["status"] == "pending":
            return item
        if item["status"] == "failed" and item.get("fail_count", 1) < 2:
            item["status"] = "pending"
            save_queue(queue)
            return item
    return None


def mark_item(url: str, status: str):
    """アイテムのステータスを更新"""
    queue = load_queue()
    for item in queue:
        if item["url"] == url and item["status"] == "pending":
            item["status"] = status
            item["processed_at"] = datetime.now().isoformat()
            if status == "failed":
                item["fail_count"] = item.get("fail_count", 0) + 1
            break
    save_queue(queue)


# ------------------------------------------------------------------ #
#  投稿ジョブ
# ------------------------------------------------------------------ #

POSTS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts_log.json")

def _load_posts_log() -> list:
    """posts_log.jsonを読み込む"""
    if os.path.exists(POSTS_LOG_FILE):
        with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def _log_post(post_id: str, source_url: str, text: str, posted_at: str,
              text_length: int = 0, posting_hour: int = 0,
              source_hashtag: str = "", video_duration: float = 7.0):
    """投稿メタデータをposts_log.jsonに記録"""
    log = _load_posts_log()
    log.append({
        "id": post_id,
        "posted_at": posted_at,
        "source_url": source_url,
        "text": text,
        "text_hash": hashlib.md5(text.strip().encode("utf-8")).hexdigest(),
        "text_length": text_length,
        "posting_hour": posting_hour,
        "source_hashtag": source_hashtag,
        "video_duration": video_duration,
        "views": None,
        "likes": None,
        "comments": None,
        "last_checked": None,
    })
    with open(POSTS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def build_caption(item: dict) -> str:
    """キャプション文字列を生成"""
    text = item.get("caption_override", "") or ""
    full_caption = config.TIKTOK_CAPTION_TEMPLATE.format(text=text)
    if config.AFFILIATE_FOOTER:
        full_caption += f"\n{config.AFFILIATE_FOOTER}"
    return full_caption.strip()



def run_post_job():
    """1投稿分の処理: スクショ → 動画合成 → TikTokアップロード"""
    item = get_next_pending()
    if not item:
        logger.info("キューにpendingな投稿がありません。スキップします。")
        return

    url = item["url"]
    logger.info(f"=== 投稿開始: {url} ===")

    # seen_ids チェック（重複投稿防止）
    from fetcher import load_seen, save_seen
    seen = load_seen()
    if url in seen:
        logger.warning(f"既投稿済みURLのためスキップ: {url}")
        mark_item(url, "skipped")
        return

    try:
        import time as _time

        # 1) テキスト取得 → X風カード生成
        logger.info("1/3 テキスト取得・カード生成中...")
        _t = _time.time()
        try:
            post_text = extract_text_from_post(url)
        except RuntimeError as e:
            err_str = str(e)
            if "IMAGE_POST" in err_str:
                logger.warning(f"画像メイン投稿のためスキップ: {url}")
                mark_item(url, "skipped")
                return
            raise
        logger.info(f"【元テキスト】{post_text}")

        if not is_valid_post(post_text):
            logger.warning(f"Gemini判定NG: 不適切なテキストのためスキップ → {post_text[:50]}")
            mark_item(url, "skipped")
            return

        # テキストハッシュで重複チェック（同じ内容が過去に投稿済みならスキップ）
        text_hash = hashlib.md5(post_text.strip().encode("utf-8")).hexdigest()
        posted_hashes = {p.get("text_hash") for p in _load_posts_log()}
        if text_hash in posted_hashes:
            logger.warning(f"同一テキストが既に投稿済みのためスキップ: {post_text[:40]}")
            mark_item(url, "skipped")
            return

        improved_text = improve_text(post_text)
        logger.info(f"【改良後テキスト】{improved_text}")
        timestamp_card = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)
        ss_path = os.path.join(config.SCREENSHOTS_DIR, f"card_{timestamp_card}.png")
        generate_card(improved_text, ss_path)
        logger.info(f"1/3完了: {_time.time()-_t:.1f}秒")

        # 2) 動画合成
        logger.info("2/3 動画合成中...")
        _t = _time.time()
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(config.OUTPUT_DIR, f"tiktok_{timestamp}.mp4")
        caption     = build_caption(item)
        compose_video(ss_path, output_path, caption_text=caption, duration=config.VIDEO_DURATION)
        logger.info(f"2/3完了: {_time.time()-_t:.1f}秒")

        # 3) TikTokアップロード
        logger.info("3/3 TikTokにアップロード中...")
        _t = _time.time()
        ok = upload_to_tiktok(output_path, caption)
        logger.info(f"3/3完了: {_time.time()-_t:.1f}秒 ok={ok}")

        if ok:
            # 投稿成功時のみseen_idsに登録（失敗時は再試行できるようにする）
            seen.add(url)
            save_seen(seen)
            mark_item(url, "done")
            _log_post(
                post_id=timestamp,
                source_url=url,
                text=improved_text,
                posted_at=datetime.now().isoformat(),
                text_length=len(improved_text),
                posting_hour=datetime.now().hour,
                source_hashtag=item.get("hashtag", ""),
                video_duration=config.VIDEO_DURATION,
            )
            logger.info(f"=== 投稿完了: {url} ===")
        else:
            mark_item(url, "failed")
            logger.error(f"=== 投稿失敗: {url} ===")

    except Exception as e:
        logger.exception(f"予期しないエラー: {e}")
        mark_item(url, "failed")


# ------------------------------------------------------------------ #
#  スケジューラー
# ------------------------------------------------------------------ #

def start_scheduler():
    """設定した時刻に1日3回投稿"""
    for t in config.POST_TIMES:
        schedule.every().day.at(t).do(run_post_job)
        logger.info(f"スケジュール登録: 毎日 {t}")

    logger.info("スケジューラー起動。Ctrl+C で停止。")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ------------------------------------------------------------------ #
#  CLI
# ------------------------------------------------------------------ #

def cmd_add(args):
    caption = " ".join(args.caption) if args.caption else ""
    add_to_queue(args.url, caption)
    print(f"追加しました: {args.url}")


def cmd_list(args):
    queue = load_queue()
    if not queue:
        print("キューは空です。")
        return
    print(f"{'#':<3} {'ステータス':<10} {'追加日時':<22} URL")
    print("-" * 80)
    for i, item in enumerate(queue, 1):
        print(f"{i:<3} {item['status']:<10} {item['added_at'][:19]:<22} {item['url']}")


def cmd_run(args):
    start_scheduler()


def cmd_post_now(args):
    run_post_job()


def main():
    parser = argparse.ArgumentParser(description="TikTok 自動投稿システム")
    sub = parser.add_subparsers(dest="cmd")

    # add
    p_add = sub.add_parser("add", help="投稿URLをキューに追加")
    p_add.add_argument("url",     help="X または Threads の投稿URL")
    p_add.add_argument("caption", nargs="*", help="任意のキャプション (省略可)")
    p_add.set_defaults(func=cmd_add)

    # list
    p_list = sub.add_parser("list", help="キュー一覧を表示")
    p_list.set_defaults(func=cmd_list)

    # run
    p_run = sub.add_parser("run", help="スケジューラーを起動")
    p_run.set_defaults(func=cmd_run)

    # post-now
    p_now = sub.add_parser("post-now", help="今すぐ1件投稿 (テスト)")
    p_now.set_defaults(func=cmd_post_now)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
