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
import sys

PROFILE_DIR  = r"C:\tiktok_debug_profile"
CHROME_PATH  = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SESSION_FILE = r"C:\actions-runner\tiktok_session.txt"
GET_SESSION  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "get_session.py")
PYTHON       = sys.executable


def kill_chrome_using_profile():
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
                subprocess.run(["taskkill", "/F", "/PID", line], capture_output=True, timeout=5)
                print(f"Chrome PID {line} を終了しました")
        time.sleep(1)
    except Exception:
        pass


def main():
    print("=" * 50)
    print("TikTok ログインセットアップ")
    print("=" * 50)
    print(f"プロファイル: {PROFILE_DIR}")
    print()

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
    time.sleep(3)

    # CDP経由でセッションIDを取得してファイルに保存
    print("\nセッションIDを取得中...")
    result = subprocess.run(
        [PYTHON, GET_SESSION],
        capture_output=True, text=True, timeout=60
    )
    sid = result.stdout.strip()

    if sid and sid != "NOT_FOUND" and len(sid) > 10:
        with open(SESSION_FILE, "w", encoding="ascii") as f:
            f.write(sid)
        print(f"ログイン確認完了！")
        print(f"sessionid: {sid[:8]}...{sid[-4:]}")
        print(f"保存先: {SESSION_FILE}")
        print("\nこれで自動投稿が動きます。次回から手動操作は不要です。")
    else:
        print("\nsessionidが取得できませんでした。")
        print("TikTokにログインできているか確認して、もう一度試してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
