"""
uploader.py - TikTok への自動アップロード

実際のChromeをCDP経由で操作することでbot検出を回避。
認証: TIKTOK_SESSION_ID + TIKTOK_EXTRA_COOKIES 環境変数
"""

import os
import json
import time
import subprocess
import logging
import tempfile

import config

logger = logging.getLogger(__name__)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PROFILE = r"C:\tiktok_debug_profile"
CDP_PORT = 9223  # メインChromeと衝突しないよう9223を使用


def _session_id() -> str:
    return os.environ.get("TIKTOK_SESSION_ID", "") or config.TIKTOK_SESSION_ID


def _all_cookies() -> list:
    cookies = []
    sid = _session_id()
    if sid and sid != "your_tiktok_session_id":
        cookies.append({
            "name": "sessionid",
            "value": sid,
            "domain": ".tiktok.com",
            "path": "/",
        })
    extra = os.environ.get("TIKTOK_EXTRA_COOKIES", "[]")
    try:
        cookies.extend(json.loads(extra))
    except Exception:
        pass
    return cookies


def upload_to_tiktok(video_path: str, caption: str, headless: bool = False) -> bool:
    if not os.path.exists(video_path):
        logger.error(f"動画ファイルが見つかりません: {video_path}")
        return False

    cookies = _all_cookies()
    if not any(c["name"] == "sessionid" for c in cookies):
        logger.error("TIKTOK_SESSION_ID が設定されていません")
        return False

    # デバッグ用Chromeを起動
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={DEBUG_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "about:blank",
    ])
    time.sleep(3)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            # Cookieを注入
            context.add_cookies(cookies)
            logger.info(f"{len(cookies)}個のCookieを注入しました")

            # TikTok Studio アップロードページへ
            logger.info("TikTok Studio を開いています...")
            page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=30000)
            time.sleep(6)

            current_url = page.url
            logger.info(f"現在のURL: {current_url}")
            if "login" in current_url.lower():
                logger.error("ログインページにリダイレクトされました。sessionidを確認してください。")
                return False

            # file inputを探す
            logger.info("アップロードフォームを探しています...")
            try:
                file_input = page.locator('input[type="file"]').first
                file_input.wait_for(state="attached", timeout=15000)
            except Exception as e:
                logger.error(f"file inputが見つかりません: {e}")
                return False

            # 動画をセット
            logger.info(f"動画をセット中: {video_path}")
            page.evaluate("""el => {
                el.style.display = 'block';
                el.style.opacity = '1';
                el.removeAttribute('hidden');
            }""", file_input.element_handle())
            file_input.set_input_files(video_path)
            logger.info("動画のセット完了。処理中...")
            time.sleep(8)

            # キャプション入力
            caption_short = caption[:150]
            for sel in [
                '[data-text="true"]',
                '[contenteditable="true"]',
                'textarea[placeholder]',
                '.caption-input',
            ]:
                try:
                    cap_el = page.locator(sel).first
                    cap_el.wait_for(timeout=5000)
                    cap_el.click()
                    cap_el.fill(caption_short)
                    logger.info(f"キャプション入力完了 ({sel})")
                    break
                except Exception:
                    continue

            # 動画処理完了を待つ（最大90秒）
            logger.info("動画処理中... (最大90秒)")
            for i in range(18):
                time.sleep(5)
                buttons = page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim())")
                # button以外のクリッカブル要素も探す
                clickable = page.evaluate("""() => Array.from(document.querySelectorAll('[role="button"],[data-e2e],[class*="next"],[class*="submit"],[class*="post"],[class*="publish"]'))
                    .map(el => el.innerText?.trim() || el.getAttribute('data-e2e') || el.className).filter(t=>t).slice(0,20)""")
                logger.info(f"[{i*5}s] ボタン: {[b for b in buttons if b]}")
                logger.info(f"[{i*5}s] クリッカブル: {clickable[:10]}")
                # 投稿ボタンが出たら止まる
                post_keywords = ["投稿する", "Post", "公開する", "投稿", "公開"]
                if any(any(k in b for k in post_keywords) for b in buttons):
                    break

            # キャプション入力（タイトル欄 or テキストエリア）
            caption_short = caption[:150]
            for sel in [
                '[class*="title"] input',
                'input[placeholder]',
                '[contenteditable="true"]',
                'textarea',
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(timeout=3000)
                    el.click()
                    el.fill(caption_short)
                    logger.info(f"キャプション入力: {sel}")
                    break
                except Exception:
                    continue

            time.sleep(1)

            # 投稿ボタンをクリック（プライマリボタンクラスで検索）
            posted = False

            # まずテキストで検索
            for btn_text in ["投稿する", "投稿", "Post", "公開する", "公開", "アップロード"]:
                try:
                    btn = page.get_by_role("button", name=btn_text).first
                    btn.wait_for(timeout=3000)
                    btn.click()
                    posted = True
                    logger.info(f"投稿ボタンをクリック（テキスト）: {btn_text}")
                    break
                except Exception:
                    continue

            # プライマリボタンクラスで検索
            if not posted:
                try:
                    btn = page.locator('[class*="Button__root--type-primary"]').last
                    btn.wait_for(timeout=5000)
                    logger.info(f"プライマリボタンをクリック")
                    btn.click()
                    posted = True
                except Exception as e:
                    logger.warning(f"プライマリボタン失敗: {e}")

            if not posted:
                buttons = page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t)")
                logger.error(f"投稿ボタンが見つかりませんでした。現在のボタン: {buttons}")
                return False

            # 投稿完了を待つ
            time.sleep(10)
            logger.info("投稿完了!")
            return True

    except Exception as e:
        logger.error(f"アップロード中にエラー: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        try:
            chrome_proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print("使い方: python uploader.py <video.mp4> <キャプション>")
        sys.exit(1)
    ok = upload_to_tiktok(sys.argv[1], sys.argv[2])
    print("成功" if ok else "失敗")
