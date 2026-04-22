"""
card_generator.py - 複数スタイルのTikTok用カード画像を生成

スタイル一覧:
  xdark     - X/Twitter ダークモード（既存）
  gradient  - ピンク→パープルグラデーション
  poem      - 詩スタイル（中央寄せ・行間広め）
  light     - Instagram風ライトカード
  line_chat - LINE風チャット吹き出し
  notebook  - ノート罫線スタイル
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH  = 900
CARD_STYLES = ["xdark", "gradient", "poem", "light", "line_chat", "notebook", "list_card"]
# voice_title は音声投稿専用（PDCA のカードスタイル選択対象外）
VOICE_TITLE_STYLE = "voice_title"


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\YuGothB.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap(text: str, font, max_w: int, draw: ImageDraw.Draw) -> list:
    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for ch in para:
            test = cur + ch
            if draw.textbbox((0, 0), test, font=font)[2] > max_w:
                if cur:
                    lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
    return lines


def _mask(img: Image.Image, r: int = 24) -> Image.Image:
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, img.width - 1, img.height - 1], radius=r, fill=255
    )
    out = img.convert("RGBA")
    out.putalpha(m)
    return out


def _lh(draw, font, spacing) -> int:
    return int(draw.textbbox((0, 0), "あ", font=font)[3] * spacing)


# ─────────────────────────────────────────
# Style 1: xdark  (X/Twitterダークモード)
# ─────────────────────────────────────────
def _xdark(text: str, path: str) -> str:
    PAD, FS, LS = 48, 36, 1.55
    CARD, FG = (21, 32, 43), (231, 233, 234)
    font = _get_font(FS)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))
    lines = _wrap(text[:300], font, CARD_WIDTH - PAD * 2, d0)
    lh = _lh(d0, font, LS)
    h = PAD + lh * len(lines) + PAD
    img = Image.new("RGB", (CARD_WIDTH, h), CARD)
    draw = ImageDraw.Draw(img)
    y = PAD
    for ln in lines:
        draw.text((PAD, y), ln, font=font, fill=FG)
        y += lh
    _mask(img, 24).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 2: gradient  (ピンク→パープルグラデ)
# ─────────────────────────────────────────
def _gradient(text: str, path: str) -> str:
    PAD, FS, LS = 52, 38, 1.65
    font = _get_font(FS)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))
    lines = _wrap(text[:250], font, CARD_WIDTH - PAD * 2, d0)
    lh = _lh(d0, font, LS)
    h = PAD * 2 + lh * len(lines)

    # numpy でグラデーション生成（高速）
    t = np.linspace(0, 1, h)
    R = (225 - t * 65).clip(0, 255).astype(np.uint8)
    G = (55  + t * 15).clip(0, 255).astype(np.uint8)
    B = (125 + t * 95).clip(0, 255).astype(np.uint8)
    arr = np.stack([R, G, B], axis=1)[:, np.newaxis, :]
    arr = np.broadcast_to(arr, (h, CARD_WIDTH, 3)).copy()
    img = Image.fromarray(arr)

    draw = ImageDraw.Draw(img)
    y = PAD
    for ln in lines:
        draw.text((PAD + 2, y + 2), ln, font=font, fill=(0, 0, 0))  # shadow
        draw.text((PAD, y), ln, font=font, fill=(255, 255, 255))
        y += lh
    _mask(img, 28).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 3: poem  (詩スタイル・中央寄せ)
# ─────────────────────────────────────────
def _poem(text: str, path: str) -> str:
    PAD, FS, LS = 60, 40, 2.1
    BG, FG, ACC = (12, 10, 22), (240, 235, 255), (155, 95, 218)
    font = _get_font(FS)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))
    lines = _wrap(text[:200], font, CARD_WIDTH - PAD * 2, d0)
    lh = _lh(d0, font, LS)
    h = PAD * 2 + 28 + lh * len(lines) + 28

    img = Image.new("RGB", (CARD_WIDTH, h), BG)
    draw = ImageDraw.Draw(img)
    draw.line([(PAD, PAD // 2), (CARD_WIDTH - PAD, PAD // 2)], fill=ACC, width=2)
    draw.line([(PAD, h - PAD // 2), (CARD_WIDTH - PAD, h - PAD // 2)], fill=ACC, width=2)

    y = PAD + 28
    for ln in lines:
        if not ln:
            y += lh
            continue
        tw = draw.textbbox((0, 0), ln, font=font)[2]
        draw.text(((CARD_WIDTH - tw) // 2, y), ln, font=font, fill=FG)
        y += lh
    _mask(img, 24).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 4: light  (Instagram風ライトカード)
# ─────────────────────────────────────────
def _light(text: str, path: str) -> str:
    PAD, FS, LS = 52, 36, 1.65
    BG, FG, ACC = (255, 255, 255), (30, 30, 30), (210, 70, 110)
    font = _get_font(FS)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))
    lines = _wrap(text[:280], font, CARD_WIDTH - PAD * 2, d0)
    lh = _lh(d0, font, LS)
    h = PAD + lh * len(lines) + PAD

    img = Image.new("RGB", (CARD_WIDTH, h), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 7, h], fill=ACC)                              # アクセントバー
    draw.rectangle([0, 0, CARD_WIDTH - 1, h - 1], outline=(210, 210, 210), width=1)

    y = PAD
    for ln in lines:
        draw.text((PAD, y), ln, font=font, fill=FG)
        y += lh
    _mask(img, 20).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 5: line_chat  (LINE風チャット)
# ─────────────────────────────────────────
def _line_chat(text: str, path: str) -> str:
    PAD, BP, FS, LS = 20, 14, 28, 1.5
    BG          = (234, 237, 244)
    CA, CB      = (94, 200, 120), (255, 255, 255)   # A=緑(右)  B=白(左)
    TA, TB      = (255, 255, 255), (30, 30, 30)
    font = _get_font(FS)
    bw = int(CARD_WIDTH * 0.68)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))

    # 行解析: "A: " / "B: " プレフィックスで振り分け、なければ交互
    rows = [ln.strip() for ln in text.split("\n") if ln.strip()]
    bubbles = []
    for i, row in enumerate(rows):
        if row.startswith("A:"):
            side, txt = "a", row[2:].strip()
        elif row.startswith("B:"):
            side, txt = "b", row[2:].strip()
        else:
            side, txt = ("a" if i % 2 == 0 else "b"), row
        wrapped = _wrap(txt, font, bw - BP * 2, d0)
        line_h = _lh(d0, font, LS)
        bh = BP * 2 + line_h * len(wrapped)
        bubbles.append((side, wrapped, bh, line_h))

    total_h = PAD * 2 + sum(bh + 12 for _, _, bh, _ in bubbles)
    img = Image.new("RGB", (CARD_WIDTH, total_h), BG)
    draw = ImageDraw.Draw(img)

    y = PAD
    for side, wlines, bh, line_h in bubbles:
        col = CA if side == "a" else CB
        tc  = TA if side == "a" else TB
        x   = CARD_WIDTH - PAD - bw if side == "a" else PAD
        draw.rounded_rectangle([x, y, x + bw, y + bh], radius=16, fill=col)
        ty = y + BP
        for ln in wlines:
            draw.text((x + BP, ty), ln, font=font, fill=tc)
            ty += line_h
        y += bh + 12

    _mask(img, 24).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 6: notebook  (ノート罫線スタイル)
# ─────────────────────────────────────────
def _notebook(text: str, path: str) -> str:
    PL, PR, PT, FS, LS = 72, 40, 44, 34, 1.85
    BG   = (255, 253, 238)
    RULE = (178, 210, 240)
    MARG = (218, 95, 95)
    RING = (152, 152, 162)
    FG   = (38, 38, 58)
    font = _get_font(FS)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))
    lines = _wrap(text[:280], font, CARD_WIDTH - PL - PR, d0)
    lh = _lh(d0, font, LS)
    h = PT * 2 + lh * max(len(lines), 4)

    img = Image.new("RGB", (CARD_WIDTH, h), BG)
    draw = ImageDraw.Draw(img)

    # 罫線
    ry = PT + lh
    while ry < h - PT:
        draw.line([(PL - 10, ry), (CARD_WIDTH - PR, ry)], fill=RULE, width=1)
        ry += lh
    # マージン縦線・スパイラルバインダー
    draw.line([(PL - 10, PT // 2), (PL - 10, h - PT // 2)], fill=MARG, width=2)
    for ry in range(PT, h - PT + 1, lh):
        draw.ellipse([14, ry - 7, 30, ry + 7], outline=RING, width=2)

    y = PT
    for ln in lines:
        draw.text((PL, y), ln, font=font, fill=FG)
        y += lh
    _mask(img, 20).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 7: list_card  (保存誘導リスト形式)
# ─────────────────────────────────────────
def _list_card(text: str, path: str) -> str:
    """リスト形式カード: タイトル(amber) + ①②③(blue+white) + CTA(muted blue)"""
    PAD_X, PAD_TOP, PAD_BOT = 52, 44, 40
    FS_T, FS_I, FS_C = 37, 32, 25
    BG       = (13, 17, 30)
    TITLE_COL= (255, 190, 100)   # amber
    NUM_COL  = (120, 160, 255)   # blue numbers
    ITEM_COL = (222, 228, 248)   # near-white items
    CTA_COL  = (95, 125, 170)    # muted blue CTA
    ACC_COL  = (60, 90, 200)     # accent bar

    font_t = _get_font(FS_T)
    font_i = _get_font(FS_I)
    font_c = _get_font(FS_C)

    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))

    # テキストをパース
    raw_lines = [l for l in text.split("\n") if l.strip()]
    title_line = raw_lines[0] if raw_lines else ""
    cta_line   = raw_lines[-1] if len(raw_lines) > 1 else "保存して読み返してね"
    item_lines = raw_lines[1:-1] if len(raw_lines) > 2 else raw_lines[1:]

    # 高さ計算
    lh_t = _lh(d0, font_t, 1.5)
    lh_i = _lh(d0, font_i, 1.7)
    lh_c = _lh(d0, font_c, 1.4)

    sep_gap = 16
    total_items_h = lh_i * len(item_lines)
    h = PAD_TOP + lh_t + sep_gap + 4 + sep_gap + total_items_h + sep_gap + lh_c + PAD_BOT

    img = Image.new("RGB", (CARD_WIDTH, h), BG)
    draw = ImageDraw.Draw(img)

    # 上下アクセントバー
    draw.rectangle([0, 0, CARD_WIDTH, 4], fill=ACC_COL)
    draw.rectangle([0, h - 4, CARD_WIDTH, h], fill=ACC_COL)

    # タイトル
    y = PAD_TOP
    title_wrapped = _wrap(title_line, font_t, CARD_WIDTH - PAD_X * 2, draw)
    for tl in title_wrapped:
        draw.text((PAD_X, y), tl, font=font_t, fill=TITLE_COL)
        y += lh_t

    # セパレータ
    y += sep_gap
    draw.line([(PAD_X, y), (CARD_WIDTH - PAD_X, y)], fill=(40, 55, 90), width=1)
    y += 4 + sep_gap

    # ①②③ アイテム
    for item in item_lines:
        # 番号部分（①②③）と残りを分ける
        num_char = ""
        rest = item
        if item and item[0] in "①②③④⑤⑥⑦⑧⑨":
            num_char = item[0]
            rest = item[1:].lstrip()

        if num_char:
            nw = draw.textbbox((0, 0), num_char, font=font_i)[2]
            draw.text((PAD_X, y), num_char, font=font_i, fill=NUM_COL)
            # 残りテキストを折り返し
            item_wrapped = _wrap(rest, font_i, CARD_WIDTH - PAD_X * 2 - nw - 8, draw)
            ix = PAD_X + nw + 8
        else:
            item_wrapped = _wrap(rest, font_i, CARD_WIDTH - PAD_X * 2, draw)
            ix = PAD_X

        for il in item_wrapped:
            draw.text((ix, y), il, font=font_i, fill=ITEM_COL)
            y += lh_i

    # CTA
    y += sep_gap
    cta_w = draw.textbbox((0, 0), cta_line, font=font_c)[2]
    draw.text(((CARD_WIDTH - cta_w) // 2, y), cta_line, font=font_c, fill=CTA_COL)

    _mask(img, 24).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Style 8: voice_title  (音声投稿用タイトルカード)
# ─────────────────────────────────────────
def _voice_title(text: str, path: str) -> str:
    """音声動画専用タイトルカード（エレガントな深色グラデ・大文字中央寄せ）"""
    PAD_X, PAD_Y = 60, 56
    FS_MAIN, FS_SUB = 52, 26
    BG_TOP  = (8, 5, 20)
    BG_BOT  = (20, 10, 42)
    FG      = (255, 248, 210)
    ACC     = (175, 110, 255)
    GLOW    = (90, 50, 160)
    SUB_COL = (190, 150, 255)
    SUBTITLE = "✦ 恋愛音声コンテンツ ✦"

    font_main = _get_font(FS_MAIN)
    font_sub  = _get_font(FS_SUB)
    d0 = ImageDraw.Draw(Image.new("RGB", (CARD_WIDTH, 100)))

    lines  = _wrap(text[:50], font_main, CARD_WIDTH - PAD_X * 2, d0)
    lh     = _lh(d0, font_main, 1.55)
    sub_h  = _lh(d0, font_sub, 1.4)
    h      = PAD_Y * 2 + 8 + lh * len(lines) + 32 + sub_h + 8

    # numpy グラデーション背景
    t = np.linspace(0, 1, h)
    R = (BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t).clip(0, 255).astype(np.uint8)
    G = (BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t).clip(0, 255).astype(np.uint8)
    B = (BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t).clip(0, 255).astype(np.uint8)
    arr = np.stack([R, G, B], axis=1)[:, np.newaxis, :]
    arr = np.broadcast_to(arr, (h, CARD_WIDTH, 3)).copy()
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # 上下アクセントライン
    draw.rectangle([0, 0, CARD_WIDTH, 5], fill=ACC)
    draw.rectangle([0, h - 5, CARD_WIDTH, h], fill=ACC)

    # タイトル（中央寄せ、グロー効果）
    y = PAD_Y + 8
    for ln in lines:
        tw = draw.textbbox((0, 0), ln, font=font_main)[2]
        x  = (CARD_WIDTH - tw) // 2
        draw.text((x + 3, y + 3), ln, font=font_main, fill=GLOW)   # shadow/glow
        draw.text((x, y), ln, font=font_main, fill=FG)
        y += lh

    # サブタイトル（中央寄せ）
    y += 20
    sw = draw.textbbox((0, 0), SUBTITLE, font=font_sub)[2]
    draw.text(((CARD_WIDTH - sw) // 2, y), SUBTITLE, font=font_sub, fill=SUB_COL)

    _mask(img, 28).save(path, "PNG")
    return path


# ─────────────────────────────────────────
# Public API
# ─────────────────────────────────────────
_DISPATCH = {
    "xdark":       _xdark,
    "gradient":    _gradient,
    "poem":        _poem,
    "light":       _light,
    "line_chat":   _line_chat,
    "notebook":    _notebook,
    "list_card":   _list_card,
    "voice_title": _voice_title,
}


def generate_card(text: str, save_path: str, style: str = "xdark") -> str:
    """
    スタイルを指定してカード画像を生成
    style: "xdark" | "gradient" | "poem" | "light" | "line_chat" | "notebook"
    """
    return _DISPATCH.get(style, _xdark)(text, save_path)


if __name__ == "__main__":
    samples = {
        "xdark":     "好きな人の連絡先があるのに、送れない夜がある。",
        "gradient":  "好きな人の前でだけ、うまく話せなくなる。それだけで、好きってわかる。",
        "poem":      "忘れようとするほど\n思い出す夜がある\nそれが恋だった",
        "light":     "Q. 失恋した後、どうすればいい？\n\nA. まず、ちゃんと泣くこと。\nそれだけで十分な日もある。",
        "line_chat": "A: もう連絡しないって決めたのに\nB: また見ちゃったの？\nA: ...うん\nB: それが好きってことじゃん",
        "notebook":  "好きな人の話題になると\n急に聞き役に回ってしまう\nなんでそうなるんだろう",
    }
    for s, txt in samples.items():
        out = generate_card(txt, f"test_{s}.png", style=s)
        print(f"{s}: {out}")
