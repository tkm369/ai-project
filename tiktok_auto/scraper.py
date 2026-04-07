"""
scraper.py - X(Twitter) と Threads の投稿をスクリーンショット取得
"""

import os
import re
import time
import logging
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


def screenshot_threads_post(url: str) -> str:
    """
    Threads の投稿URLからスクリーンショットを取得。
    戻り値: 保存したPNGのパス
    """
    import threading

    post_id = url.rstrip("/").split("/")[-1]
    save_path = _save_path("threads", post_id)
    result = [save_path]
    error = [None]

    def _do():
        try:
            result[0] = _screenshot_threads_inner(url, save_path)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_do)
    t.start()
    t.join(timeout=SCREENSHOT_TIMEOUT)
    if t.is_alive():
        raise RuntimeError(f"スクショ取得が{SCREENSHOT_TIMEOUT}秒でタイムアウト: {url}")
    if error[0]:
        raise error[0]
    return result[0]


def _screenshot_threads_inner(url: str, save_path: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 600, "height": 900},
            device_scale_factor=2,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # ログインバナーを閉じる
            for selector in ['[aria-label="Close"]', '[aria-label="閉じる"]', 'button:has-text("後で")']:
                try:
                    btn = page.locator(selector).first
                    btn.wait_for(timeout=2000)
                    btn.click()
                    time.sleep(0.5)
                    break
                except PlaywrightTimeout:
                    pass

            # 投稿本文のセレクタ (複数試す)
            selectors = [
                'article',
                '[data-pressable-container]',
                'div[class*="post"]',
                'main',
            ]
            captured = False
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    el.wait_for(timeout=8000)
                    time.sleep(1)
                    el.screenshot(path=save_path)
                    captured = True
                    logger.info(f"[Threads] スクショ保存 ({sel}): {save_path}")
                    break
                except Exception:
                    continue

            if not captured:
                # フォールバック: ページ中央部を切り出し
                page.screenshot(path=save_path, full_page=False)
                logger.info(f"[Threads] フォールバック全体スクショ: {save_path}")

        except Exception as e:
            logger.error(f"[Threads] スクショ失敗 {url}: {e}")
            try:
                page.screenshot(path=save_path, full_page=False)
            except Exception:
                pass

        finally:
            browser.close()

    return save_path


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
