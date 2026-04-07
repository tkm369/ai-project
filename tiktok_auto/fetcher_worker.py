"""
fetcher_worker.py - subprocess として呼ばれるThreadsハッシュタグ収集ワーカー
使い方: python fetcher_worker.py <hashtag>
出力: JSON形式のURL一覧を標準出力へ
"""
import sys
import json
import time
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def run(hashtag: str, limit: int = 10):
    search_url = f"https://www.threads.net/search?q={hashtag}&serp_type=default"
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        page = context.new_page()

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(4)

            for selector in ['[aria-label="Close"]', '[aria-label="閉じる"]', 'button:has-text("後で")']:
                try:
                    page.locator(selector).first.wait_for(timeout=2000)
                    page.locator(selector).first.click()
                    time.sleep(0.5)
                    break
                except PlaywrightTimeout:
                    pass

            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

            hrefs = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                return [...new Set(links.map(a => a.href))];
            }""")

            for href in hrefs:
                m = re.search(r"/post/([A-Za-z0-9_-]+)", href)
                if not m:
                    continue
                post_id = m.group(1)
                results.append({"url": f"https://www.threads.net/post/{post_id}", "id": post_id})
                if len(results) >= limit:
                    break

        except Exception as e:
            print(f"ERROR:{e}", flush=True)
            sys.exit(1)
        finally:
            browser.close()

    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR:引数不足", flush=True)
        sys.exit(1)
    run(sys.argv[1])
