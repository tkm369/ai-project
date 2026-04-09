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

        # 動画リストを取得
        analytics = []
        try:
            # TikTok Studioの動画カードを取得
            videos = page.evaluate("""() => {
                const results = [];
                // 動画アイテムを探す
                const items = document.querySelectorAll('[class*="video-card"], [class*="content-item"], [data-e2e="video-card"]');
                items.forEach(item => {
                    try {
                        const text = item.innerText;
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                        // 数字を含む行を探す（再生数・いいね数）
                        const nums = lines.filter(l => /^[\\d\\.KMk万]+$/.test(l.replace(/,/g, '')));

                        // 日付を探す
                        const datePattern = /\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}|\\d{1,2}[-/]\\d{1,2}[-/]\\d{4}/;
                        const dateLine = lines.find(l => datePattern.test(l));

                        if (nums.length > 0) {
                            results.push({
                                raw_text: text.substring(0, 200),
                                numbers: nums,
                                date_text: dateLine || '',
                            });
                        }
                    } catch(e) {}
                });
                return results;
            }""")

            if not videos:
                # 別のセレクタを試す
                page_text = page.evaluate("""() => document.body.innerText""")
                safe_print(f"PAGE_TEXT:{page_text[:500]}", flush=True)

            for v in videos[:20]:
                # 数字を解析（K=千、M=百万）
                def parse_num(s):
                    s = s.strip().replace(',', '')
                    if s.endswith('K') or s.endswith('k'):
                        return int(float(s[:-1]) * 1000)
                    if s.endswith('M') or s.endswith('m'):
                        return int(float(s[:-1]) * 1000000)
                    if s.endswith('万'):
                        return int(float(s[:-1]) * 10000)
                    try:
                        return int(s)
                    except:
                        return None

                nums = [parse_num(n) for n in v.get('numbers', []) if parse_num(n) is not None]
                date_text = v.get('date_text', '')

                # 日付をパース
                import re
                from datetime import datetime
                created_at = None
                date_match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_text)
                if date_match:
                    try:
                        created_at = datetime(
                            int(date_match.group(1)),
                            int(date_match.group(2)),
                            int(date_match.group(3))
                        ).isoformat()
                    except:
                        pass

                if nums and created_at:
                    analytics.append({
                        "created_at": created_at,
                        "views": nums[0] if len(nums) > 0 else None,
                        "likes": nums[1] if len(nums) > 1 else None,
                        "comments": nums[2] if len(nums) > 2 else None,
                    })

        except Exception as e:
            safe_print(f"ERROR:{e}", flush=True)
        finally:
            browser.close()

        print(f"ANALYTICS:{json.dumps(analytics, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    collect()
