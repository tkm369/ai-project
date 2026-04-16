"""
auto_relogin.py - セッション切れ時に自動でChrome開いてログイン完了を検知する
ユーザーがTikTokにログインしたら自動でセッション保存してChromeを閉じる
"""
import subprocess
import time
import json
import urllib.request
import sys
import os

PROFILE_DIR  = r"C:\tiktok_debug_profile"
CHROME_PATH  = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CDP_PORT     = 9225
SESSION_FILE = r"C:\actions-runner\tiktok_session.txt"
TIMEOUT_SEC  = 300  # 5分以内にログインしなければ終了


def kill_chrome_on_profile():
    try:
        r = subprocess.run(
            ["wmic", "process", "where",
             "name='chrome.exe' and commandline like '%tiktok_debug_profile%'",
             "get", "processid"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", line], capture_output=True, timeout=5)
        time.sleep(1)
    except Exception:
        pass


def main():
    print("TikTok自動再ログイン: Chromeを開きます...")
    kill_chrome_on_profile()

    proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.tiktok.com/login",
    ])

    # CDP起動待ち
    for _ in range(20):
        time.sleep(1)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2
            ) as r:
                r.read()
            break
        except Exception:
            continue
    else:
        print("ERROR: ChromeのCDP起動タイムアウト")
        proc.terminate()
        sys.exit(1)

    print(f"TikTokにログインしてください（最大{TIMEOUT_SEC}秒）...")

    import websocket

    deadline = time.time() + TIMEOUT_SEC
    sid = None

    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=5
            ) as r:
                targets = json.loads(r.read())

            page_url = ""
            ws_url = ""
            for t in targets:
                if t.get("type") == "page":
                    page_url = t.get("url", "")
                    ws_url = t.get("webSocketDebuggerUrl", "")
                    break

            # ログインページから離れた = ログイン完了
            if page_url and "login" not in page_url and "passport" not in page_url and "tiktok.com" in page_url:
                if ws_url:
                    ws = websocket.create_connection(ws_url, timeout=10)
                    ws.send(json.dumps({
                        "id": 1,
                        "method": "Network.getCookies",
                        "params": {"urls": ["https://www.tiktok.com"]}
                    }))
                    result = json.loads(ws.recv())
                    ws.close()
                    cookies = result.get("result", {}).get("cookies", [])
                    for c in cookies:
                        if c["name"] == "sessionid" and len(c["value"]) > 10:
                            sid = c["value"]
                            break

                if sid:
                    print(f"ログイン確認完了！セッションを保存します...")
                    with open(SESSION_FILE, "w", encoding="ascii") as f:
                        f.write(sid)
                    print(f"保存完了: {sid[:8]}...")
                    break
        except Exception:
            continue

    # Chrome終了
    try:
        kill_chrome_on_profile()
        proc.terminate()
    except Exception:
        pass

    if sid:
        print("自動再ログイン完了。投稿を再開します。")
        sys.exit(0)
    else:
        print("ERROR: タイムアウト。再度setup_login.pyを実行してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
