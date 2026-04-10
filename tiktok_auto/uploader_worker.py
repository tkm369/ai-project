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


def safe_print(*args, **kwargs):
    """cp932で出力できない文字を置換してprint"""
    text = " ".join(str(a) for a in args)
    text = text.encode('cp932', errors='replace').decode('cp932')
    print(text, **kwargs)

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
                    safe_print(f"INFO:Chrome PID {pid} を終了しました", flush=True)
        time.sleep(2)
    except Exception as e:
        safe_print(f"INFO:Chrome終了試行: {e}", flush=True)


def release_profile_lock(profile_dir):
    """ChromeプロファイルのSingletonLockファイルを削除"""
    import pathlib
    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = pathlib.Path(profile_dir) / lock_name
        try:
            if lock_path.exists():
                lock_path.unlink()
                safe_print(f"INFO:{lock_name} 削除完了", flush=True)
        except Exception as e:
            safe_print(f"INFO:{lock_name} 削除失敗: {e}", flush=True)


def run(video_path: str, caption: str):
    cookies = get_cookies()
    if not any(c["name"] == "sessionid" for c in cookies):
        safe_print("ERROR:TIKTOK_SESSION_ID未設定", flush=True)
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
            safe_print("INFO:Cookie注入完了", flush=True)

            page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=30000)
            time.sleep(6)

            if "login" in page.url.lower():
                safe_print("ERROR:ログインページ。sessionid期限切れ", flush=True)
                sys.exit(1)

            # ファイル選択ダイアログをインターセプトしてファイルをセット
            # TikTokのReactハンドラを正しく起動させるため、実際のボタンクリックを使う
            upload_triggered = False
            try:
                with page.expect_file_chooser(timeout=15000) as fc_info:
                    # アップロードボタンやドラッグエリアをクリック
                    for up_sel in [
                        '[data-e2e="upload-btn"]',
                        'button:has-text("アップロード")',
                        'div[class*="upload"]:has-text("アップロード")',
                        'label[for]',
                        'input[type="file"]',
                    ]:
                        try:
                            el = page.locator(up_sel).first
                            if el.is_visible(timeout=2000):
                                el.click()
                                break
                        except Exception:
                            continue
                file_chooser = fc_info.value
                file_chooser.set_files(video_path)
                upload_triggered = True
                safe_print("INFO:動画セット完了（ファイルチューザー経由）", flush=True)
            except Exception as e:
                safe_print(f"INFO:ファイルチューザー失敗、直接セット試行: {e}", flush=True)

            if not upload_triggered:
                # フォールバック：input[type=file]を直接操作
                file_input = page.locator('input[type="file"]').first
                file_input.wait_for(state="attached", timeout=15000)
                page.evaluate("""el => {
                    el.style.display = 'block';
                    el.style.opacity = '1';
                    el.removeAttribute('hidden');
                }""", file_input.element_handle())
                file_input.set_input_files(video_path)
                # React の onChange イベントを手動発火
                page.evaluate("""el => {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'files').set;
                    const event = new Event('change', { bubbles: true });
                    el.dispatchEvent(event);
                    const inputEvent = new Event('input', { bubbles: true });
                    el.dispatchEvent(inputEvent);
                }""", file_input.element_handle())
                safe_print("INFO:動画セット完了（直接セット）", flush=True)

            # アップロード開始を確認（最大30秒）
            for i in range(15):
                time.sleep(2)
                page_text = page.evaluate("() => document.body.innerText.slice(0, 200)")
                btns = page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b=>b.innerText.trim()).filter(t=>t)")
                safe_print(f"INFO:ページ状態({i*2}秒) ボタン:{btns[:4]}", flush=True)
                # 動画処理中・キャプション入力エリアが出たら次へ
                uploading_signs = ["アップロード中", "処理中", "caption", "キャプション"]
                if any(s in page_text for s in uploading_signs) or any("投稿" in b for b in btns):
                    break

            # キャプション入力
            caption_short = caption[:150]
            for sel in ['[data-text="true"]', '[contenteditable="true"]', 'textarea[placeholder]']:
                try:
                    el = page.locator(sel).first
                    el.wait_for(timeout=5000)
                    el.click()
                    el.fill(caption_short)
                    safe_print(f"INFO:キャプション入力 ({sel})", flush=True)
                    break
                except Exception:
                    continue

            # 動画処理完了を待つ（最大120秒）
            for i in range(24):
                time.sleep(5)
                buttons = page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim())")
                post_keywords = ["投稿する", "Post", "公開する", "投稿", "公開"]
                if any(any(k in b for k in post_keywords) for b in buttons):
                    safe_print(f"INFO:投稿可能ボタン検出: {[b for b in buttons if b][:5]}", flush=True)
                    break
                if i % 4 == 0:
                    safe_print(f"INFO:待機中({i*5}秒) ボタン: {[b for b in buttons if b][:5]}", flush=True)

            # 投稿ボタンをクリック（disabledが解除されるまで最大60秒待つ）
            clicked = False
            for sel in [
                '[data-e2e="post_video_button"]',
                '[data-e2e="post-video-button"]',
                '[data-e2e="submit_video_button"]',
            ]:
                try:
                    btn = page.locator(sel).first
                    btn.wait_for(state="visible", timeout=5000)
                    btn_text = btn.inner_text()
                    safe_print(f"INFO:投稿ボタン発見 ({sel}): '{btn_text}'", flush=True)
                    # disabledが解除されるまで待つ（最大90秒）
                    is_disabled = True
                    for wait_i in range(90):
                        is_disabled = page.evaluate(
                            "(sel) => { const el = document.querySelector(sel); return el ? el.disabled || el.getAttribute('disabled') !== null || el.getAttribute('aria-disabled') === 'true' : true; }",
                            sel
                        )
                        if not is_disabled:
                            safe_print(f"INFO:投稿ボタンenabled確認({wait_i}秒)", flush=True)
                            break
                        time.sleep(1)
                    if is_disabled:
                        safe_print(f"WARN:投稿ボタンがまだdisabledです、force clickします", flush=True)
                        page.evaluate(f"() => document.querySelector('{sel}').click()")
                    else:
                        btn.click()
                    clicked = True
                    safe_print(f"INFO:投稿ボタンクリック完了", flush=True)
                    break
                except Exception as e:
                    safe_print(f"WARN:投稿ボタン ({sel}) 失敗: {e}", flush=True)
                    continue

            if not clicked:
                # ページ上の全ボタンをデバッグ出力
                all_btns = page.evaluate("() => Array.from(document.querySelectorAll('button, [role=button]')).map(b => b.innerText.trim() + '|' + (b.getAttribute('data-e2e') || ''))")
                safe_print(f"ERROR:投稿ボタンが見つかりませんでした。ページ上のボタン: {all_btns[:10]}", flush=True)
                sys.exit(1)

            # 投稿成功を確認（最大60秒）
            url_before = page.url
            for i in range(60):
                time.sleep(1)
                url_now = page.url

                # URLが変わったら成功
                if url_now != url_before and "upload" not in url_now:
                    safe_print(f"OK:投稿完了 (URL: {url_now})", flush=True)
                    return

                # 「今すぐ投稿」確認ダイアログが出たらクリック
                for confirm_text in ["今すぐ投稿", "Post now", "Post anyway"]:
                    try:
                        btn = page.get_by_text(confirm_text, exact=True).first
                        if btn.is_visible():
                            btn.click()
                            safe_print(f"INFO:確認ダイアログ「{confirm_text}」をクリック", flush=True)
                            time.sleep(5)
                            break
                    except Exception:
                        pass

            # タイムアウト：URLは変わらなかったが投稿された可能性あり
            safe_print(f"OK:投稿ボタンクリック完了（URL未変化）", flush=True)

    except Exception as e:
        safe_print(f"ERROR:{e}", flush=True)
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
        safe_print("ERROR:引数不足 <video_path> <caption または --caption-file path>", flush=True)
        sys.exit(1)

    video = sys.argv[1]
    if sys.argv[2] == "--caption-file" and len(sys.argv) >= 4:
        # UTF-8ファイルからキャプションを読む（文字化け回避）
        with open(sys.argv[3], "r", encoding="utf-8") as f:
            cap = f.read()
    else:
        cap = sys.argv[2]

    run(video, cap)
