"""
scraper_worker.py - subprocess として呼ばれるスクショ取得ワーカー
使い方: python scraper_worker.py <url> <save_path>
"""
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Windows cp932環境でも絵文字等を含むテキストを出力できるようにUTF-8に設定
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


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
            has_image = False
            try:
                result = page.evaluate("""() => {
                    const article = document.querySelector('article');
                    const container = article || document;

                    // 画像・動画があるか検出（スクリーンショット/画像メイン投稿を判定）
                    const imgs = container.querySelectorAll('img[src*="cdninstagram"], img[src*="fbcdn"], img[src*="threads"]');
                    const videos = container.querySelectorAll('video');
                    // アバター画像を除く（小さい画像はアバター）
                    const contentImgs = Array.from(imgs).filter(img => {
                        const rect = img.getBoundingClientRect();
                        return rect.width > 100 && rect.height > 100;
                    });
                    const hasImage = contentImgs.length > 0 || videos.length > 0;

                    const spans = container.querySelectorAll("span[dir='auto']");
                    const texts = Array.from(spans)
                        .map(s => {
                            let t = s.innerText.trim();
                            t = t.replace(/\\s*\\n?Translate\\s*$/, '').replace(/\\s*\\n?Related\\s*$/, '').trim();
                            return t;
                        })
                        .filter(t => {
                            if (t.length < 10) return false;
                            const hasJapanese = /[\\u3040-\\u9fff]/.test(t);
                            if (!hasJapanese) return false;
                            return true;
                        });
                    return { texts, hasImage };
                }""")
                if result.get("texts"):
                    text = result["texts"][0]
                has_image = result.get("hasImage", False)
            except Exception:
                pass

            if has_image:
                print("ERROR:IMAGE_POST", flush=True)
                sys.exit(1)

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
