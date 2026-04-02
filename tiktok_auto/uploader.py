"""
uploader.py - TikTok への自動アップロード

tiktok-uploader ライブラリを使用してボット検出を回避。
認証: TIKTOK_SESSION_ID 環境変数 or config.py
"""

import os
import json
import tempfile
import logging

import config

logger = logging.getLogger(__name__)


def _session_id() -> str:
    return os.environ.get("TIKTOK_SESSION_ID", "") or config.TIKTOK_SESSION_ID


def _write_cookies_file() -> str:
    """sessionid を Netscape cookie ファイルに書き出して、パスを返す"""
    sid = _session_id()
    if not sid or sid == "your_tiktok_session_id":
        return None

    # Netscape cookie format
    lines = [
        "# Netscape HTTP Cookie File",
        ".tiktok.com\tTRUE\t/\tTRUE\t0\tsessionid\t" + sid,
    ]
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines))
    tmp.close()
    return tmp.name


def upload_to_tiktok(
    video_path: str,
    caption: str,
    headless: bool = True,
) -> bool:
    """
    TikTok に動画をアップロード。
    tiktok-uploader ライブラリ経由でボット検出を回避。
    戻り値: 成功 True / 失敗 False
    """
    if not os.path.exists(video_path):
        logger.error(f"動画ファイルが見つかりません: {video_path}")
        return False

    cookies_path = _write_cookies_file()
    if not cookies_path:
        logger.error("TIKTOK_SESSION_ID が設定されていません")
        return False

    try:
        from tiktok_uploader.upload import upload_video
        logger.info(f"tiktok-uploader でアップロード開始: {video_path}")
        logger.info(f"キャプション: {caption[:50]}...")

        results = upload_video(
            filename=video_path,
            description=caption,
            cookies=cookies_path,
            headless=False,   # ローカルPC実行なのでheadlessオフ（#root hidden回避）
            browser="chrome",
        )

        # results は list（dict or object どちらも対応）
        if results:
            r = results[0]
            success = r.get('success', False) if isinstance(r, dict) else getattr(r, 'success', False)
            if success:
                logger.info("投稿完了!")
                return True
            err = r.get('error', '不明') if isinstance(r, dict) else getattr(r, 'error', '不明')
            logger.error(f"アップロード失敗: {err}")
        else:
            logger.error("結果が空です")
        return False

    except Exception as e:
        logger.error(f"アップロード中にエラー: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)


# --- 動作確認用 ---
if __name__ == "__main__":
    import sys
    import logging
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print("使い方: python uploader.py <video.mp4> <キャプション>")
        sys.exit(1)
    ok = upload_to_tiktok(sys.argv[1], sys.argv[2], headless=False)
    print("成功" if ok else "失敗")
