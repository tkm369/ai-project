"""
Threadsアクセストークンを自動更新するスクリプト
- 有効期限が30日以内に迫ったら更新
- GitHub Actions secrets を gh CLI で自動更新
- collect_analytics.yml から週1で呼び出す
"""
import os
import sys
import requests
import subprocess
from datetime import datetime, timezone
import pytz

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
GH_REPO = "tkm369/sns-auto-poster"


def get_token_info(token):
    """トークンの有効期限を確認"""
    url = "https://graph.threads.net/access_token"
    params = {
        "grant_type": "th_refresh_token",
        "access_token": token,
    }
    resp = requests.get(url, params=params, timeout=10)
    return resp


def refresh_threads_token():
    if not THREADS_ACCESS_TOKEN:
        print("⚠️  THREADS_ACCESS_TOKEN が未設定")
        return False

    print("🔄 Threadsトークンを更新中...")
    resp = get_token_info(THREADS_ACCESS_TOKEN)

    if resp.status_code == 200:
        data = resp.json()
        new_token = data.get("access_token")
        expires_in = data.get("expires_in", 0)  # 秒

        if not new_token:
            print("⚠️  新しいトークンが取得できませんでした")
            return False

        days_left = expires_in // 86400
        print(f"✅ トークン更新成功（有効期限: あと約{days_left}日）")

        # GitHub Secrets を gh CLI で更新
        result = subprocess.run(
            ["gh", "secret", "set", "THREADS_ACCESS_TOKEN",
             "-R", GH_REPO, "--body", new_token],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ GitHub Secrets 更新完了")
            return True
        else:
            print(f"⚠️  GitHub Secrets 更新失敗: {result.stderr}")
            return False
    else:
        print(f"⚠️  トークン更新失敗: {resp.status_code} {resp.text[:200]}")
        return False


if __name__ == "__main__":
    refresh_threads_token()
