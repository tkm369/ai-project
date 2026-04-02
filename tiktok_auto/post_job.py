"""
post_job.py - タスクスケジューラから呼ばれる1投稿スクリプト
"""
import sys, os
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

from fetcher import fetch_and_enqueue
from scheduler import run_post_job

# 1) X/Threads の新着を自動取得してキューに追加
fetch_and_enqueue()

# 2) キューから1件処理してTikTokに投稿
run_post_job()
