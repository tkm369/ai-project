"""
composer.py - スクリーンショットを背景動画に合成して縦型TikTok動画を生成
"""

import os
import random
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from moviepy import VideoFileClip, VideoClip, ImageClip, CompositeVideoClip
from moviepy.video.fx import Crop, Resize, Loop, CrossFadeIn

import config

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  画像加工ユーティリティ
# ------------------------------------------------------------------ #

def _rounded_corners(img: Image.Image, radius: int) -> Image.Image:
    """PIL画像に角丸マスクを適用してPNGで返す"""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, img.width, img.height], radius=radius, fill=255)
    img.putalpha(mask)
    return img


def _add_shadow(img: Image.Image, offset: int, blur: int, opacity: int) -> Image.Image:
    """影付き画像を生成（透過PNG）"""
    pad = offset + blur * 2
    canvas_w = img.width  + pad * 2
    canvas_h = img.height + pad * 2

    shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    shadow_mask  = Image.new("L",    (canvas_w, canvas_h), 0)

    # 影の形をマスクで描く
    draw = ImageDraw.Draw(shadow_mask)
    draw.rounded_rectangle(
        [pad + offset, pad + offset,
         pad + offset + img.width, pad + offset + img.height],
        radius=config.CORNER_RADIUS,
        fill=opacity,
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur))
    shadow_layer.putalpha(shadow_mask)

    # 影レイヤーにimg本体を貼る
    shadow_layer.paste(img, (pad, pad), img)
    return shadow_layer


def prepare_screenshot(screenshot_path: str, target_width: int) -> Image.Image:
    """スクショを角丸+影付きに加工して最終的なPIL Imageを返す"""
    img = Image.open(screenshot_path).convert("RGBA")

    # リサイズ (幅を target_width に合わせる)
    ratio  = target_width / img.width
    new_h  = int(img.height * ratio)
    img    = img.resize((target_width, new_h), Image.LANCZOS)

    img    = _rounded_corners(img, config.CORNER_RADIUS)
    img    = _add_shadow(img, config.SHADOW_OFFSET, config.SHADOW_BLUR, config.SHADOW_OPACITY)
    return img


# ------------------------------------------------------------------ #
#  メイン: 動画合成
# ------------------------------------------------------------------ #

def compose_video(
    screenshot_path: str,
    output_path: str,
    caption_text: str = "",
    duration: float = 15.0,
) -> str:
    """
    screenshot_path : スクリーンショット(PNG)のパス
    output_path     : 出力MP4のパス
    caption_text    : TikTokのキャプション用テキスト (映像には入れない)
    duration        : 動画の長さ(秒) ※背景動画より短い場合は背景をループ
    戻り値          : output_path
    """
    # ---- 背景動画をランダムに選ぶ (なければグラデーション生成) ------
    bg_files = []
    if os.path.isdir(config.BACKGROUNDS_DIR):
        bg_files = [
            f for f in os.listdir(config.BACKGROUNDS_DIR)
            if f.lower().endswith((".mp4", ".mov", ".avi"))
        ]

    if bg_files:
        bg_path = os.path.join(config.BACKGROUNDS_DIR, random.choice(bg_files))
        logger.info(f"背景動画: {bg_path}")
        bg_clip = VideoFileClip(bg_path)
        if bg_clip.duration < duration:
            bg_clip = bg_clip.with_effects([Loop(duration=duration)])
        else:
            bg_clip = bg_clip.subclipped(0, duration)
        # 縦型 (9:16) にクロップ
        target_ar = config.VIDEO_WIDTH / config.VIDEO_HEIGHT
        bg_ar     = bg_clip.w / bg_clip.h
        if bg_ar > target_ar:
            new_w = int(bg_clip.h * target_ar)
            bg_clip = bg_clip.with_effects([Crop(width=new_w, x_center=bg_clip.w / 2)])
        else:
            new_h = int(bg_clip.w / target_ar)
            bg_clip = bg_clip.with_effects([Crop(height=new_h, y_center=bg_clip.h / 2)])
        bg_clip = bg_clip.with_effects([Resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT))])
    else:
        # 背景動画なし → 紫グラデーションを自動生成
        logger.info("背景動画なし。グラデーション背景を生成します。")
        W, H = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        def _gradient_frame(t):
            frame = np.zeros((H, W, 3), dtype=np.uint8)
            shift = int(t * 8) % H
            for y in range(H):
                ratio = ((y + shift) % H) / H
                # 明るいピンク→パープルグラデーション
                frame[y, :] = [int(255 - ratio*60), int(100 + ratio*60), int(200 + ratio*55)]
            return frame
        bg_clip = VideoClip(_gradient_frame, duration=duration)
        bg_clip = bg_clip.with_effects([Resize((W, H))])

    # ---- スクリーンショットを加工 ------------------------------------
    ss_target_w = int(config.VIDEO_WIDTH * config.SCREENSHOT_WIDTH_RATIO)
    ss_img      = prepare_screenshot(screenshot_path, ss_target_w)

    # PIL Image → numpy array → ImageClip
    ss_array = np.array(ss_img)
    ss_clip  = ImageClip(ss_array)

    # 表示時間: フェードイン0.3s 後、動画終わりまで表示
    ss_clip = ss_clip.with_start(0.3).with_duration(duration - 0.3)
    ss_clip = ss_clip.with_effects([CrossFadeIn(0.4)])

    # 中央 (X方向) + 上から SCREENSHOT_Y_RATIO の位置
    x_pos = (config.VIDEO_WIDTH  - ss_img.width)  // 2
    y_pos = int(config.VIDEO_HEIGHT * config.SCREENSHOT_Y_RATIO)
    ss_clip = ss_clip.with_position((x_pos, y_pos))

    # ---- 合成 --------------------------------------------------------
    final = CompositeVideoClip([bg_clip, ss_clip], size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
    final = final.with_duration(duration)

    # ---- 書き出し ----------------------------------------------------
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        ffmpeg_params=["-crf", "23"],
        logger=None,
    )
    logger.info(f"動画生成完了: {output_path}")

    bg_clip.close()
    final.close()
    return output_path


# --- 動作確認用 ---
if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print("使い方: python composer.py <screenshot.png> <output.mp4>")
        sys.exit(1)
    compose_video(sys.argv[1], sys.argv[2], duration=15)
