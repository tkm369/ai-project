"""
analytics_worker.py - Playwright でTikTok Studioから動画の再生数等を取得する
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

TIKTOK_STUDIO_URL = "https://www.tiktok.com/tiktokstudio/content"


def safe_print(*args, **kwargs):
    text = " ".join(str(a) for a in args)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        print(text.encode('cp932', errors='replace').decode('cp932'), **kwargs)


def get_session_id() -> str:
    return os.environ.get("TIKTOK_SESSION_ID", "") or config.TIKTOK_SESSION_ID


def collect():
    from playwright.sync_api import sync_playwright

    sid = get_session_id()
    if not sid or sid == "your_tiktok_session_id":
        print("ERROR:TIKTOK_SESSION_ID未設定", flush=True)
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # セッションCookie設定
        context.add_cookies([{
            "name": "sessionid",
            "value": sid,
            "domain": ".tiktok.com",
            "path": "/",
        }])

        # 追加Cookie
        extra = os.environ.get("TIKTOK_EXTRA_COOKIES", "")
        if extra:
            try:
                for c in json.loads(extra):
                    context.add_cookies([c])
            except Exception:
                pass

        page = context.new_page()
        page.goto(TIKTOK_STUDIO_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        # 動画リストを取得（CSSセレクタに依存しないテキストパース方式）
        analytics = []
        try:
            import re
            from datetime import datetime

            page_text = page.evaluate("() => document.body.innerText")

            def parse_num(s):
                s = str(s).strip().replace(',', '')
                try:
                    if s.endswith('K') or s.endswith('k'):
                        return int(float(s[:-1]) * 1000)
                    if s.endswith('M') or s.endswith('m'):
                        return int(float(s[:-1]) * 1000000)
                    if '万' in s:
                        return int(float(s.replace('万', '')) * 10000)
                    return int(s)
                except Exception:
                    return None

            # 日付パターン: "Dec 18, 2024" or "2024-12-18" or "12/18/2024"
            date_pattern = re.compile(
                r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}'
                r'|\d{4}[-/]\d{1,2}[-/]\d{1,2}'
                r'|\d{1,2}[-/]\d{1,2}[-/]\d{4}'
            )
            # 数値パターン（再生数・いいね数）: 数字のみ or K/M/万付き
            num_pattern = re.compile(r'^[\d,]+(?:\.\d+)?[KkMm万]?$')

            lines = [l.strip() for l in page_text.split('\n') if l.strip()]

            i = 0
            while i < len(lines):
                date_match = date_pattern.search(lines[i])
                if date_match:
                    date_str = date_match.group(0)
                    created_at = None
                    # 日付パース
                    for fmt in ('%b %d, %Y', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y'):
                        try:
                            created_at = datetime.strptime(date_str.strip(), fmt).isoformat()
                            break
                        except Exception:
                            pass

                    if created_at:
                        # 日付の前後10行以内で数値を探す
                        window = lines[max(0, i-5):min(len(lines), i+10)]
                        nums = []
                        for w in window:
                            w_clean = w.replace(',', '')
                            if num_pattern.match(w_clean):
                                n = parse_num(w_clean)
                                if n is not None and n >= 0:
                                    nums.append(n)

                        if len(nums) >= 2:
                            analytics.append({
                                "created_at": created_at,
                                "views":    nums[0],
                                "likes":    nums[1] if len(nums) > 1 else None,
                                "comments": nums[2] if len(nums) > 2 else None,
                            })
                i += 1

            safe_print(f"INFO:動画 {len(analytics)}件のアナリティクスを取得", flush=True)

        except Exception as e:
            safe_print(f"ERROR:{e}", flush=True)
        finally:
            browser.close()

        print(f"ANALYTICS:{json.dumps(analytics, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    collect()
