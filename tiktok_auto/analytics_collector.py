"""
analytics_collector.py - TikTok Studioから再生数・いいね数を取得してposts_log.jsonを更新する
"""
import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

POSTS_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts_log.json")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analytics_worker.py")
PYTHON = sys.executable


def collect_analytics():
    """posts_log.jsonの未取得・古いエントリのアナリティクスを更新"""
    if not os.path.exists(POSTS_LOG_FILE):
        logger.info("posts_log.jsonがありません。スキップします。")
        return

    with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
        log = json.load(f)

    # 投稿から1時間以上経過 かつ 未取得または24時間以上前に取得したものを対象
    now = datetime.now()
    targets = []
    for entry in log:
        posted_at = datetime.fromisoformat(entry["posted_at"])
        if now - posted_at < timedelta(hours=1):
            continue  # 投稿直後は除外
        last_checked = entry.get("last_checked")
        if last_checked:
            last_checked_dt = datetime.fromisoformat(last_checked)
            if now - last_checked_dt < timedelta(hours=24):
                continue  # 24時間以内に取得済み
        targets.append(entry)

    if not targets:
        logger.info("アナリティクス取得対象なし")
        return

    logger.info(f"アナリティクス取得: {len(targets)}件")

    import subprocess
    result = subprocess.run(
        [PYTHON, WORKER],
        capture_output=True, text=True, timeout=120,
        env={**os.environ}
    )

    # worker出力をそのままログに流す（デバッグ用）
    for line in result.stdout.splitlines():
        if not line.startswith("ANALYTICS:"):
            logger.info(f"[worker] {line}")
    if result.stderr:
        for line in result.stderr.splitlines()[:20]:
            logger.warning(f"[worker stderr] {line}")

    if result.returncode != 0:
        logger.error(f"analytics_worker失敗 (rc={result.returncode})")
        # returncode!=0でもANALYTICSが出力されている場合は続行

    # workerの出力からJSONを取得
    for line in result.stdout.splitlines():
        if line.startswith("ANALYTICS:"):
            try:
                data = json.loads(line[10:])
                _update_log(log, data)
            except Exception as e:
                logger.error(f"パース失敗: {e}")

    with open(POSTS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    logger.info("posts_log.json 更新完了")


def _update_log(log: list, analytics_data: list):
    """取得したアナリティクスデータでログを更新（投稿時刻で照合）"""
    for entry in log:
        posted_at = datetime.fromisoformat(entry["posted_at"])
        for item in analytics_data:
            try:
                item_dt = datetime.fromisoformat(item["created_at"])
                # 投稿時刻が30分以内のものを同一とみなす
                if abs((posted_at - item_dt).total_seconds()) < 1800:
                    entry["views"] = item.get("views", entry["views"])
                    entry["likes"] = item.get("likes", entry["likes"])
                    entry["comments"] = item.get("comments", entry["comments"])
                    entry["last_checked"] = datetime.now().isoformat()
                    break
            except Exception:
                continue


def trim_posts_log(keep: int = 500):
    """posts_log.json を最新keep件に絞る（古いエントリを削除）"""
    if not os.path.exists(POSTS_LOG_FILE):
        return
    with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
        log = json.load(f)
    if len(log) <= keep:
        return
    log = sorted(log, key=lambda x: x.get("posted_at", ""))[-keep:]
    with open(POSTS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    logger.info(f"posts_log.json トリム完了: {keep}件に削減")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    trim_posts_log()
    collect_analytics()
