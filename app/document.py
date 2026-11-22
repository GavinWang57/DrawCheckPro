"""開啟的圖面：保留原始檔位元組，增強版本只存在記憶體中。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pymupdf as fitz

from app.enhance import raster_enhance as rx
from app.enhance.vector_enhance import VectorParams, enhance_forms, enhance_page

MODE_VECTOR = "vector"
MODE_RASTER = "raster"
MODE_OFF = "off"


@dataclass(frozen=True)
class ViewSettings:
  mode: str = MODE_VECTOR
  vector: VectorParams = field(default_factory=VectorParams)
  min_line_px: float = 1.0
  raster_radius: int = 1
  gamma: float = 1.6
  dark: bool = False
  min_px_on: bool = True
  raster_on: bool = True
  gamma_on: bool = True

  def with_(self, **kw) -> "ViewSettings":
    return replace(self, **kw)


def file_sha256(path: str | Path) -> str:
  h = hashlib.sha256()
  with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
      h.update(chunk)
  return h.hexdigest()


class DrawingDocument:
  def __init__(self, path: str | Path):
    self.path = Path(path)
    self._data = self.path.read_bytes()
    self.sha256 = hashlib.sha256(self._data).hexdigest()
    self.base = fitz.open(stream=self._data, filetype="pdf")
    self._settings = ViewSettings()
    self._enh: fitz.Document | None = None
    self._enh_pages: set[int] = set()
    self._failed_pages: set[int] = set()
    self._dlists: dict[tuple[str, int], fitz.DisplayList] = {}

  @property
  def page_count(self) -> int:
    return self.base.page_count

  @property
  def settings(self) -> ViewSettings:
    return self._settings

  def set_settings(self, s: ViewSettings):
    if s.vector != self._settings.vector:
      self._drop_enhanced()
    self._settings = s

  def page_rect(self, pno: int) -> fitz.Rect:
    return self.base[pno].rect

  def rotation_matrix(self, pno: int) -> fitz.Matrix:
    return self.base[pno].rotation_matrix

  def derotation_matrix(self, pno: int) -> fitz.Matrix:
    return self.base[pno].derotation_matrix

  def is_vector_failed(self, pno: int) -> bool:
    return pno in self._failed_pages

  def _drop_enhanced(self):
    if self._enh is not None:
      self._enh.close()
    self._enh = None
    self._enh_pages.clear()
    self._failed_pages.clear()
    self._dlists = {k: v for k, v in self._dlists.items() if k[0] != "enh"}

  def _enhanced_page(self, pno: int) -> fitz.Page:
    if self._enh is None:
      self._enh = fitz.open(stream=self._data, filetype="pdf")
      enhance_forms(self._enh, self._settings.vector)
    page = self._enh[pno]
    if pno not in self._enh_pages:
      try:
        enhance_page(self._enh, page, self._settings.vector)
      except Exception:
        self._failed_pages.add(pno)
        self._enh.close()
        self._enh = None
        self._enh_pages.clear()
        return self.base[pno]
      self._enh_pages.add(pno)
      page = self._enh[pno]
    return page

  def fresh_copy(self, enhanced: bool) -> fitz.Document:
    """從原始位元組開一份新的記憶體副本（輸出 / 列印用）；enhanced 時套用目前的向量加粗參數。"""
    doc = fitz.open(stream=self._data, filetype="pdf")
    if enhanced:
      enhance_forms(doc, self._settings.vector)
      for page in doc:
        try:
          enhance_page(doc, page, self._settings.vector)
        except Exception:
          pass  # 解析失敗的頁面保留原樣
    return doc

  def _display_list(self, pno: int) -> fitz.DisplayList:
    use_enh = self._settings.mode == MODE_VECTOR and pno not in self._failed_pages
    key = ("enh" if use_enh else "base", pno)
    dl = self._dlists.get(key)
    if dl is None:
      page = self._enhanced_page(pno) if use_enh else self.base[pno]
      if use_enh and pno in self._failed_pages:
        key = ("base", pno)
      dl = page.get_displaylist()
      self._dlists[key] = dl
    return dl

  def render(self, pno: int, zoom: float,
             clip: fitz.Rect | None = None) -> tuple[np.ndarray, fitz.IRect]:
    """以 zoom（像素/pt）渲染 clip 區域（顯示座標）。

    回傳 (套用全部增強後的 RGB 陣列, 該陣列在 zoom 像素座標中的位置)。
    """
    s = self._settings
    min_px = s.min_line_px if s.min_px_on and s.mode != MODE_OFF else 0.0
    fitz.TOOLS.set_graphics_min_line_width(min_px)
    dl = self._display_list(pno)
    mat = fitz.Matrix(zoom, zoom)
    area = fitz.Rect(dl.rect) if clip is None else fitz.Rect(clip) & dl.rect
    target = (area * mat).irect
    radius = 0
    if s.mode == MODE_RASTER and s.raster_on:
      radius = s.raster_radius
    elif s.mode == MODE_VECTOR and pno in self._failed_pages:
      radius = max(1, s.raster_radius)
    if radius:
      pad = (radius + 1) / zoom
      area = fitz.Rect(area.x0 - pad, area.y0 - pad, area.x1 + pad, area.y1 + pad)
    pix = dl.get_pixmap(matrix=mat, clip=area, alpha=False, colorspace=fitz.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    img = img[:, : pix.width * 3].reshape(pix.height, pix.width, 3)
    if radius:
      img = rx.thicken_dark(img, radius)
    x_off, y_off = max(0, target.x0 - pix.x), max(0, target.y0 - pix.y)
    img = img[y_off:y_off + target.height, x_off:x_off + target.width]
    x0, y0 = pix.x + x_off, pix.y + y_off
    target = fitz.IRect(x0, y0, x0 + img.shape[1], y0 + img.shape[0])
    if s.mode != MODE_OFF and s.gamma_on:
      img = rx.darken(img, s.gamma)
    if s.dark:
      img = rx.invert_lightness(img)
    return np.ascontiguousarray(img), target

  def close(self):
    self._drop_enhanced()
    self._dlists.clear()
    self.base.close()
