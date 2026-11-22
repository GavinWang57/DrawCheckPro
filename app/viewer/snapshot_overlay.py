"""截圖選取框：先出現預設框線，使用者可移動 / 調整大小 / 重新框選，再選擇複製或另存。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.ui import icons

HANDLE = 8
MIN_SIZE = 12
ACCENT = QColor("#00c853")
ACTION_COPY = "copy"
ACTION_SAVE = "save"

# 控制點：(x 位置 0/0.5/1, y 位置 0/0.5/1)
_HANDLES = {
  "tl": (0, 0), "t": (0.5, 0), "tr": (1, 0), "r": (1, 0.5),
  "br": (1, 1), "b": (0.5, 1), "bl": (0, 1), "l": (0, 0.5),
}
_CURSORS = {
  "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
  "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
  "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
  "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
}


class SnapshotOverlay(QWidget):
  confirmed = Signal(QRect, str)  # viewport 座標的範圍、動作（copy / save）
  cancelled = Signal()

  def __init__(self, parent: QWidget):
    super().__init__(parent)
    self.setMouseTracking(True)
    self.frame = QRect()
    self._drag_mode = ""   # "new" / "move" / 控制點名稱
    self._drag_from = QPoint()
    self._frame_from = QRect()

    self.bar = QFrame(self)
    self.bar.setObjectName("HoverToolbar")
    lay = QHBoxLayout(self.bar)
    lay.setContentsMargins(6, 4, 6, 4)
    lay.setSpacing(6)
    self.size_label = QLabel()
    self.size_label.setObjectName("Muted")
    copy = QPushButton(icons.icon("copy"), "複製到剪貼簿")
    save = QPushButton(icons.icon("save"), "另存 PNG")
    cancel = QPushButton("取消")
    for b in (copy, save, cancel):
      b.setIconSize(QSize(16, 16))
      b.setCursor(Qt.CursorShape.PointingHandCursor)
    lay.addWidget(self.size_label)
    lay.addWidget(copy)
    lay.addWidget(save)
    lay.addWidget(cancel)
    copy.clicked.connect(lambda: self._confirm(ACTION_COPY))
    save.clicked.connect(lambda: self._confirm(ACTION_SAVE))
    cancel.clicked.connect(self.cancel)
    self.hide()

  # ---- 開啟 / 關閉 ----
  def start(self):
    vp = self.parentWidget().rect()
    self.setGeometry(vp)
    w, h = int(vp.width() * 0.5), int(vp.height() * 0.5)
    self.frame = QRect((vp.width() - w) // 2, (vp.height() - h) // 2, w, h)
    self.show()
    self.raise_()
    self.setFocus()
    self._layout_bar()

  def cancel(self):
    self.hide()
    self.cancelled.emit()

  def _confirm(self, action: str):
    rect = QRect(self.frame)
    self.hide()
    self.confirmed.emit(rect, action)

  def sync_geometry(self):
    if self.isVisible():
      self.setGeometry(self.parentWidget().rect())
      self.frame = self.frame.intersected(self.rect())
      self._layout_bar()

  # ---- 外觀 ----
  def _layout_bar(self):
    self.size_label.setText(f"{self.frame.width()}×{self.frame.height()}")
    self.bar.adjustSize()
    x = min(max(self.frame.right() - self.bar.width(), 4), self.width() - self.bar.width() - 4)
    y = self.frame.bottom() + 8
    if y + self.bar.height() > self.height() - 4:
      y = self.frame.top() - self.bar.height() - 8
    if y < 4:
      y = self.frame.bottom() - self.bar.height() - 8
    self.bar.move(x, y)
    self.bar.setVisible(self.frame.width() >= MIN_SIZE and self.frame.height() >= MIN_SIZE)
    self.update()

  def _handle_rects(self) -> dict[str, QRect]:
    f = self.frame
    out = {}
    for name, (fx, fy) in _HANDLES.items():
      cx = f.left() + round(f.width() * fx)
      cy = f.top() + round(f.height() * fy)
      out[name] = QRect(cx - HANDLE // 2, cy - HANDLE // 2, HANDLE, HANDLE)
    return out

  def paintEvent(self, _):
    p = QPainter(self)
    outside = QPainterPath()
    outside.addRect(self.rect())
    inner = QPainterPath()
    inner.addRect(self.frame)
    p.fillPath(outside.subtracted(inner), QColor(0, 0, 0, 110))
    if self.frame.isEmpty():
      return
    p.setPen(QPen(ACCENT, 2, Qt.PenStyle.DashLine))
    p.drawRect(self.frame)
    p.setPen(QPen(QColor("white"), 1))
    p.setBrush(ACCENT)
    for r in self._handle_rects().values():
      p.drawRect(r)

  # ---- 滑鼠 ----
  def _hit(self, pos: QPoint) -> str:
    for name, r in self._handle_rects().items():
      if r.adjusted(-3, -3, 3, 3).contains(pos):
        return name
    if self.frame.contains(pos):
      return "move"
    return "new"

  def mousePressEvent(self, e):
    if e.button() != Qt.MouseButton.LeftButton:
      e.ignore()  # 中鍵等交給圖面（平移）
      return
    pos = e.position().toPoint()
    self._drag_mode = self._hit(pos)
    self._drag_from = pos
    self._frame_from = QRect(self.frame)
    if self._drag_mode == "new":
      self.frame = QRect(pos, QSize(0, 0))
    self.bar.hide()

  def mouseMoveEvent(self, e):
    pos = e.position().toPoint()
    if not self._drag_mode:
      mode = self._hit(pos)
      self.setCursor(_CURSORS.get(mode, Qt.CursorShape.SizeAllCursor if mode == "move"
                                  else Qt.CursorShape.CrossCursor))
      return
    d = pos - self._drag_from
    f = QRect(self._frame_from)
    if self._drag_mode == "new":
      f = QRect(self._drag_from, pos).normalized()
    elif self._drag_mode == "move":
      f.translate(d)
      f.moveLeft(min(max(f.left(), 0), self.width() - f.width()))
      f.moveTop(min(max(f.top(), 0), self.height() - f.height()))
    else:
      if "l" in self._drag_mode:
        f.setLeft(f.left() + d.x())
      if "r" in self._drag_mode:
        f.setRight(f.right() + d.x())
      if "t" in self._drag_mode:
        f.setTop(f.top() + d.y())
      if "b" in self._drag_mode:
        f.setBottom(f.bottom() + d.y())
      f = f.normalized()
    self.frame = f.intersected(self.rect())
    self.update()

  def mouseReleaseEvent(self, e):
    if e.button() != Qt.MouseButton.LeftButton:
      e.ignore()
      return
    self._drag_mode = ""
    if self.frame.width() < MIN_SIZE or self.frame.height() < MIN_SIZE:
      self.frame = QRect(self._frame_from) if not self._frame_from.isEmpty() else self.frame
    self._layout_bar()

  def mouseDoubleClickEvent(self, e):
    if self.frame.contains(e.position().toPoint()):
      self._confirm(ACTION_COPY)

  def wheelEvent(self, e):
    e.ignore()  # 讓圖面照常縮放；框線維持在螢幕上的位置

  def keyPressEvent(self, e):
    if e.key() == Qt.Key.Key_Escape:
      self.cancel()
    elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
      self._confirm(ACTION_COPY)
    else:
      super().keyPressEvent(e)
