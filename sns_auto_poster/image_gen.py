"""
占い・スピリチュアル系フォーチュンカード画像を生成する
グラジェント4種 + Pollinations.ai AI生成4種 = 計8スタイルをA/Bテスト
"""
import os
import random
import textwrap
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SIZE = 1080

FONT_PATHS_REGULAR = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]
FONT_PATHS_BOLD = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
]

# ─── グラジェントスタイル ────────────────────────────────
GRADIENT_STYLES = {
    "gradient_purple": {
        "desc": "紫ピンクグラジェント",
        "bg_top": (45, 5, 80), "bg_bottom": (160, 30, 100),
        "text_color": (255, 255, 255), "accent_color": (255, 210, 80),
        "glow_color": (200, 100, 255), "shadow_color": (10, 0, 30),
        "header": "今日のスピリチュアルメッセージ", "footer": "✦ あなたへのメッセージ ✦",
    },
    "gradient_dark": {
        "desc": "ダークミニマル",
        "bg_top": (8, 8, 18), "bg_bottom": (25, 15, 45),
        "text_color": (235, 225, 255), "accent_color": (160, 130, 255),
        "glow_color": (100, 60, 200), "shadow_color": (0, 0, 0),
        "header": "— message for you —", "footer": "✦ spiritual reading ✦",
    },
    "gradient_sunset": {
        "desc": "サンセットオレンジ",
        "bg_top": (150, 40, 10), "bg_bottom": (220, 130, 20),
        "text_color": (255, 255, 245), "accent_color": (255, 235, 160),
        "glow_color": (255, 180, 80), "shadow_color": (60, 10, 0),
        "header": "今日のあなたへ", "footer": "✦ 心に届くメッセージ ✦",
    },
    "gradient_midnight": {
        "desc": "ミッドナイトブルー",
        "bg_top": (3, 8, 40), "bg_bottom": (15, 40, 100),
        "text_color": (220, 240, 255), "accent_color": (160, 200, 255),
        "glow_color": (80, 140, 255), "shadow_color": (0, 0, 15),
        "header": "星からのメッセージ", "footer": "✦ 今夜、あなたに届く言葉 ✦",
    },
}

# ─── AI生成スタイル（Pollinations.ai） ────────────────────
AI_STYLES = {
    "ai_goddess": {
        "desc": "女神・スピリチュアル女性（AI生成）",
        "prompt": "beautiful ethereal goddess woman, spiritual golden purple glowing aura, mystical soft dreamy bokeh, high quality cinematic portrait, dark background, no text, no watermark",
        "overlay_opacity": 0.50,
        "text_color": (255, 248, 220), "accent_color": (255, 210, 90),
        "shadow_color": (0, 0, 0),
        "header": "女神からのメッセージ", "footer": "✦ あなたへの祝福 ✦",
    },
    "ai_cosmic": {
        "desc": "宇宙・銀河（AI生成）",
        "prompt": "cosmic galaxy nebula stars universe, deep purple blue violet, mystical spiritual beautiful, cinematic, no text, no watermark, high quality 8k",
        "overlay_opacity": 0.45,
        "text_color": (220, 238, 255), "accent_color": (180, 205, 255),
        "shadow_color": (0, 0, 20),
        "header": "星からのメッセージ", "footer": "✦ 宇宙はあなたの味方 ✦",
    },
    "ai_nature": {
        "desc": "神秘的な森・自然（AI生成）",
        "prompt": "sacred magical forest with divine golden light rays through trees, mystical ethereal nature, spiritual glowing atmosphere, beautiful cinematic, no text, no watermark",
        "overlay_opacity": 0.52,
        "text_color": (245, 255, 235), "accent_color": (180, 240, 150),
        "shadow_color": (0, 15, 0),
        "header": "自然からのサイン", "footer": "✦ 今のあなたへ ✦",
    },
    "ai_emotional": {
        "desc": "エモい抽象アート（AI生成）",
        "prompt": "emotional abstract watercolor art, soft dreamy romantic bokeh light, purple pink rose gold pastel gradient, aesthetic beautiful cinematic, no text, no watermark",
        "overlay_opacity": 0.48,
        "text_color": (255, 242, 248), "accent_color": (255, 185, 210),
        "shadow_color": (30, 0, 15),
        "header": "心に届く言葉", "footer": "✦ あなたの気持ちは正しい ✦",
    },
}

ALL_STYLES = list(GRADIENT_STYLES.keys()) + list(AI_STYLES.keys())
STYLES = {**GRADIENT_STYLES, **AI_STYLES}

# ─── コンテンツパターン ────────────────────────────────────
CONTENT_PATTERNS = {
    "hook":         "1行目フック（大文字）",
    "multi_line":   "冒頭2〜3行（中サイズ）",
    "short_phrase": "最短インパクト行（特大）",
    "question":     "疑問形の行を優先表示",
}
ALL_CONTENT_PATTERNS = list(CONTENT_PATTERNS.keys())


# ─── ユーティリティ ───────────────────────────────────────
def _get_font(size, bold=False):
    paths = FONT_PATHS_BOLD if bold else FONT_PATHS_REGULAR
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # ボールドが見つからなければレギュラーにフォールバック
    if bold:
        return _get_font(size, bold=False)
    return ImageFont.load_default()


def _make_gradient(color_top, color_bottom):
    img = Image.new("RGB", (SIZE, SIZE))
    draw = ImageDraw.Draw(img)
    for y in range(SIZE):
        ratio = y / SIZE
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b))
    return img


def _add_bokeh(img, glow_color, count=12, seed=None):
    """グラジェント背景にソフトなボケ丸を重ねてリッチな質感にする"""
    rng = random.Random(seed)
    bokeh = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(bokeh)
    for _ in range(count):
        x = rng.randint(-100, SIZE + 100)
        y = rng.randint(-100, SIZE + 100)
        r = rng.randint(40, 140)
        alpha = rng.randint(15, 50)
        bdraw.ellipse([(x - r, y - r), (x + r, y + r)],
                      fill=(*glow_color, alpha))
    bokeh = bokeh.filter(ImageFilter.GaussianBlur(radius=35))
    return Image.alpha_composite(img.convert("RGBA"), bokeh).convert("RGB")


def _add_center_glow(img, glow_color):
    """中央に柔らかいグロー（光）を追加してテキスト周りを引き立てる"""
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    cx, cy = SIZE // 2, SIZE // 2
    for radius, alpha in [(380, 20), (260, 30), (160, 40)]:
        gdraw.ellipse([(cx - radius, cy - radius), (cx + radius, cy + radius)],
                      fill=(*glow_color, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    return Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")


def _fetch_ai_background(prompt, timeout=55):
    """Pollinations.ai でAI背景画像を生成する（無料・APIキー不要）"""
    import requests
    from urllib.parse import quote
    seed = int(datetime.now().timestamp()) % 99999
    encoded = quote(prompt)
    url = (f"https://image.pollinations.ai/prompt/{encoded}"
           f"?width={SIZE}&height={SIZE}&nologo=true&seed={seed}&enhance=true")
    try:
        res = requests.get(url, timeout=timeout)
        if res.status_code == 200 and len(res.content) > 10000:
            img = Image.open(BytesIO(res.content)).convert("RGB")
            return img.resize((SIZE, SIZE), Image.LANCZOS)
    except Exception as e:
        print(f"  AI画像取得失敗: {e}")
    return None


def _apply_dark_overlay(img, opacity):
    """テキスト可読性のための半透明暗オーバーレイ"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, int(255 * opacity)))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _draw_text_with_shadow(draw, text, font, x, y, color, shadow_color, shadow_offset=3):
    """影付きテキストを描画"""
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=color)


def _draw_text_centered(draw, text, font, y, color, shadow_color):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except AttributeError:
        tw, _ = draw.textsize(text, font=font)
    x = (SIZE - tw) / 2
    _draw_text_with_shadow(draw, text, font, x, y, color, shadow_color)


def _get_content_lines(post_text):
    return [
        l.strip() for l in post_text.strip().split('\n')
        if l.strip() and not l.strip().startswith('#')
    ]


def _pick_best_lines(post_text, max_lines=3):
    """投稿から最もインパクトのある2〜3行を選ぶ"""
    lines = _get_content_lines(post_text)
    if not lines:
        return [""]

    # 短めでインパクトのある行を優先（15文字以下）
    short_lines = [l for l in lines if 4 <= len(l) <= 20]
    # 疑問文を優先
    question_lines = [l for l in lines if "？" in l or "?" in l]

    selected = []
    # 1行目は必ず先頭から取る（フック）
    selected.append(lines[0])

    # 2行目以降: 疑問文 > 短い行 > 通常順
    candidates = question_lines + short_lines + lines[1:]
    seen = set(selected)
    for l in candidates:
        if l not in seen and len(selected) < max_lines:
            selected.append(l)
            seen.add(l)

    return selected


def _extract_image_text(post_text, pattern):
    """コンテンツパターンに応じた表示テキストとフォントサイズを返す"""
    lines = _get_content_lines(post_text)
    if not lines:
        return [""], 58

    if pattern == "hook":
        # 1行目を大きく見せる
        hook = lines[0]
        if len(hook) > 22:
            hook = hook[:20] + "…"
        return [hook], 68

    elif pattern == "multi_line":
        # 2〜3行を中サイズで
        selected = _pick_best_lines(post_text, max_lines=3)
        result = []
        for l in selected:
            result.append(l[:18] + "…" if len(l) > 20 else l)
        return result, 52

    elif pattern == "short_phrase":
        # 最もインパクトのある短いフレーズを特大で
        candidates = [l for l in lines if 4 < len(l) <= 16]
        phrase = min(candidates, key=len) if candidates else lines[0][:14]
        return [phrase], 88

    elif pattern == "question":
        # 疑問文を優先して大きく見せる
        for l in lines:
            if "？" in l or "?" in l:
                text = l[:22] + "…" if len(l) > 24 else l
                return [text], 62
        hook = lines[0][:20]
        if not (hook.endswith("？") or hook.endswith("?")):
            hook += "？"
        return [hook], 62

    return [lines[0][:20]], 62


# ─── 装飾要素 ─────────────────────────────────────────────
def _draw_ornament_lines(draw, accent_color):
    """上下の装飾ラインをダブルラインで描く"""
    y_top = int(SIZE * 0.20)
    y_bot = int(SIZE * 0.80)
    x1, x2 = int(SIZE * 0.10), int(SIZE * 0.90)

    draw.line([(x1, y_top), (x2, y_top)], fill=accent_color, width=2)
    draw.line([(x1, y_top + 5), (x2, y_top + 5)], fill=(*accent_color[:3], 120), width=1)
    draw.line([(x1, y_bot), (x2, y_bot)], fill=accent_color, width=2)
    draw.line([(x1, y_bot - 5), (x2, y_bot - 5)], fill=(*accent_color[:3], 120), width=1)


def _draw_corner_dots(draw, accent_color):
    """四隅にアクセントの小さな菱形を描く"""
    size = 6
    for x, y in [(int(SIZE * 0.10), int(SIZE * 0.20)),
                 (int(SIZE * 0.90), int(SIZE * 0.20)),
                 (int(SIZE * 0.10), int(SIZE * 0.80)),
                 (int(SIZE * 0.90), int(SIZE * 0.80))]:
        draw.polygon([(x, y - size), (x + size, y),
                      (x, y + size), (x - size, y)], fill=accent_color)


# ─── メイン生成関数 ───────────────────────────────────────
def load_style_guide_summary():
    """style_guide.jsonのサマリーを読み込む（なければNone）"""
    path = os.path.join(os.path.dirname(__file__), "style_guide.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("summary")
    except Exception:
        return None


def load_style_guide_top_patterns():
    """style_guide.jsonから高スコアのパターンを最大3件返す"""
    path = os.path.join(os.path.dirname(__file__), "style_guide.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        styles = data.get("styles", [])
        # スコア7以上・スキップなし・いいね数順
        good = [s for s in styles
                if not s.get("skip")
                and s.get("overall_quality_score", 0) >= 7]
        good.sort(key=lambda s: s.get("like_count", 0), reverse=True)
        return good[:3]
    except Exception:
        return []


def build_dynamic_prompt(post_text, style_patterns):
    """
    競合分析パターンとGeminiを使って
    Pollinations.ai用の画像プロンプトを動的に生成する
    """
    from config import GEMINI_API_KEY
    if not GEMINI_API_KEY or not style_patterns:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 参考パターンをまとめる
        pattern_desc = []
        for p in style_patterns:
            parts = []
            if p.get("background_type"):
                parts.append(f"背景:{p['background_type']}")
            if p.get("atmosphere"):
                parts.append(f"雰囲気:{p['atmosphere']}")
            if p.get("key_visual_elements"):
                parts.append(f"要素:{','.join(p['key_visual_elements'][:3])}")
            if p.get("dominant_colors"):
                parts.append(f"色:{','.join(p['dominant_colors'][:2])}")
            pattern_desc.append(" / ".join(parts))

        prompt = f"""以下の条件でThreads投稿用の背景画像のプロンプトを英語で作成してください。

【参考にする人気投稿のビジュアルパターン】
{chr(10).join(f'- {d}' for d in pattern_desc)}

【投稿内容（テーマの参考に）】
{post_text[:100]}

【条件】
- Pollinations.ai（Stable Diffusion系）に渡す英語プロンプト
- 人物を含む場合は美しい日本人女性または東洋系女性
- テキストや文字は含めない（no text, no watermark必須）
- 1080x1080の正方形に映える構図
- 占い・スピリチュアル・恋愛の雰囲気に合うもの
- 高品質・シネマティックな仕上がり

プロンプト文字列のみ返してください（説明不要）:"""

        import time
        time.sleep(13)
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt)
        generated_prompt = response.text.strip()
        # 余計な引用符を除去
        generated_prompt = generated_prompt.strip('"\'')
        print(f"  動的プロンプト生成: {generated_prompt[:80]}...")
        return generated_prompt
    except Exception as e:
        print(f"  動的プロンプト生成失敗: {e}")
        return None


def get_recommended_style():
    """
    style_guide.jsonのデータが十分なら動的生成モードを示す文字列を返す
    データが不足している場合はNone（通常A/Bテストに任せる）
    """
    summary = load_style_guide_summary()
    if not summary or summary.get("total_analyzed", 0) < 3:
        return None
    return "dynamic"  # 動的プロンプト生成モード


def create_fortune_image(post_text, output_path,
                         style="gradient_purple",
                         content_pattern="hook"):
    if style not in ALL_STYLES:
        style = "gradient_purple"
    if content_pattern not in CONTENT_PATTERNS:
        content_pattern = "hook"

    # ─ 背景生成 ─
    # 動的モード: 競合分析パターンからGeminiがプロンプトを生成
    dynamic_img = None
    if style == "dynamic":
        patterns = load_style_guide_top_patterns()
        if patterns:
            dynamic_prompt = build_dynamic_prompt(post_text, patterns)
            if dynamic_prompt:
                print(f"  競合スタイル学習画像を生成中...")
                dynamic_img = _fetch_ai_background(dynamic_prompt)
        if dynamic_img is None:
            print(f"  動的生成失敗 → ai_goddessにフォールバック")
        style = "ai_goddess"  # 動的生成のオーバーレイ設定用

    is_ai = style in AI_STYLES
    s = STYLES[style]

    if dynamic_img is not None:
        # 動的生成成功: そのまま使う
        img = dynamic_img
        is_ai = True
    elif is_ai:
        print(f"  AI画像生成中... ({s['desc']})")
        img = _fetch_ai_background(s["prompt"])
        if img is None:
            print(f"  フォールバック: gradient_purple を使用")
            style = "gradient_purple"
            s = GRADIENT_STYLES[style]
            is_ai = False

    if not is_ai:
        img = _make_gradient(s["bg_top"], s["bg_bottom"])
        img = _add_bokeh(img, s["glow_color"], count=14,
                         seed=hash(post_text[:20]) % 9999)
        img = _add_center_glow(img, s["glow_color"])

    # ─ オーバーレイ ─
    if is_ai:
        img = _apply_dark_overlay(img, s["overlay_opacity"])

    draw = ImageDraw.Draw(img)

    # ─ 装飾 ─
    _draw_ornament_lines(draw, s["accent_color"])
    _draw_corner_dots(draw, s["accent_color"])

    # ─ ヘッダー ─
    header_font = _get_font(32)
    _draw_text_centered(draw, s["header"], header_font,
                        int(SIZE * 0.12), s["accent_color"], s["shadow_color"])

    # ─ メインテキスト（2〜3行・ボールド） ─
    text_lines, font_size = _extract_image_text(post_text, content_pattern)
    main_font = _get_font(font_size, bold=True)
    line_h = int(font_size * 1.55)
    total_h = len(text_lines) * line_h
    y_start = (SIZE - total_h) / 2 - 20

    for i, line in enumerate(text_lines):
        _draw_text_centered(draw, line, main_font,
                            y_start + i * line_h,
                            s["text_color"], s["shadow_color"])

    # ─ フッター ─
    sub_font = _get_font(28)
    _draw_text_centered(draw, s["footer"], sub_font,
                        int(SIZE * 0.84), s["accent_color"], s["shadow_color"])

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    return output_path


def upload_image(image_path):
    """catbox.moe に画像をアップロードしてURLを返す"""
    import requests
    try:
        with open(image_path, "rb") as f:
            res = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": ("image.png", f, "image/png")},
                timeout=30,
            )
        url = res.text.strip()
        if res.status_code == 200 and url.startswith("https://"):
            return url
        print(f"  catbox.moe アップロード失敗: {res.text[:100]}")
        return None
    except Exception as e:
        print(f"  画像アップロード失敗: {e}")
        return None


def cleanup_old_images(images_dir, keep_days=7):
    """指定日数より古い画像を削除"""
    if not os.path.exists(images_dir):
        return
    cutoff = datetime.now() - timedelta(days=keep_days)
    deleted = 0
    for filename in os.listdir(images_dir):
        if not filename.endswith('.png'):
            continue
        try:
            ts = datetime.strptime(filename[:15], "%Y%m%d_%H%M%S")
            if ts < cutoff:
                os.remove(os.path.join(images_dir, filename))
                deleted += 1
        except ValueError:
            pass
    if deleted:
        print(f"  古い画像を{deleted}件削除しました")
