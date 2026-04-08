"""
setup_login.py - TikTokに一度だけログインしてセッションを保存する

実行方法:
    python setup_login.py

ブラウザが開くので TikTok にログインして、
ログイン完了後にこのターミナルで Enter を押してください。
以降は自動投稿時にこのセッションが使われます。
"""
import os
from playwright.sync_api import sync_playwright

PROFILE_DIR = os.environ.get("TIKTOK_PROFILE_DIR", r"C:\tiktok_profile")

def main():
    print("=" * 50)
    print("TikTok ログインセットアップ")
    print("=" * 50)
    print(f"プロファイル保存先: {PROFILE_DIR}")
    print()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.new_page() if not context.pages else context.pages[0]
        page.goto("https://www.tiktok.com/login", timeout=30000)

        print("ブラウザが開きました。TikTok にログインしてください。")
        print("ログイン完了後、ここで Enter を押してください...")
        input()

        # ログイン確認
        page.goto("https://www.tiktok.com", timeout=15000)
        page.wait_for_load_state("networkidle")

        cookies = context.cookies()
        session = next((c for c in cookies if c["name"] == "sessionid"), None)
        if session:
            print("✓ ログイン確認完了！セッションを保存しました。")
            print("これで python scheduler.py run で自動投稿が動きます。")
        else:
            print("× ログインが確認できませんでした。もう一度試してください。")

        context.close()

if __name__ == "__main__":
    main()
