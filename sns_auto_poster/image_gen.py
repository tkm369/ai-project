"""
占い・スピリチュアル系フォーチュンカード画像を生成する
複数スタイルをA/Bテストで自動最適化
"""
import os
import textwrap
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

SIZE = 1080

FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
]

# スタイル定義
STYLES = {
    "gradient_purple": {
        "desc": "紫ピンクグラジェント（神秘系）",
        "bg_top": (60, 10, 100),
        "bg_bottom": (180, 40, 110),
        "text_color": (255, 255, 255),
        "accent_color": (255, 215, 90),
        "shadow_color": (20, 5, 40),
        "header": "今日のスピリチュアルメッセージ",
        "footer": "あなたへのメッセージ",
    },
    "dark_minimal": {
        "desc": "ダークミニマル（クール系）",
        "bg_top": (10, 10, 20),
        "bg_bottom": (30, 20, 50),
        "text_color": (230, 220, 255),
        "accent_color": (150, 120, 255),
        "shadow_color": (0, 0, 0),
        "header": "message for you",
        "footer": "spiritual reading",
    },
    "warm_sunset": {
        "desc": "サンセットオレンジ（温かみ系）",
        "bg_top": (180, 60, 20),
        "bg_bottom": (240, 160, 30),
        "text_color": (255, 255, 240),
        "accent_color": (255, 240, 180),
        "shadow_color": (80, 20, 0),
        "header": "今日のあなたへ",
        "footer": "心に届くメッセージ",
    },
    "midnight_blue": {
        "desc": "ミッドナイトブルー（星空系）",
        "bg_top": (5, 10, 50),
        "bg_bottom": (20, 50, 120),
        "text_color": (220, 235, 255),
        "accent_color": (180, 210, 255),
        "shadow_color": (0, 0, 20),
        "header": "星からのメッセージ",
        "footer": "今夜、あなたに届く言葉",
    },
}

ALL_STYLES = list(STYLES.keys())

# 画像コンテンツパターン定義
CONTENT_PATTERNS = {
    "hook": "1行目フック（大文字）",
    "multi_line": "冒頭2〜3行（中サイズ）",
    "short_phrase": "最短インパクト行（特大）",
    "question": "疑問形の行を優先表示",
}
ALL_CONTENT_PATTERNS = list(CONTENT_PATTERNS.keys())


def _get_font(size):
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
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


def _draw_stars(draw, count=40, color=(255, 255, 255), seed=42):
    import random
    random.seed(seed)
    for _ in range(count):
        x = random.randint(0, SIZE)
        y = random.randint(0, SIZE)
        r = random.randint(1, 3)
        draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=color)


def _draw_text_centered(draw, text, font, y, color, shadow_color):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except AttributeError:
        tw, _ = draw.textsize(text, font=font)
    x = (SIZE - tw) / 2
    draw.text((x + 2, y + 2), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=color)


def _get_content_lines(post_text):
    """投稿テキストから有効な行（空行・ハッシュタグ除く）を返す"""
    return [
        l.strip() for l in post_text.strip().split('\n')
        if l.strip() and not l.strip().startswith('#')
    ]


def _extract_image_text(post_text, pattern):
    """コンテンツパターンに応じて画像に表示するテキストを抽出する
    Returns: (lines: list[str], font_size: int)
    """
    lines = _get_content_lines(post_text)
    if not lines:
        return [""], 62

    if pattern == "hook":
        # 1行目のみ、大フォント
        hook = lines[0]
        if len(hook) > 28:
            hook = hook[:26] + "…"
        return [hook], 62

    elif pattern == "multi_line":
        # 冒頭2〜3行、中フォント
        selected = []
        for l in lines[:4]:
            if len(l) <= 22:
                selected.append(l)
            else:
                selected.append(l[:20] + "…")
            if len(selected) >= 3:
                break
        return selected, 44

    elif pattern == "short_phrase":
        # 最も短い行を特大フォントで（5文字以上）
        candidates = [l for l in lines if 4 < len(l) <= 20]
        if candidates:
            phrase = min(candidates, key=len)
        else:
            phrase = lines[0][:16]
        return [phrase], 80

    elif pattern == "question":
        # 疑問形の行を優先、なければhookに「？」
        for l in lines:
            if "？" in l or "?" in l:
                if len(l) > 28:
                    l = l[:26] + "…"
                return [l], 58
        hook = lines[0]
        if not (hook.endswith("？") or hook.endswith("?")):
            hook = hook[:22] + "？"
        return [hook], 58

    return [lines[0]], 62


def create_fortune_image(post_text, output_path, style="gradient_purple", content_pattern="hook"):
    """
    スタイル・コンテンツパターン指定でフォーチュンカード画像を生成して保存する
    Args:
        post_text: 投稿テキスト
        output_path: 保存先パス (.png)
        style: スタイル名（STYLES のキー）
        content_pattern: コンテンツパターン（CONTENT_PATTERNS のキー）
    """
    if style not in STYLES:
        style = "gradient_purple"
    if content_pattern not in CONTENT_PATTERNS:
        content_pattern = "hook"

    s = STYLES[style]

    img = _make_gradient(s["bg_top"], s["bg_bottom"])
    draw = ImageDraw.Draw(img)

    # 星の装飾
    _draw_stars(draw, count=35, color=s["accent_color"])

    # 区切りライン
    lw = 2
    draw.line([(SIZE * 0.1, SIZE * 0.22), (SIZE * 0.9, SIZE * 0.22)],
              fill=s["accent_color"], width=lw)
    draw.line([(SIZE * 0.1, SIZE * 0.78), (SIZE * 0.9, SIZE * 0.78)],
              fill=s["accent_color"], width=lw)

    # ヘッダー
    header_font = _get_font(34)
    _draw_text_centered(draw, s["header"], header_font,
                        SIZE * 0.25, s["accent_color"], s["shadow_color"])

    # コンテンツパターンに応じたテキスト抽出
    text_lines, font_size = _extract_image_text(post_text, content_pattern)
    main_font = _get_font(font_size)

    # 行間はフォントサイズに比例
    line_h = int(font_size * 1.3)
    # 折り返し幅もフォントサイズに反比例
    wrap_width = max(8, int(900 / font_size))

    # 全行を折り返し展開
    all_wrapped = []
    for line in text_lines:
        wrapped = textwrap.wrap(line, width=wrap_width) or [line]
        all_wrapped.extend(wrapped)

    total_h = len(all_wrapped) * line_h
    y_start = (SIZE - total_h) / 2 - 10

    for i, line in enumerate(all_wrapped):
        _draw_text_centered(draw, line, main_font,
                            y_start + i * line_h,
                            s["text_color"], s["shadow_color"])

    # フッター
    sub_font = _get_font(30)
    _draw_text_centered(draw, s["footer"], sub_font,
                        SIZE * 0.81, s["accent_color"], s["shadow_color"])

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    return output_path


def upload_image(image_path):
    """catbox.moe（無料CDN）に画像をアップロードしてURLを返す"""
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
