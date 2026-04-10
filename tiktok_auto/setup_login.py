"""
setup_login.py - TikTokに一度だけログインしてセッションを保存する

実行方法:
    python setup_login.py

Chromeが開くので TikTok にログインして、
ログイン完了後にこのターミナルで Enter を押してください。
"""
import os
import subprocess
import time
import sqlite3
import glob
import sys

PROFILE_DIR = r"C:\tiktok_debug_profile"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def kill_chrome_using_profile():
    """プロファイルを使用中のChromeを終了させる"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             f"name='chrome.exe' and commandline like '%tiktok_debug_profile%'",
             "get", "processid"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", line], timeout=5)
                print(f"Chrome PID {line} を終了しました")
        time.sleep(1)
    except Exception:
        pass


def get_session_id():
    candidates = (
        glob.glob(os.path.join(PROFILE_DIR, "**", "Network", "Cookies"), recursive=True) +
        glob.glob(os.path.join(PROFILE_DIR, "**", "Cookies"), recursive=True)
    )
    for path in candidates:
        try:
            uri = "file:" + path.replace(os.sep, "/") + "?immutable=1"
            conn = sqlite3.connect(uri, uri=True)
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in c.fetchall()]
            if not tables:
                conn.close()
                continue
            table = "cookies" if "cookies" in tables else tables[0]
            c.execute(
                f"SELECT value FROM {table} "
                f"WHERE host_key LIKE '%tiktok.com' AND name='sessionid'"
            )
            rows = c.fetchall()
            conn.close()
            if rows and rows[0][0]:
                return rows[0][0]
        except Exception:
            continue
    return None


def main():
    print("=" * 50)
    print("TikTok ログインセットアップ")
    print("=" * 50)
    print(f"プロファイル: {PROFILE_DIR}")
    print()

    # 既存のChrome（このプロファイルを使用中）を終了
    kill_chrome_using_profile()

    if not os.path.exists(CHROME_PATH):
        print(f"Chromeが見つかりません: {CHROME_PATH}")
        sys.exit(1)

    os.makedirs(PROFILE_DIR, exist_ok=True)
    proc = subprocess.Popen([
        CHROME_PATH,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.tiktok.com/login",
    ])

    print("Chromeが開きました。TikTokにログインしてください。")
    print("ログイン完了後、ここで Enter を押してください...")
    input()

    # Chromeを閉じてCookiesをフラッシュ
    proc.terminate()
    time.sleep(2)

    sid = get_session_id()
    if sid:
        print(f"\nログイン確認完了！")
        print(f"sessionid: {sid[:16]}...")
        print("\nこれで自動投稿が動きます。次回から手動操作は不要です。")
    else:
        print("\nsessionidが見つかりませんでした。")
        print("TikTokにログインできているか確認して、もう一度試してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
