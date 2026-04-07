"""
scraper_worker.py - subprocess として呼ばれるスクショ取得ワーカー
使い方: python scraper_worker.py <url> <save_path>
"""
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def run(url: str, save_path: str):
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
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            # ログインバナーを閉じる
            for selector in ['[aria-label="Close"]', '[aria-label="閉じる"]', 'button:has-text("後で")']:
                try:
                    page.locator(selector).first.wait_for(timeout=2000)
                    page.locator(selector).first.click()
                    time.sleep(0.5)
                    break
                except PlaywrightTimeout:
                    pass

            # 投稿要素を探してスクショ
            for sel in ['article', '[data-pressable-container]', 'div[class*="post"]', 'main']:
                try:
                    el = page.locator(sel).first
                    el.wait_for(timeout=8000)
                    time.sleep(1)
                    el.screenshot(path=save_path)
                    print(f"OK:{save_path}", flush=True)
                    return
                except Exception:
                    continue

            # フォールバック
            page.screenshot(path=save_path, full_page=False)
            print(f"OK:{save_path}", flush=True)

        except Exception as e:
            print(f"ERROR:{e}", flush=True)
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR:引数不足", flush=True)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
