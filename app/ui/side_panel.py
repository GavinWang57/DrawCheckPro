"""可收合到視窗邊緣的側欄：展開時顯示內容，收合時只剩一條帶圖示的窄邊條。"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from app.ui import icons

STRIP_W = 44
MIN_EXPANDED_W = 230


def collapse_button(side: str) -> QToolButton:
  """放在面板標題列角落的收合按鈕。左側面板往左收（«），右側往右收（»）。"""
  b = QToolButton()
  b.setObjectName("CollapseBtn")
  b.setIcon(icons.icon("collapse_left" if side == "left" else "collapse_right", "#8fa6c4"))
  b.setIconSize(QSize(16, 16))
  b.setToolTip("收合面板")
  b.setAutoRaise(True)
  return b


class CollapsibleSide(QStackedWidget):
  collapsedChanged = Signal(bool)

  def __init__(self, side: str, content: QWidget, parent=None):
    super().__init__(parent)
    self.side = side
    self.content = content
    self.strip = QFrame()
    self.strip.setObjectName("SideStrip")
    self._strip_lay = QVBoxLayout(self.strip)
    self._strip_lay.setContentsMargins(4, 8, 4, 8)
    self._strip_lay.setSpacing(6)
    self._strip_lay.addStretch(1)
    expand = self._strip_button("collapse_right" if side == "left" else "collapse_left", "展開面板")
    expand.clicked.connect(self.expand)
    self._strip_lay.addWidget(expand)
    self.addWidget(content)
    self.addWidget(self.strip)
    self._collapsed = False

  def _strip_button(self, icon_name: str, tip: str) -> QToolButton:
    b = QToolButton()
    b.setObjectName("StripBtn")
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    return b

  def add_section(self, icon_name: str, tip: str, on_open: Callable[[], None]):
    """邊條上的圖示：點一下展開面板並切到該區塊。"""
    b = self._strip_button(icon_name, tip)
    b.clicked.connect(lambda: (self.expand(), on_open()))
    self._strip_lay.insertWidget(self._strip_lay.count() - 2, b)

  @property
  def collapsed(self) -> bool:
    return self._collapsed

  def set_collapsed(self, on: bool):
    if on == self._collapsed:
      return
    self._collapsed = on
    self.setCurrentWidget(self.strip if on else self.content)
    if on:
      self.setMinimumWidth(STRIP_W)
      self.setMaximumWidth(STRIP_W)
    else:
      self.setMinimumWidth(MIN_EXPANDED_W)
      self.setMaximumWidth(16777215)
    self.collapsedChanged.emit(on)

  def collapse(self):
    self.set_collapsed(True)

  def expand(self):
    self.set_collapsed(False)
