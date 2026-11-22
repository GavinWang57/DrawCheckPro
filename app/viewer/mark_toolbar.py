"""滑鼠停在文字框上時出現的浮動工具列：開啟連結、編輯、複製、刪除。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from app.ui import icons

HIDE_DELAY_MS = 350


class MarkHoverToolbar(QFrame):
  openLink = Signal(str)
  edit = Signal(str)
  duplicate = Signal(str)
  delete = Signal(str)

  def __init__(self, parent: QWidget):
    super().__init__(parent)
    self.setObjectName("HoverToolbar")
    self.mark_id = ""
    self._link = ""
    lay = QHBoxLayout(self)
    lay.setContentsMargins(3, 3, 3, 3)
    lay.setSpacing(2)
    self.btn_link = self._button("link", "開啟連結", lambda: self.openLink.emit(self._link))
    self.btn_edit = self._button("text", "編輯文字與格式", lambda: self.edit.emit(self.mark_id))
    self.btn_copy = self._button("copy", "複製一份文字框", lambda: self.duplicate.emit(self.mark_id))
    self.btn_delete = self._button("delete", "刪除", lambda: self.delete.emit(self.mark_id))
    for b in (self.btn_link, self.btn_edit, self.btn_copy, self.btn_delete):
      lay.addWidget(b)
    self._hide_timer = QTimer(self)
    self._hide_timer.setSingleShot(True)
    self._hide_timer.setInterval(HIDE_DELAY_MS)
    self._hide_timer.timeout.connect(self._maybe_hide)
    self.hide()

  def _button(self, icon_name: str, tip: str, slot) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda: (self.hide(), slot()))
    return b

  def show_for(self, mark_id: str, link: str, anchor: QPoint):
    """anchor：文字框右上角（viewport 座標）。工具列放在框的上方、靠右對齊。"""
    self._hide_timer.stop()
    self.mark_id, self._link = mark_id, link
    self.btn_link.setVisible(bool(link))
    self.adjustSize()
    vp = self.parentWidget().rect()
    x = min(max(anchor.x() - self.width(), 2), vp.width() - self.width() - 2)
    y = anchor.y() - self.height() - 4
    if y < 2:
      y = anchor.y() + 4
    self.move(x, y)
    self.show()
    self.raise_()

  def schedule_hide(self):
    if self.isVisible() and not self._hide_timer.isActive():
      self._hide_timer.start()

  def cancel_hide(self):
    self._hide_timer.stop()

  def _maybe_hide(self):
    if not self.underMouse():
      self.hide()

  def enterEvent(self, e):
    self.cancel_hide()
    super().enterEvent(e)

  def leaveEvent(self, e):
    self.schedule_hide()
    super().leaveEvent(e)
