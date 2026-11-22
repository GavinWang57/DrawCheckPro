"""圖面檢視區：縮放平移、標記工具。"""
from __future__ import annotations

import pymupdf as fitz
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView

from app.document import DrawingDocument
from app.marks.controller import MarkController
from app.marks import text_layout
from app.marks.items import MarkItem
from app.marks.model import (KIND_ELLIPSE, KIND_RECT, KIND_STAMP, KIND_TEXT, STATUS_NG, STATUS_OK,
                             STATUS_NONE, STATUS_PENDING, Mark)
from app.ui import theme
from app.viewer.mark_toolbar import MarkHoverToolbar
from app.viewer.snapshot_overlay import SnapshotOverlay
from app.viewer.tile_renderer import PageItem, TileCache

TOOL_SELECT = "select"
TOOL_PAN = "pan"
TOOL_OK = "stamp_ok"
TOOL_NG = "stamp_ng"
TOOL_PENDING = "stamp_pending"
TOOL_RECT = "rect"
TOOL_ELLIPSE = "ellipse"
TOOL_TEXT = "text"
TOOL_SNAP = "snapshot"
REVIEW_TOOLS = (TOOL_OK, TOOL_NG, TOOL_PENDING, TOOL_RECT, TOOL_ELLIPSE, TOOL_TEXT)
SNAP_MAX_PX = 8000
DUPLICATE_OFFSET_PX = 14
_STAMP_TOOLS = {TOOL_OK: STATUS_OK, TOOL_NG: STATUS_NG, TOOL_PENDING: STATUS_PENDING}

MIN_SCALE, MAX_SCALE = 0.05, 64.0
STAMP_SCREEN_PX = 26
CHECKER_DEFAULT = ""
PX_PER_PT_100 = 96 / 72
HIT_FILL = QColor(255, 214, 0, 70)
HIT_CURRENT = QColor(255, 140, 0, 110)


class PageView(QGraphicsView):
  zoomChanged = Signal(float)
  selectionChangedIds = Signal(list)
  editRequested = Signal(str)
  pageChanged = Signal(int)
  contextMenuRequested = Signal(list, QPoint)  # 選取的標記 id、螢幕座標
  textPlaceRequested = Signal(QPointF)          # 文字工具點擊位置（顯示座標 pt）
  snapshotRequested = Signal(QRectF, str)       # 截圖範圍（顯示座標 pt）、動作 copy / save
  snapshotCancelled = Signal()
  linkActivated = Signal(str)
  toolMenuRequested = Signal(list, QPoint)      # 審查工具中按右鍵：游標下的標記 id、螢幕座標
  escapePressed = Signal()                      # 非選取工具時按 Esc

  def __init__(self, controller: MarkController, parent=None):
    super().__init__(parent)
    self.ctl = controller
    self.doc: DrawingDocument | None = None
    self.pno = 0
    self.cache = TileCache()
    self.page_item: PageItem | None = None
    self.items_by_id: dict[str, MarkItem] = {}
    self.tool = TOOL_SELECT
    self.checker = CHECKER_DEFAULT
    self._pan_from: QPointF | None = None
    self._space = False
    self._draw_start: QPointF | None = None
    self._draw_item: QGraphicsRectItem | None = None
    self._hits: list[tuple[int, fitz.Rect]] = []
    self._hit_items: list[QGraphicsRectItem] = []
    self._current_hit = -1

    self.setScene(QGraphicsScene(self))
    self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
    self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.set_dark(False)
    self.scene().selectionChanged.connect(self._on_selection)

    self.hover_bar = MarkHoverToolbar(self.viewport())
    self.hover_bar.openLink.connect(self.linkActivated)
    self.hover_bar.edit.connect(self.editRequested)
    self.hover_bar.duplicate.connect(self.duplicate_mark)
    self.hover_bar.delete.connect(lambda mid: self.ctl.delete_marks([mid]))
    self.snap_overlay = SnapshotOverlay(self.viewport())
    self.snap_overlay.confirmed.connect(self._on_snap_confirmed)
    self.snap_overlay.cancelled.connect(self.snapshotCancelled)
    self.horizontalScrollBar().valueChanged.connect(self.hover_bar.hide)
    self.verticalScrollBar().valueChanged.connect(self.hover_bar.hide)

    controller.added.connect(self._on_added)
    controller.removed.connect(self._on_removed)
    controller.changed.connect(self._on_changed)
    controller.reset.connect(self._rebuild_marks)

  # ---- 文件與頁面 ----
  def set_document(self, doc: DrawingDocument | None):
    self.doc = doc
    self.cache.clear()
    self.pno = 0
    self._load_page(fit=True)

  def set_page(self, pno: int):
    if not self.doc or not 0 <= pno < self.doc.page_count or pno == self.pno:
      return
    self.pno = pno
    self._load_page(fit=True)

  def _load_page(self, fit: bool):
    self.hover_bar.hide()
    sc = self.scene()
    sc.clear()
    self.items_by_id.clear()
    self._hit_items = []
    self.page_item = None
    if not self.doc:
      return
    self.page_item = PageItem(self.doc, self.pno, self.cache)
    sc.addItem(self.page_item)
    r = self.page_item.boundingRect()
    margin = max(r.width(), r.height()) * 0.05
    sc.setSceneRect(r.adjusted(-margin, -margin, margin, margin))
    self._rebuild_marks()
    self._rebuild_hits()
    self.set_tool(self.tool)
    if fit:
      self.fit_page()
      QTimer.singleShot(0, self.fit_page)
    self.pageChanged.emit(self.pno)

  def refresh_render(self):
    self.cache.clear()
    if self.page_item:
      self.page_item.invalidate()

  def set_dark(self, dark: bool):
    self.setBackgroundBrush(QColor(theme.CANVAS_DARK if dark else theme.CANVAS))

  # ---- 搜尋結果標示 ----
  def set_search_hits(self, hits: list):
    self._hits = list(hits)
    self._current_hit = -1
    self._rebuild_hits()

  def _rebuild_hits(self):
    for it in self._hit_items:
      if it.scene() is self.scene():
        self.scene().removeItem(it)
    self._hit_items = []
    if not self.doc:
      return
    mat = self.doc.rotation_matrix(self.pno)
    for i, (pno, r) in enumerate(self._hits):
      if pno != self.pno:
        continue
      d = (fitz.Rect(r) * mat).normalize()
      item = QGraphicsRectItem(QRectF(d.x0 - 1, d.y0 - 1, d.width + 2, d.height + 2))
      item.setPen(QPen(Qt.PenStyle.NoPen))
      item.setBrush(QBrush(HIT_CURRENT if i == self._current_hit else HIT_FILL))
      item.setZValue(5)
      self.scene().addItem(item)
      self._hit_items.append(item)

  def focus_hit(self, index: int):
    if not self.doc or not 0 <= index < len(self._hits):
      return
    pno, r = self._hits[index]
    self._current_hit = index
    if pno != self.pno:
      self.pno = pno
      self._load_page(fit=False)
    else:
      self._rebuild_hits()
    d = (fitz.Rect(r) * self.doc.rotation_matrix(pno)).normalize()
    vp = self.viewport().rect()
    want = min(vp.width() / max(d.width, 1) / 8, vp.height() / max(d.height, 1) / 8, 8.0)
    if self.current_scale() < want * 0.5:
      self.set_zoom(want)
    self.centerOn(QPointF((d.x0 + d.x1) / 2, (d.y0 + d.y1) / 2))

  # ---- 縮放 ----
  def current_scale(self) -> float:
    return self.transform().m11()

  def zoom_percent(self) -> float:
    return self.current_scale() / PX_PER_PT_100 * 100

  def set_zoom_percent(self, pct: float):
    self.set_zoom(pct / 100 * PX_PER_PT_100)

  def _apply_scale(self, factor: float):
    s = self.current_scale()
    factor = max(MIN_SCALE / s, min(MAX_SCALE / s, factor))
    self.hover_bar.hide()
    self.scale(factor, factor)
    self.zoomChanged.emit(self.current_scale())

  def zoom_by(self, factor: float):
    anchor = self.transformationAnchor()
    self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
    self._apply_scale(factor)
    self.setTransformationAnchor(anchor)

  def set_zoom(self, scale: float):
    self.zoom_by(scale / self.current_scale())

  def fit_page(self):
    if self.page_item:
      self.fitInView(self.page_item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
      self.zoomChanged.emit(self.current_scale())

  def fit_width(self):
    if self.page_item:
      r = self.page_item.boundingRect()
      vw = self.viewport().width() - 20
      self.set_zoom(vw / r.width())
      self.centerOn(r.center().x(), r.top())

  def wheelEvent(self, e):
    if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
      return super().wheelEvent(e)
    delta = e.angleDelta().y()
    if delta:
      self._apply_scale(1.0015 ** delta)
    e.accept()

  # ---- 座標換算 ----
  def mark_display_rect(self, m: Mark) -> QRectF:
    r = (fitz.Rect(m.rect) * self.doc.rotation_matrix(m.page)).normalize()
    return QRectF(r.x0, r.y0, r.width, r.height)

  def display_to_mark_rect(self, r: QRectF) -> list[float]:
    fr = (fitz.Rect(r.left(), r.top(), r.right(), r.bottom())
          * self.doc.derotation_matrix(self.pno)).normalize()
    return [round(v, 3) for v in (fr.x0, fr.y0, fr.x1, fr.y1)]

  # ---- 標記圖層同步 ----
  def _rebuild_marks(self):
    for item in self.items_by_id.values():
      self.scene().removeItem(item)
    self.items_by_id.clear()
    if not self.doc:
      return
    for m in self.ctl.marks_on_page(self.pno):
      self._on_added(m)

  def _on_added(self, m: Mark):
    if not self.doc or m.page != self.pno or m.id in self.items_by_id:
      return
    item = MarkItem(m, self.mark_display_rect(m))
    self.scene().addItem(item)
    self.items_by_id[m.id] = item

  def _on_removed(self, mid: str, page: int):
    if self.hover_bar.mark_id == mid:
      self.hover_bar.hide()
    item = self.items_by_id.pop(mid, None)
    if item:
      self.scene().removeItem(item)

  def _on_changed(self, m: Mark):
    item = self.items_by_id.get(m.id)
    if item:
      item.sync(m, self.mark_display_rect(m))

  def _on_selection(self):
    try:
      ids = [i.mark_id for i in self.scene().selectedItems() if isinstance(i, MarkItem)]
    except RuntimeError:
      return
    self.selectionChangedIds.emit(ids)

  def selected_ids(self) -> list[str]:
    return [i.mark_id for i in self.scene().selectedItems() if isinstance(i, MarkItem)]

  def focus_mark(self, mid: str):
    m = self.ctl.get(mid)
    if not m:
      return
    if m.page != self.pno:
      self.pno = m.page
      self._load_page(fit=False)
    item = self.items_by_id.get(mid)
    if not item:
      return
    self.scene().clearSelection()
    item.setSelected(True)
    r = item.display_rect()
    vp = self.viewport().rect()
    want = min(vp.width() / max(r.width(), 1) / 6, vp.height() / max(r.height(), 1) / 6)
    if self.current_scale() < want * 0.5:
      self.set_zoom(min(want, 8.0))
    self.centerOn(r.center())

  # ---- 工具 ----
  def _idle_cursor(self) -> Qt.CursorShape:
    if self._space or self.tool == TOOL_PAN:
      return Qt.CursorShape.OpenHandCursor
    if self.tool == TOOL_TEXT:
      return Qt.CursorShape.IBeamCursor
    return Qt.CursorShape.ArrowCursor if self.tool == TOOL_SELECT else Qt.CursorShape.CrossCursor

  def set_tool(self, tool: str):
    self.tool = tool
    select = tool == TOOL_SELECT
    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag if select
                     else QGraphicsView.DragMode.NoDrag)
    for item in self.items_by_id.values():
      item.setFlag(item.GraphicsItemFlag.ItemIsMovable, select)
    self.viewport().setCursor(self._idle_cursor())
    if tool == TOOL_SNAP and self.doc:
      self.hover_bar.hide()
      self.snap_overlay.start()
    elif tool != TOOL_SNAP:
      self.snap_overlay.hide()

  def _on_page(self, p: QPointF) -> bool:
    return bool(self.page_item) and self.page_item.boundingRect().contains(p)

  def _create_mark(self, kind: str, status: str, display_rect: QRectF):
    m = Mark(page=self.pno, kind=kind, rect=self.display_to_mark_rect(display_rect),
             status=status, checker=self.checker)
    self.ctl.add_mark(m)
    item = self.items_by_id.get(m.id)
    if item:
      self.scene().clearSelection()
      item.setSelected(True)

  # ---- 滑鼠 / 鍵盤 ----
  def _start_pan(self, pos):
    self._pan_from = QPointF(pos)
    self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

  def mousePressEvent(self, e):
    if e.button() == Qt.MouseButton.MiddleButton or (
        (self._space or self.tool == TOOL_PAN) and e.button() == Qt.MouseButton.LeftButton):
      self._start_pan(e.position())
      e.accept()
      return
    if (e.button() == Qt.MouseButton.LeftButton
        and e.modifiers() & Qt.KeyboardModifier.ControlModifier):
      item = self._mark_at(e.position().toPoint())
      m = self.ctl.get(item.mark_id) if item else None
      if m and m.link:
        self.linkActivated.emit(m.link)
        e.accept()
        return
    if (e.button() == Qt.MouseButton.LeftButton and self.tool not in (TOOL_SELECT, TOOL_PAN)
        and self.doc):
      p = self.mapToScene(e.position().toPoint())
      if not self._on_page(p):
        return
      if self.tool == TOOL_TEXT:
        self.textPlaceRequested.emit(p)
      elif self.tool in _STAMP_TOOLS:
        size = STAMP_SCREEN_PX / self.current_scale()
        self._create_mark(KIND_STAMP, _STAMP_TOOLS[self.tool],
                          QRectF(p.x() - size / 2, p.y() - size / 2, size, size))
      else:
        self._draw_start = p
        self._draw_item = QGraphicsRectItem(QRectF(p, p))
        pen = QPen(QColor("#2f7df6"), 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self._draw_item.setPen(pen)
        self._draw_item.setZValue(100)
        self.scene().addItem(self._draw_item)
      e.accept()
      return
    super().mousePressEvent(e)

  def mouseMoveEvent(self, e):
    if self._pan_from is not None:
      d = e.position() - self._pan_from
      self._pan_from = QPointF(e.position())
      self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
      self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
      e.accept()
      return
    if self._draw_item is not None:
      p = self.mapToScene(e.position().toPoint())
      self._draw_item.setRect(QRectF(self._draw_start, p).normalized())
      e.accept()
      return
    super().mouseMoveEvent(e)
    self._update_hover(e)

  # ---- 文字框浮動工具列 ----
  def _update_hover(self, e):
    if e.buttons() != Qt.MouseButton.NoButton:
      self.hover_bar.hide()
      return
    item = self._mark_at(e.position().toPoint())
    m = self.ctl.get(item.mark_id) if item else None
    if m is None or m.kind != KIND_TEXT:
      self.hover_bar.schedule_hide()
      return
    if self.hover_bar.isVisible() and self.hover_bar.mark_id == m.id:
      self.hover_bar.cancel_hide()
      return
    r = item.display_rect()
    anchor = self.mapFromScene(QPointF(r.right(), r.top()))
    self.hover_bar.show_for(m.id, m.link, anchor)

  def leaveEvent(self, e):
    self.hover_bar.schedule_hide()
    super().leaveEvent(e)

  def duplicate_mark(self, mid: str):
    m = self.ctl.get(mid)
    if not m:
      return
    if m.page != self.pno:
      self.pno = m.page
      self._load_page(fit=False)
    r = self.mark_display_rect(m)
    off = DUPLICATE_OFFSET_PX / self.current_scale()
    page = self.page_item.boundingRect()
    x = min(r.left() + off, max(page.left(), page.right() - r.width()))
    y = min(r.top() + off, max(page.top(), page.bottom() - r.height()))
    new = Mark(page=m.page, kind=m.kind, rect=self.display_to_mark_rect(
                 QRectF(x, y, r.width(), r.height())),
               status=m.status, note=m.note, measured=m.measured, checker=m.checker,
               text=m.text, link=m.link, style=dict(m.style))
    self.ctl.add_mark(new)
    item = self.items_by_id.get(new.id)
    if item:
      self.scene().clearSelection()
      item.setSelected(True)

  def mouseReleaseEvent(self, e):
    if self._pan_from is not None and e.button() in (Qt.MouseButton.MiddleButton,
                                                      Qt.MouseButton.LeftButton):
      self._pan_from = None
      self.viewport().setCursor(self._idle_cursor())
      e.accept()
      return
    if self._draw_item is not None:
      r = self._draw_item.rect().intersected(self.page_item.boundingRect())
      self.scene().removeItem(self._draw_item)
      self._draw_item = None
      min_pt = 4 / self.current_scale()
      if r.width() >= min_pt and r.height() >= min_pt:
        kind = KIND_ELLIPSE if self.tool == TOOL_ELLIPSE else KIND_RECT
        self._create_mark(kind, STATUS_NONE, r)
      e.accept()
      return
    super().mouseReleaseEvent(e)
    if self.tool == TOOL_SELECT:
      self._commit_moves()

  # ---- 文字標記 ----
  def default_text_font_pt(self) -> float:
    """新文字框的預設字級：在目前縮放下約 14 螢幕像素。"""
    return round(min(max(14 / self.current_scale(), 2.0), 72.0), 1)

  def create_text_mark(self, pos: QPointF, values: dict):
    w, h = text_layout.measure(values["text"], values["style"])
    page = self.page_item.boundingRect()
    x = min(max(pos.x(), page.left()), max(page.left(), page.right() - w))
    y = min(max(pos.y(), page.top()), max(page.top(), page.bottom() - h))
    m = Mark(page=self.pno, kind=KIND_TEXT, rect=self.display_to_mark_rect(QRectF(x, y, w, h)),
             status=values.get("status", STATUS_NONE),
             checker=values.get("checker") or self.checker,
             text=values["text"], link=values.get("link", ""), style=values["style"])
    self.ctl.add_mark(m)
    item = self.items_by_id.get(m.id)
    if item:
      self.scene().clearSelection()
      item.setSelected(True)

  def resized_text_rect(self, m: Mark, text: str, style: dict) -> list[float]:
    """文字或字級變更後，以原本的左上角（顯示座標）重新計算框的大小。"""
    old = self.mark_display_rect(m)
    w, h = text_layout.measure(text, style)
    return self.display_to_mark_rect(QRectF(old.left(), old.top(), w, h))

  # ---- 截圖 ----
  def resizeEvent(self, e):
    super().resizeEvent(e)
    self.snap_overlay.sync_geometry()

  def _on_snap_confirmed(self, frame, action: str):
    """選取框（viewport 像素）→ 顯示座標 pt，並限制在頁面範圍內。"""
    r = self.mapToScene(frame).boundingRect()
    if self.page_item:
      r = r.intersected(self.page_item.boundingRect())
    if r.isEmpty():
      self.snapshotCancelled.emit()
      return
    self.snapshotRequested.emit(r, action)

  def render_snapshot(self, rect: QRectF) -> QImage:
    """以至少 2 倍螢幕解析度重新渲染指定範圍（含增強、深色模式與標記）。"""
    if not self.doc or rect.isEmpty():
      return QImage()
    zoom = max(self.current_scale() * self.devicePixelRatioF(), 2.0)
    zoom = min(zoom, SNAP_MAX_PX / max(rect.width(), rect.height()))
    arr, ir = self.doc.render(self.pno, zoom, fitz.Rect(rect.left(), rect.top(),
                                                        rect.right(), rect.bottom()))
    img = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0],
                 QImage.Format.Format_RGB888).copy()
    source = QRectF(ir.x0 / zoom, ir.y0 / zoom, ir.width / zoom, ir.height / zoom)
    selected = self.scene().selectedItems()
    self.scene().clearSelection()
    hidden = [self.page_item, *self._hit_items]
    for it in hidden:
      it.setVisible(False)
    painter = QPainter(img)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    self.scene().render(painter, QRectF(0, 0, img.width(), img.height()), source)
    painter.end()
    for it in hidden:
      it.setVisible(True)
    for it in selected:
      it.setSelected(True)
    return img

  def _commit_moves(self):
    moved = []
    for mid, item in self.items_by_id.items():
      m = self.ctl.get(mid)
      new_rect = self.display_to_mark_rect(item.display_rect())
      if m and any(abs(a - b) > 1e-3 for a, b in zip(new_rect, m.rect)):
        moved.append((mid, new_rect))
    if not moved:
      return
    stack = self.ctl.undo_stack
    stack.beginMacro("移動標記")
    for mid, rect in moved:
      self.ctl.update_marks([mid], rect=rect)
    stack.endMacro()

  def _mark_at(self, pos) -> MarkItem | None:
    item = self.itemAt(pos)
    while item is not None and not isinstance(item, MarkItem):
      item = item.parentItem()
    return item

  def mouseDoubleClickEvent(self, e):
    item = self._mark_at(e.position().toPoint())
    if item is not None:
      self.editRequested.emit(item.mark_id)
      e.accept()
      return
    super().mouseDoubleClickEvent(e)

  def contextMenuEvent(self, e):
    item = self._mark_at(e.pos())
    if self.tool in REVIEW_TOOLS:
      if item is not None:
        self.scene().clearSelection()
        item.setSelected(True)
      self.toolMenuRequested.emit([item.mark_id] if item else [], e.globalPos())
      e.accept()
      return
    if item is None:
      return
    if not item.isSelected():
      self.scene().clearSelection()
      item.setSelected(True)
    self.contextMenuRequested.emit(self.selected_ids(), e.globalPos())
    e.accept()

  def keyPressEvent(self, e):
    if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
      self._space = True
      self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
      e.accept()
      return
    if e.key() == Qt.Key.Key_Escape:
      if self._draw_item is not None:
        self.scene().removeItem(self._draw_item)
        self._draw_item = None
        return
      if self.tool != TOOL_SELECT:
        self.escapePressed.emit()
        return
    super().keyPressEvent(e)

  def keyReleaseEvent(self, e):
    if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
      self._space = False
      self.set_tool(self.tool)
      e.accept()
      return
    super().keyReleaseEvent(e)
