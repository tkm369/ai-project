"""
scraper.py - X(Twitter) と Threads の投稿をスクリーンショット取得
"""

import os
import re
import sys
import time
import logging
import subprocess
from datetime import datetime
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

import config

logger = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_path(platform: str, post_id: str) -> str:
    fname = f"{platform}_{post_id}_{_timestamp()}.png"
    return os.path.join(config.SCREENSHOTS_DIR, fname)


def screenshot_x_post(url: str) -> str:
    """
    X(Twitter) の投稿URLからスクリーンショットを取得。
    ログイン不要の公開投稿を対象。
    戻り値: 保存したPNGのパス
    """
    post_id = re.search(r"/status/(\d+)", url)
    post_id = post_id.group(1) if post_id else "unknown"
    save_path = _save_path("x", post_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 600, "height": 900},
            device_scale_factor=2,          # Retina解像度
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            # ログインポップアップを閉じる
            try:
                page.locator('[data-testid="sheetDialog"]').wait_for(timeout=3000)
                page.keyboard.press("Escape")
                time.sleep(0.5)
            except PlaywrightTimeout:
                pass

            # ツイート本文のカード要素を取得
            tweet = page.locator('article[data-testid="tweet"]').first
            tweet.wait_for(timeout=15000)

            # アニメーション完了を少し待つ
            time.sleep(1.5)
            tweet.screenshot(path=save_path)
            logger.info(f"[X] スクショ保存: {save_path}")

        except Exception as e:
            logger.error(f"[X] スクショ失敗 {url}: {e}")
            # フォールバック: ページ全体をキャプチャ
            page.screenshot(path=save_path, full_page=False)

        finally:
            browser.close()

    return save_path


SCREENSHOT_TIMEOUT = 60  # スクショ取得の全体タイムアウト（秒）
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_worker.py")
PYTHON = sys.executable


def screenshot_threads_post(url: str) -> str:
    """
    Threads の投稿URLからスクリーンショットを取得。
    子プロセスで実行してタイムアウト時はプロセスごと強制終了する。
    戻り値: 保存したPNGのパス
    """
    os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)
    post_id = url.rstrip("/").split("/")[-1]
    save_path = _save_path("threads", post_id)

    try:
        result = subprocess.run(
            [PYTHON, WORKER, url, save_path],
            timeout=SCREENSHOT_TIMEOUT,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip()
        if output.startswith("OK:"):
            logger.info(f"[Threads] スクショ保存: {save_path}")
            return save_path
        else:
            err = output or result.stderr.strip()
            raise RuntimeError(f"worker失敗: {err}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"スクショ取得が{SCREENSHOT_TIMEOUT}秒でタイムアウト: {url}")


def crop_post_body(image_path: str, top_ratio: float = 0.18, bottom_ratio: float = 0.20) -> str:
    """
    スクショの上部(アカウント情報)と下部(エンゲージメント)をトリミング。
    top_ratio   : 上から何割カットするか (デフォルト18%)
    bottom_ratio: 下から何割カットするか (デフォルト20%)
    """
    img = Image.open(image_path)
    w, h = img.size
    top    = int(h * top_ratio)
    bottom = int(h * (1 - bottom_ratio))
    cropped = img.crop((0, top, w, bottom))
    cropped.save(image_path)
    return image_path


def extract_text_from_post(url: str) -> str:
    """Threads投稿URLからテキストを抽出して返す"""
    try:
        result = subprocess.run(
            [PYTHON, WORKER, "--text", url],
            timeout=SCREENSHOT_TIMEOUT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout.strip()
        # 画像メインの投稿はスキップ
        if "IMAGE_POST" in output:
            raise RuntimeError("IMAGE_POST:画像メインの投稿のためスキップ")
        # TEXT: 以降の全テキストを取得（改行含む投稿に対応）
        if "TEXT:" in output:
            idx = output.index("TEXT:")
            text = output[idx + 5:].strip()
            logger.info(f"[Threads] テキスト取得: {text[:50]}...")
            return text
        raise RuntimeError(f"テキスト取得失敗: {output or result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"テキスト取得タイムアウト: {url}")


def screenshot_post(url: str) -> str:
    """URLからプラットフォームを自動判定してスクショ取得"""
    if "x.com" in url or "twitter.com" in url:
        path = screenshot_x_post(url)
    elif "threads.net" in url or "threads.com" in url:
        path = screenshot_threads_post(url)
    else:
        raise ValueError(f"未対応のURL: {url}  (x.com / threads.net / threads.com のみ対応)")
    return crop_post_body(path)


# --- 動作確認用 ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    if len(sys.argv) < 2:
        print("使い方: python scraper.py <投稿URL>")
        sys.exit(1)
    result = screenshot_post(sys.argv[1])
    print(f"保存先: {result}")
