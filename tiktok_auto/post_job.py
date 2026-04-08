"""
post_job.py - タスクスケジューラから呼ばれる1投稿スクリプト
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_auto.log"),
            encoding="utf-8"
        ),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

from fetcher import fetch_and_enqueue
from scheduler import run_post_job

logger.info("=== STEP1: fetch_and_enqueue 開始 ===")
t0 = time.time()
fetch_and_enqueue()
logger.info(f"=== STEP1完了: {time.time()-t0:.1f}秒 ===")

logger.info("=== STEP2: run_post_job 開始 ===")
t1 = time.time()
run_post_job()
logger.info(f"=== STEP2完了: {time.time()-t1:.1f}秒 ===")
