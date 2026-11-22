"""頁面分塊渲染：依縮放等級切成 512px 方塊，LRU 快取，缺塊時先畫低解析預覽並延後補渲染。"""
from __future__ import annotations

import math
import time
from collections import OrderedDict

import numpy as np
import pymupdf as fitz
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

from app.document import DrawingDocument

TILE = 512
CACHE_PIXELS = 96_000_000
PREVIEW_MAX_PX = 2400
BATCH_MS = 50


def quantize_zoom(scale: float) -> float:
  """往上取到 2^(1/4) 的倍數，讓重繪時能重用快取，且解析度不低於螢幕所需。"""
  scale = min(max(scale, 0.05), 64.0)
  return 2 ** (math.ceil(math.log2(scale) * 4 - 1e-6) / 4)


def to_pixmap(img: np.ndarray) -> QPixmap:
  h, w = img.shape[:2]
  qimg = QImage(img.data, w, h, 3 * w, QImage.Format.Format_RGB888)
  return QPixmap.fromImage(qimg.copy())


class TileCache:
  def __init__(self, budget: int = CACHE_PIXELS):
    self.budget = budget
    self.used = 0
    self._d: OrderedDict[tuple, tuple[QPixmap, QRectF]] = OrderedDict()

  def get(self, key):
    v = self._d.get(key)
    if v is not None:
      self._d.move_to_end(key)
    return v

  def put(self, key, pix: QPixmap, rect: QRectF):
    self._d[key] = (pix, rect)
    self.used += pix.width() * pix.height()
    while self.used > self.budget and len(self._d) > 1:
      _, (old, _) = self._d.popitem(last=False)
      self.used -= old.width() * old.height()

  def clear(self):
    self._d.clear()
    self.used = 0


class PageItem(QGraphicsItem):
  """一頁圖面。座標單位 = 顯示座標的 pt（已套用頁面旋轉）。"""

  def __init__(self, doc: DrawingDocument, pno: int, cache: TileCache):
    super().__init__()
    self.doc, self.pno, self.cache = doc, pno, cache
    r = doc.page_rect(pno)
    self._rect = QRectF(r.x0, r.y0, r.width, r.height)
    self._preview: tuple[QPixmap, QRectF] | None = None
    self._pending: OrderedDict[tuple, QRectF] = OrderedDict()
    self._level = 0.0
    self._timer = QTimer()
    self._timer.setSingleShot(True)
    self._timer.timeout.connect(self._render_pending)
    self.setZValue(-100)
    self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)

  def boundingRect(self) -> QRectF:
    return self._rect

  def invalidate(self):
    self._preview = None
    self._pending.clear()
    self.update()

  def _ensure_preview(self):
    if self._preview is None:
      long_side = max(self._rect.width(), self._rect.height()) or 1
      z = min(2.0, PREVIEW_MAX_PX / long_side)
      img, ir = self.doc.render(self.pno, z)
      self._preview = (to_pixmap(img), QRectF(ir.x0 / z, ir.y0 / z, ir.width / z, ir.height / z))
    return self._preview

  def paint(self, painter, option: QStyleOptionGraphicsItem, widget=None):
    t = painter.worldTransform()
    dpr = painter.device().devicePixelRatioF() if painter.device() else 1.0
    level = quantize_zoom(math.hypot(t.m11(), t.m12()) * dpr)
    if level != self._level:
      self._pending.clear()
      self._level = level
    exposed = option.exposedRect.intersected(self._rect)
    if exposed.isEmpty():
      return
    painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform, True)
    painter.setRenderHint(painter.RenderHint.Antialiasing, False)

    span = TILE / level
    tx0, tx1 = int(exposed.left() // span), int(exposed.right() // span)
    ty0, ty1 = int(exposed.top() // span), int(exposed.bottom() // span)
    tiles, missing = [], False
    for ty in range(ty0, ty1 + 1):
      for tx in range(tx0, tx1 + 1):
        key = (id(self.doc), self.pno, level, tx, ty)
        hit = self.cache.get(key)
        if hit:
          tiles.append(hit)
        else:
          missing = True
          self._pending[key] = QRectF(tx * span, ty * span, span, span)
    if missing:
      pix, r = self._ensure_preview()
      painter.drawPixmap(r, pix, QRectF(pix.rect()))
      self._timer.start(0)
    for pix, r in tiles:
      painter.drawPixmap(r, pix, QRectF(pix.rect()))

  def _render_pending(self):
    deadline = time.perf_counter() + BATCH_MS / 1000
    while self._pending and time.perf_counter() < deadline:
      key, r = self._pending.popitem(last=False)
      level = key[2]
      if level != self._level or self.cache.get(key):
        continue
      overlap = 1.0 / level  # 多 1px，避免相鄰分塊之間露出背景色的細縫
      clip = fitz.Rect(r.left(), r.top(), r.right() + overlap, r.bottom() + overlap)
      img, ir = self.doc.render(self.pno, level, clip)
      if img.size == 0:
        continue
      rect = QRectF(ir.x0 / level, ir.y0 / level, ir.width / level, ir.height / level)
      self.cache.put(key, to_pixmap(img), rect)
      self.update(rect)
    if self._pending:
      self._timer.start(0)
