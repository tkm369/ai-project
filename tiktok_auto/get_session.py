"""
TikTokのセッションIDをPlaywrightプロファイルから取得する。
setup_login.py で一度ログインしておけば、以降は自動で取得できる。
"""
import sys
import sqlite3
import os
import glob

PROFILE_DIR = r"C:\tiktok_debug_profile"


def get_session_id():
    # プロファイル内のCookiesファイルを検索
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


if __name__ == "__main__":
    val = get_session_id()
    if val:
        print(val)
    else:
        print("NOT_FOUND")
        sys.exit(1)
