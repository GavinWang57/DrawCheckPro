"""從宣傳圖 icon.png 裁出左側圓角方塊圖示，產生 app.ico（exe 用）與 app_icon.png（視窗用）。

用法：.venv\\Scripts\\python tools\\make_icon.py [icon.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "app" / "resources"
# 圓角方塊在 1536×1024 原圖中的外框（含外圈金屬邊）與圓角半徑
BOX = (55, 185, 630, 795)
RADIUS = 95
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def rounded_mask(w: int, h: int, r: float) -> np.ndarray:
  """圓角矩形的抗鋸齒遮罩（0~1）。"""
  ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
  dx = np.maximum(np.maximum(r - xs, xs - (w - r)), 0)
  dy = np.maximum(np.maximum(r - ys, ys - (h - r)), 0)
  dist = np.sqrt(dx * dx + dy * dy) - r
  return np.clip(0.5 - dist, 0, 1)


def build(src: Path) -> Image.Image:
  img = Image.open(src).convert("RGBA")
  x0, y0, x1, y1 = BOX
  crop = np.asarray(img.crop(BOX), dtype=np.float32)
  h, w = crop.shape[:2]
  crop[..., 3] *= rounded_mask(w, h, RADIUS)
  side = max(w, h)
  canvas = np.zeros((side, side, 4), dtype=np.float32)
  ox, oy = (side - w) // 2, (side - h) // 2
  canvas[oy:oy + h, ox:ox + w] = crop
  return Image.fromarray(canvas.round().astype(np.uint8), "RGBA")


def main():
  src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "icon.png"
  OUT_DIR.mkdir(parents=True, exist_ok=True)
  icon = build(src)
  icon.resize((512, 512), Image.LANCZOS).save(OUT_DIR / "app_icon.png")
  icon.resize((256, 256), Image.LANCZOS).save(
    OUT_DIR / "app.ico", sizes=[(s, s) for s in ICO_SIZES])
  print("written:", OUT_DIR / "app_icon.png", OUT_DIR / "app.ico")


if __name__ == "__main__":
  main()
