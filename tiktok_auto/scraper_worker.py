"""
scraper_worker.py - subprocess として呼ばれるスクショ取得ワーカー
使い方: python scraper_worker.py <url> <save_path>
"""
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def dismiss_overlays(page):
    """各種ポップアップ・オーバーレイを閉じる"""
    selectors = [
        '[aria-label="Close"]',
        '[aria-label="閉じる"]',
        'button:has-text("後で")',
        'button:has-text("Not now")',
        'button:has-text("Log in")',  # ログインダイアログの外側クリックで閉じる
        '[role="dialog"] button',
    ]
    for selector in selectors:
        try:
            els = page.locator(selector).all()
            for el in els:
                if el.is_visible():
                    el.click()
                    time.sleep(0.5)
        except Exception:
            pass

    # Escキーでポップアップを閉じる
    try:
        page.keyboard.press("Escape")
        time.sleep(0.5)
    except Exception:
        pass


def extract_text(url: str) -> str:
    """Threadsの投稿からテキストだけを取得して stdout に出力"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1080, "height": 1920},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            dismiss_overlays(page)

            # テキスト抽出 (JavaScript で dir=auto のspan要素から取得)
            text = ""
            try:
                texts = page.evaluate("""() => {
                    const spans = document.querySelectorAll("span[dir='auto']");
                    return Array.from(spans)
                        .map(s => {
                            let t = s.innerText.trim();
                            // 末尾の "Translate" や "Related" を削除
                            t = t.replace(/\\s*\\n?Translate\\s*$/, '').replace(/\\s*\\n?Related\\s*$/, '').trim();
                            return t;
                        })
                        .filter(t => {
                            if (t.length < 10) return false;
                            // 日本語が含まれているものだけを対象にする
                            const hasJapanese = /[\\u3040-\\u9fff]/.test(t);
                            if (!hasJapanese) return false;
                            return true;
                        });
                }""")
                if texts:
                    text = texts[0]  # 最初の有効なテキスト
            except Exception:
                pass

            if text:
                print(f"TEXT:{text}", flush=True)
            else:
                print("ERROR:テキスト取得失敗", flush=True)
                sys.exit(1)
        except Exception as e:
            print(f"ERROR:{e}", flush=True)
            sys.exit(1)
        finally:
            browser.close()


def run(url: str, save_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=2,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(4)

            # オーバーレイを閉じる
            dismiss_overlays(page)
            time.sleep(1)

            # 投稿テキスト部分だけを撮影
            post_selectors = [
                'article',
                '[data-pressable-container]',
                'div[class*="x1yztbdb"]',  # Threads投稿コンテナ
                'div[class*="post"]',
                'main',
            ]

            for sel in post_selectors:
                try:
                    el = page.locator(sel).first
                    el.wait_for(timeout=8000)
                    time.sleep(1)

                    # オーバーレイが消えているか確認してからスクショ
                    dismiss_overlays(page)
                    time.sleep(0.5)

                    el.screenshot(path=save_path)
                    print(f"OK:{save_path}", flush=True)
                    return
                except Exception:
                    continue

            # フォールバック：ページ全体
            dismiss_overlays(page)
            page.screenshot(path=save_path, full_page=False)
            print(f"OK:{save_path}", flush=True)

        except Exception as e:
            print(f"ERROR:{e}", flush=True)
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR:引数不足", flush=True)
        sys.exit(1)
    if sys.argv[1] == "--text":
        # テキスト抽出モード: python scraper_worker.py --text <url>
        if len(sys.argv) < 3:
            print("ERROR:引数不足", flush=True)
            sys.exit(1)
        extract_text(sys.argv[2])
    else:
        # スクショモード: python scraper_worker.py <url> <save_path>
        if len(sys.argv) < 3:
            print("ERROR:引数不足", flush=True)
            sys.exit(1)
        run(sys.argv[1], sys.argv[2])
