"""
auto_set_secret.py
クリップボードを監視して sessionid を検出したら GitHub Secret に自動登録する
"""
import subprocess, sys, time, re
import pyperclip

REPO = "tkm369/sns-auto-poster"
SECRET_NAME = "TIKTOK_SESSION_ID"

# TikTok sessionid の形式: 40文字程度の英数字
SESSION_PATTERN = re.compile(r'^[0-9a-f]{30,80}$')

def looks_like_session_id(text: str) -> bool:
    text = text.strip()
    return bool(SESSION_PATTERN.match(text))

def set_github_secret(value: str) -> bool:
    result = subprocess.run(
        ["gh", "secret", "set", SECRET_NAME, "--repo", REPO, "--body", value],
        capture_output=True, text=True
    )
    return result.returncode == 0

print("=" * 60)
print("  TikTok sessionid 自動取得スクリプト")
print("=" * 60)
print()
print("【手順】")
print("1. ブラウザで TikTok を開く")
print("2. F12 キーで DevTools を開く")
print("3. 上部タブ「Application」をクリック")
print("4. 左メニュー「Cookies」→「https://www.tiktok.com」")
print("5. 「sessionid」の行をクリック")
print("6. Value 列の値をダブルクリックして全選択 → Ctrl+C")
print()
print("コピーを検知したら自動で GitHub Secret に登録します...")
print("(Ctrl+C で終了)")
print()

prev = ""
dots = 0
while True:
    try:
        current = pyperclip.paste().strip()
        if current != prev and looks_like_session_id(current):
            print(f"\n✓ sessionid を検出しました！ ({current[:8]}...{current[-4:]})")
            print("  GitHub Secret に登録中...")
            if set_github_secret(current):
                print(f"  ✓ {REPO} の Secret '{SECRET_NAME}' に登録完了！")
                print()
                print("これで GitHub Actions が自動投稿します。PCは完全オフでOKです。")
                print()
                print("次のステップ: 投稿URLをキューに追加してプッシュ")
                print("  python scheduler.py add <X or Threads の投稿URL>")
                print("  git add tiktok_auto/queue.json && git commit -m 'add post' && git push")
                input("\nEnter を押して終了...")
                break
            else:
                print("  × GitHub Secret の登録に失敗しました。")
                print("  gh auth status を確認してください。")
        prev = current
        time.sleep(0.5)
        dots = (dots + 1) % 4
        print(f"\r待機中{'.' * dots}   ", end="", flush=True)
    except KeyboardInterrupt:
        print("\n終了しました。")
        sys.exit(0)
