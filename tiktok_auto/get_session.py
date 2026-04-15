"""
TikTokのセッションIDをCDP経由で取得する。
セッション延命のため、毎回TikTok.comを訪問してからCookieを読む。
"""
import sys
import subprocess
import time
import json
import urllib.request
import os

PROFILE_DIR = r"C:\tiktok_debug_profile"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CDP_PORT    = 9224  # uploader_workerの9223とかぶらないよう別ポート


def kill_existing_chrome_on_port():
    """CDPポートを使用中のChromeを終了"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{CDP_PORT}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], timeout=5)
                time.sleep(1)
                break
    except Exception:
        pass


def get_session_id():
    kill_existing_chrome_on_port()

    proc = subprocess.Popen(
        [
            CHROME_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--headless=new",
            f"--remote-allow-origins=http://127.0.0.1:{CDP_PORT}",
            "--no-sandbox",
            "--disable-gpu",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # CDP が起動するまで待つ (最大15秒)
        for _ in range(30):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2
                ) as r:
                    r.read()
                break
            except Exception:
                continue
        else:
            return None

        with urllib.request.urlopen(
            f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=5
        ) as r:
            targets = json.loads(r.read())

        if not targets:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{CDP_PORT}/json/new", timeout=5
            ) as r:
                targets = [json.loads(r.read())]

        ws_url = targets[0]["webSocketDebuggerUrl"]

        import websocket
        ws = websocket.create_connection(ws_url, timeout=10)

        # ★ セッション延命: TikTok.comを訪問してサーバー側のセッションを更新
        ws.send(json.dumps({
            "id": 1,
            "method": "Page.navigate",
            "params": {"url": "https://www.tiktok.com"}
        }))
        ws.recv()  # navigateの応答を受け取る
        time.sleep(4)  # ページ読み込み待機（Cookieがセットされるまで）

        # Cookieを取得
        ws.send(json.dumps({
            "id": 2,
            "method": "Network.getCookies",
            "params": {"urls": ["https://www.tiktok.com", "https://.tiktok.com"]}
        }))
        result = json.loads(ws.recv())
        ws.close()

        cookies = result.get("result", {}).get("cookies", [])
        for c in cookies:
            if c["name"] == "sessionid":
                return c["value"]

        return None
    finally:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                timeout=5, capture_output=True
            )
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            pass


if __name__ == "__main__":
    val = get_session_id()
    if val:
        print(val)
    else:
        print("NOT_FOUND")
        sys.exit(1)
