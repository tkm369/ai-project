"""
analytics_worker.py - TikTok Studioから再生数・いいね数を取得する
Method 1: ネットワークインターセプト (APIレスポンスを直接取得)
Method 2: ページテキストパース (フォールバック)
"""
import os
import sys
import json
import time
import re
from datetime import datetime

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


def parse_num(s):
    s = str(s).strip().replace(',', '').replace('\u00a0', '').replace(' ', '')
    try:
        if s.endswith('K') or s.endswith('k'):
            return int(float(s[:-1]) * 1000)
        if s.endswith('M') or s.endswith('m'):
            return int(float(s[:-1]) * 1000000)
        if '万' in s:
            return int(float(s.replace('万', '')) * 10000)
        if '千' in s:
            return int(float(s.replace('千', '')) * 1000)
        return int(s)
    except Exception:
        return None


def collect():
    from playwright.sync_api import sync_playwright

    sid = get_session_id()
    if not sid or sid == "your_tiktok_session_id":
        print("ERROR:TIKTOK_SESSION_ID未設定", flush=True)
        sys.exit(1)

    api_responses = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )

        # bot検知回避
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        context.add_cookies([{
            "name": "sessionid",
            "value": sid,
            "domain": ".tiktok.com",
            "path": "/",
        }])

        extra = os.environ.get("TIKTOK_EXTRA_COOKIES", "")
        if extra:
            try:
                for c in json.loads(extra):
                    context.add_cookies([c])
            except Exception:
                pass

        page = context.new_page()

        # APIレスポンスをインターセプト
        def on_response(response):
            url = response.url
            if "tiktok.com" in url and response.status == 200:
                if any(k in url for k in [
                    "item_list", "video/list", "post/list",
                    "aweme/v1/creator", "creator/post",
                    "content/list", "item/list",
                    "publish/video/query",
                    "tiktokstudio/api",
                ]):
                    try:
                        data = response.json()
                        api_responses.append({"url": url, "data": data})
                        safe_print(f"INFO:API捕捉: {url[:100]}", flush=True)
                    except Exception:
                        pass

        page.on("response", on_response)

        safe_print("INFO:TikTok Studio読み込み中...", flush=True)
        try:
            page.goto(TIKTOK_STUDIO_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            safe_print(f"WARN:ページロードタイムアウト: {e}", flush=True)

        # TikTok Studioは重いので長めに待機
        time.sleep(20)

        title = page.title()
        url = page.url
        safe_print(f"INFO:タイトル: {title}", flush=True)
        safe_print(f"INFO:URL: {url}", flush=True)

        # デバッグ用スクリーンショット保存
        try:
            page.screenshot(path=r"C:\actions-runner\debug_analytics.png", full_page=False)
            safe_print("INFO:スクリーンショット保存: C:\\actions-runner\\debug_analytics.png", flush=True)
        except Exception as se:
            safe_print(f"WARN:スクリーンショット失敗: {se}", flush=True)

        # セッション切れ検知
        if "login" in url.lower() or "passport" in url.lower():
            safe_print("ERROR:セッション切れ - ログインページにリダイレクト", flush=True)
            browser.close()
            print("ANALYTICS:[]", flush=True)
            sys.exit(1)

        analytics = []

        # --- APIレスポンスをデバッグ保存（item_listの最初のitem構造を保存） ---
        try:
            item_saved = False
            for r in api_responses:
                if "item_list" not in r["url"]:
                    continue
                d = r["data"]
                # あらゆるネストを試みてitemsを見つける
                def find_items(obj, depth=0):
                    if depth > 3 or not isinstance(obj, dict):
                        return []
                    for k, v in obj.items():
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            if any(x in v[0] for x in ["create_time","createTime","aweme_id","id","video_id"]):
                                return v
                    for k, v in obj.items():
                        if isinstance(v, dict):
                            result = find_items(v, depth+1)
                            if result:
                                return result
                    return []
                items_found = find_items(d)
                if items_found:
                    sample = items_found[0]
                    with open(r"C:\actions-runner\debug_item.json", "w", encoding="utf-8") as f:
                        json.dump(sample, f, ensure_ascii=False, indent=2)
                    safe_print(f"INFO:サンプルitem保存: {list(sample.keys())[:15]}", flush=True)
                    item_saved = True
                    break
            if not item_saved:
                safe_print("WARN:サンプルitem取得失敗", flush=True)
        except Exception as de:
            safe_print(f"WARN:デバッグ保存失敗: {de}", flush=True)

        # --- Method 1: APIインターセプト ---
        for resp in api_responses:
            data = resp["data"]
            # すべての可能な構造を試みる
            items = (
                data.get("aweme_list") or
                data.get("itemList") or
                data.get("item_list") or
                data.get("items") or
                data.get("videoList") or
                (data.get("data") or {}).get("aweme_list") or
                (data.get("data") or {}).get("itemList") or
                (data.get("data") or {}).get("item_list") or
                (data.get("data") or {}).get("items") or
                (data.get("data") or {}).get("list") or
                (data.get("data") or {}).get("videoList") or
                []
            )
            for item in items:
                try:
                    stats = (
                        item.get("statistics") or
                        item.get("stats") or
                        item.get("video_stats") or
                        item.get("stat") or
                        {}
                    )
                    created = (
                        item.get("create_time") or
                        item.get("createTime") or
                        item.get("created_at") or
                        item.get("publish_time") or
                        item.get("publishTime")
                    )
                    if created:
                        created_str = str(created).strip()
                        # Unixタイムスタンプ（整数または文字列）をISO datetimeに変換
                        if isinstance(created, (int, float)) or (
                            created_str.isdigit() and len(created_str) >= 9
                        ):
                            created_at = datetime.fromtimestamp(int(created_str)).isoformat()
                        else:
                            created_at = created_str
                    else:
                        continue

                    def _to_int(v):
                        if v is None:
                            return None
                        try:
                            return int(str(v).replace(',', ''))
                        except (ValueError, TypeError):
                            return None

                    def _get(*keys):
                        """item または stats から最初に見つかった値を返す"""
                        for k in keys:
                            v = item.get(k)
                            if v is None:
                                v = stats.get(k)
                            if v is not None:
                                return v
                        return None

                    views = _to_int(_get(
                        "play_count", "playCount", "view_count", "viewCount",
                        "video_view_count",
                    ))
                    likes = _to_int(_get(
                        "like_count", "likeCount",
                        "digg_count", "diggCount",
                        "heart_count", "heartCount",
                    ))
                    comments = _to_int(_get(
                        "comment_count", "commentCount",
                    ))
                    saves = _to_int(_get(
                        "favorite_count", "favoriteCount",
                        "collect_count", "collectCount",
                        "save_count", "saveCount",
                    ))
                    shares = _to_int(_get(
                        "share_count", "shareCount",
                    ))

                    if views is not None or likes is not None:
                        analytics.append({
                            "created_at": created_at,
                            "views":    views,
                            "likes":    likes,
                            "comments": comments,
                            "saves":    saves,
                            "shares":   shares,
                        })
                except Exception:
                    continue

        safe_print(f"INFO:API経由 {len(analytics)}件取得", flush=True)

        # --- Method 2: ページテキストパース（フォールバック） ---
        if not analytics:
            safe_print("INFO:フォールバック: ページテキストをパース...", flush=True)
            try:
                page_text = page.evaluate("() => document.body.innerText")
                safe_print(f"INFO:ページテキスト長: {len(page_text)}", flush=True)

                # 日付パターン（英語・日本語両対応）
                date_pattern = re.compile(
                    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}'
                    r'|\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?'
                    r'|\d{1,2}[-/]\d{1,2}[-/]\d{4}'
                    r'|\d{1,2}月\d{1,2}日'
                )
                num_pattern = re.compile(r'^[\d,]+(?:\.\d+)?[KkMm万千]?$')

                lines = [l.strip() for l in page_text.split('\n') if l.strip()]
                safe_print(f"INFO:テキスト行数: {len(lines)}", flush=True)

                i = 0
                while i < len(lines):
                    date_match = date_pattern.search(lines[i])
                    if date_match:
                        date_str = date_match.group(0)
                        created_at = None

                        # 月日のみの場合は今年を補完
                        month_day = re.match(r'^(\d{1,2})月(\d{1,2})日$', date_str)
                        if month_day:
                            year = datetime.now().year
                            created_at = (
                                f"{year}-{int(month_day.group(1)):02d}"
                                f"-{int(month_day.group(2)):02d}T00:00:00"
                            )
                        else:
                            for fmt in (
                                '%b %d, %Y', '%Y-%m-%d', '%Y/%m/%d',
                                '%Y年%m月%d日', '%m/%d/%Y', '%d/%m/%Y',
                            ):
                                try:
                                    created_at = datetime.strptime(
                                        date_str.strip(), fmt
                                    ).isoformat()
                                    break
                                except Exception:
                                    pass

                        if created_at:
                            window = lines[max(0, i - 5):min(len(lines), i + 10)]
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

                safe_print(f"INFO:テキストパース {len(analytics)}件取得", flush=True)

            except Exception as e:
                safe_print(f"ERROR:テキストパース失敗: {e}", flush=True)

        browser.close()

    safe_print(f"INFO:合計 {len(analytics)}件のアナリティクスを取得", flush=True)
    print(f"ANALYTICS:{json.dumps(analytics, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    collect()
