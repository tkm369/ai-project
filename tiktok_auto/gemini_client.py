"""
gemini_client.py - Gemini API 共通クライアント

エラー種別を判定してリトライ戦略を切り替える:
  - 分単位レートリミット (PerMinute) → 最大3回、指数バックオフでリトライ
  - 日次クォータ枯渇 (PerDay / limit:0) → 即座に失敗（待っても無駄）
  - その他エラー → 即座に失敗
"""
import json
import os
import time
import urllib.error
import urllib.request
import logging

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.0-flash"
GEMINI_URL     = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


class GeminiQuotaExhausted(Exception):
    """日次クォータ枯渇 — その日はリトライしても無意味"""


class GeminiUnavailable(Exception):
    """API キー未設定など、そもそも呼び出せない状態"""


def _is_daily_quota_error(err_body: str) -> bool:
    """エラーボディが日次クォータ枯渇かどうか判定"""
    indicators = [
        "PerDay",
        "free_tier_input_token_count",
        "RESOURCE_EXHAUSTED",
        '"limit": 0',
        "'limit': 0",
        "limit: 0",
    ]
    return any(ind in err_body for ind in indicators)


def call_gemini(
    prompt: str,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    response_json: bool = False,
) -> str:
    """
    Gemini API を呼び出してテキストを返す。

    Args:
        prompt:        プロンプト文字列
        max_tokens:    最大出力トークン数
        temperature:   温度パラメータ
        response_json: True なら responseMimeType=application/json を指定

    Returns:
        生成テキスト（str）

    Raises:
        GeminiUnavailable:     API キー未設定
        GeminiQuotaExhausted:  日次クォータ枯渇
        RuntimeError:          3回リトライ後も失敗
    """
    if not GEMINI_API_KEY:
        raise GeminiUnavailable("GEMINI_API_KEY が未設定です")

    gen_config: dict = {"maxOutputTokens": max_tokens, "temperature": temperature}
    if response_json:
        gen_config["responseMimeType"] = "application/json"

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }).encode("utf-8")

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if e.code == 429:
                if _is_daily_quota_error(err_body):
                    # 日次クォータ枯渇 → リトライ不要
                    logger.error(
                        f"Gemini 日次クォータ枯渇。本日はスキップします。"
                        f"（有料プランへの切り替えを推奨）"
                    )
                    raise GeminiQuotaExhausted(
                        f"Daily quota exhausted: {err_body[:200]}"
                    )
                else:
                    # 分単位レートリミット → バックオフしてリトライ
                    if attempt < 2:
                        wait = 65 * (attempt + 1)
                        logger.info(
                            f"Gemini 分単位レートリミット、{wait}秒待機"
                            f" (attempt {attempt+1}/3)"
                        )
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Gemini 3回リトライ失敗: {e}")
            else:
                logger.error(f"Gemini HTTPエラー {e.code}: {err_body[:200]}")
                raise

        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                if _is_daily_quota_error(err_str):
                    logger.error("Gemini 日次クォータ枯渇。本日はスキップします。")
                    raise GeminiQuotaExhausted(err_str[:200])
                if attempt < 2:
                    wait = 65 * (attempt + 1)
                    logger.info(f"Gemini レートリミット、{wait}秒待機 (attempt {attempt+1}/3)")
                    time.sleep(wait)
                    continue
            logger.error(f"Gemini 呼び出し失敗: {e}")
            raise

    raise RuntimeError("Gemini API 3回リトライ失敗")
