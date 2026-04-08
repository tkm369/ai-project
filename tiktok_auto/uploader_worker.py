"""
uploader_worker.py - subprocess として呼ばれるTikTokアップロードワーカー
使い方: python uploader_worker.py <video_path> <caption>
環境変数: TIKTOK_SESSION_ID, TIKTOK_EXTRA_COOKIES
"""
import os
import sys
import json
import time
import subprocess

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PROFILE = r"C:\tiktok_debug_profile"
CDP_PORT = 9223


def get_cookies():
    cookies = []
    sid = os.environ.get("TIKTOK_SESSION_ID", "")
    if sid and sid != "your_tiktok_session_id":
        cookies.append({"name": "sessionid", "value": sid, "domain": ".tiktok.com", "path": "/"})
    extra = os.environ.get("TIKTOK_EXTRA_COOKIES", "[]")
    try:
        cookies.extend(json.loads(extra))
    except Exception:
        pass
    return cookies


def kill_port(port):
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], timeout=5)
                time.sleep(1)
                break
    except Exception:
        pass


def kill_chrome_holding_profile(profile_dir):
    """tiktok_debug_profileを掴んでいるChromeプロセスを強制終了"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"CommandLine like '%{profile_dir}%'", "get", "ProcessId", "/format:list"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if line.startswith("ProcessId="):
                pid = line.split("=")[1].strip()
                if pid:
                    subprocess.run(["taskkill", "/F", "/PID", pid], timeout=5)
                    print(f"INFO:Chrome PID {pid} を終了しました", flush=True)
        time.sleep(2)
    except Exception as e:
        print(f"INFO:Chrome終了試行: {e}", flush=True)


def release_profile_lock(profile_dir):
    """ChromeプロファイルのSingletonLockファイルを削除"""
    import pathlib
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = pathlib.Path(profile_dir) / lock_name
        try:
            if lock_path.exists():
                lock_path.unlink()
                print(f"INFO:{lock_name} 削除完了", flush=True)
        except Exception as e:
            print(f"INFO:{lock_name} 削除失敗: {e}", flush=True)


def run(video_path: str, caption: str):
    cookies = get_cookies()
    if not any(c["name"] == "sessionid" for c in cookies):
        print("ERROR:TIKTOK_SESSION_ID未設定", flush=True)
        sys.exit(1)

    kill_chrome_holding_profile(DEBUG_PROFILE)
    kill_port(CDP_PORT)
    release_profile_lock(DEBUG_PROFILE)

    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={DEBUG_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--no-restore-session-state",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "about:blank",
    ])
    time.sleep(3)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}", timeout=10000)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            context.add_cookies(cookies)
            print("INFO:Cookie注入完了", flush=True)

            page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=30000)
            time.sleep(6)

            if "login" in page.url.lower():
                print("ERROR:ログインページ。sessionid期限切れ", flush=True)
                sys.exit(1)

            file_input = page.locator('input[type="file"]').first
            file_input.wait_for(state="attached", timeout=15000)

            page.evaluate("""el => {
                el.style.display = 'block';
                el.style.opacity = '1';
                el.removeAttribute('hidden');
            }""", file_input.element_handle())
            file_input.set_input_files(video_path)
            print("INFO:動画セット完了", flush=True)
            time.sleep(8)

            # キャプション入力
            caption_short = caption[:150]
            for sel in ['[data-text="true"]', '[contenteditable="true"]', 'textarea[placeholder]']:
                try:
                    el = page.locator(sel).first
                    el.wait_for(timeout=5000)
                    el.click()
                    el.fill(caption_short)
                    print(f"INFO:キャプション入力 ({sel})", flush=True)
                    break
                except Exception:
                    continue

            # 動画処理完了を待つ（最大90秒）
            for i in range(18):
                time.sleep(5)
                buttons = page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim())")
                post_keywords = ["投稿する", "Post", "公開する", "投稿", "公開"]
                if any(any(k in b for k in post_keywords) for b in buttons):
                    break

            # 投稿ボタンをクリック
            for sel in [
                '[data-e2e="post_video_button"]',
                '[data-e2e="post-video-button"]',
                '[data-e2e="submit_video_button"]',
            ]:
                try:
                    btn = page.locator(sel).first
                    btn.wait_for(state="visible", timeout=3000)
                    btn.click()
                    time.sleep(10)
                    print("OK:投稿完了", flush=True)
                    return
                except Exception:
                    continue

            print("ERROR:投稿ボタンが見つかりませんでした", flush=True)
            sys.exit(1)

    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)
    finally:
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=5)
        except Exception:
            pass
        try:
            chrome_proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR:引数不足 <video_path> <caption>", flush=True)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
