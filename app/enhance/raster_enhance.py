"""點陣後處理：深色筆畫擴張、加深、深色模式。輸入輸出皆為 HxWx3 uint8。"""
from __future__ import annotations

import numpy as np


def thicken_dark(img: np.ndarray, radius: int) -> np.ndarray:
  """以 min-filter 讓深色筆畫往外擴張 radius 像素。"""
  if radius <= 0:
    return img
  out = img
  for _ in range(radius):
    p = np.pad(out, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = out.shape[:2]
    out = np.minimum.reduce([
      p[1:h + 1, 1:w + 1], p[0:h, 1:w + 1], p[2:h + 2, 1:w + 1],
      p[1:h + 1, 0:w], p[1:h + 1, 2:w + 2],
    ])
  return out


_gamma_cache: dict[float, np.ndarray] = {}


def darken(img: np.ndarray, gamma: float) -> np.ndarray:
  """gamma > 1 時讓反鋸齒產生的淺灰線條變深，白底維持白色。"""
  if gamma <= 1.0:
    return img
  lut = _gamma_cache.get(gamma)
  if lut is None:
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(np.power(x, gamma) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    _gamma_cache[gamma] = lut
  return lut[img]


def invert_lightness(img: np.ndarray) -> np.ndarray:
  """反轉亮度但保留色相：黑白互換，紅線仍是紅線（不會變成青色）。"""
  i = img.astype(np.int16)
  shift = 255 - i.max(axis=2, keepdims=True) - i.min(axis=2, keepdims=True)
  return np.clip(i + shift, 0, 255).astype(np.uint8)
