"""
session_keepalive.py - TikTokセッションをHTTPリクエストで維持する
Chrome不要・Session 0で動作可能・ウィンドウ一切なし
"""
import os
import sys
import subprocess
import urllib.request
import urllib.error

SESSION_FILE = r"C:\actions-runner\tiktok_session.txt"


def check_and_keepalive() -> bool:
    if not os.path.exists(SESSION_FILE):
        print("ERROR: session file not found")
        return False

    with open(SESSION_FILE, "r", encoding="ascii") as f:
        sid = f.read().strip()

    if not sid or len(sid) < 10:
        print("ERROR: session file is empty")
        return False

    req = urllib.request.Request(
        "https://www.tiktok.com/api/user/detail/?uniqueId=tiktok",
        headers={
            "Cookie": f"sessionid={sid}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
            # ログインページへのリダイレクトや認証エラーを検出
            if '"statusCode":0' in body or '"user"' in body:
                print(f"OK: session is valid ({sid[:8]}...)")
                return True
            elif "login" in body.lower() or "passport" in body.lower():
                print("ERROR: SESSION_EXPIRED - run setup_login.py")
                return False
            else:
                # レスポンスが取れれば基本的に有効
                print(f"OK: session active ({sid[:8]}...)")
                return True
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(f"ERROR: SESSION_EXPIRED (HTTP {e.code}) - run setup_login.py")
            return False
        print(f"WARN: HTTP {e.code} - session may still be valid")
        return True
    except Exception as e:
        print(f"WARN: request failed ({e}) - skipping")
        return True  # ネットワークエラーはセッション切れとみなさない


def trigger_relogin():
    """セッション切れ検知時にユーザーセッションでauto_relogin.pyを起動する"""
    try:
        # Task Schedulerのタスクを起動（ユーザーセッションで実行される）
        subprocess.run(
            ["schtasks", "/run", "/tn", "TikTokAutoRelogin"],
            capture_output=True, timeout=10
        )
        print("INFO: TikTokAutoRelogin task triggered")
    except Exception as e:
        print(f"WARN: relogin trigger failed: {e}")


if __name__ == "__main__":
    ok = check_and_keepalive()
    if not ok:
        trigger_relogin()
    sys.exit(0 if ok else 1)
