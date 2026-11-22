"""上方工具列：先選分類標籤（檔案／檢視／工具／審查／設定），再顯示該分類的圖示按鈕。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QMenu, QStackedWidget, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

ICON_PX = 28


class RibbonPage(QFrame):
  def __init__(self, parent=None):
    super().__init__(parent)
    self.setObjectName("RibbonGroup")
    self._row = QHBoxLayout(self)
    self._row.setContentsMargins(8, 4, 8, 4)
    self._row.setSpacing(2)
    self._row.addStretch(1)

  def add(self, action: QAction, menu: QMenu | None = None) -> QToolButton:
    b = QToolButton()
    b.setDefaultAction(action)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    b.setIconSize(QSize(ICON_PX, ICON_PX))
    b.setAutoRaise(True)
    if menu is not None:
      b.setMenu(menu)
      b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    self._row.insertWidget(self._row.count() - 1, b)
    return b

  def add_separator(self):
    line = QFrame()
    line.setObjectName("RibbonSep")
    line.setFixedWidth(1)
    self._row.insertWidget(self._row.count() - 1, line)


class Ribbon(QWidget):
  currentChanged = Signal(int)

  def __init__(self, parent=None):
    super().__init__(parent)
    self.setObjectName("Ribbon")
    self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    self.tabs = QTabBar()
    self.tabs.setObjectName("RibbonTabs")
    self.tabs.setExpanding(False)
    self.tabs.setDrawBase(False)
    self.stack = QStackedWidget()
    lay = QVBoxLayout(self)
    lay.setContentsMargins(8, 4, 8, 6)
    lay.setSpacing(4)
    lay.addWidget(self.tabs)
    lay.addWidget(self.stack)
    self.tabs.currentChanged.connect(self.stack.setCurrentIndex)
    self.tabs.currentChanged.connect(self.currentChanged)

  def page(self, title: str) -> RibbonPage:
    p = RibbonPage()
    self.stack.addWidget(p)
    self.tabs.addTab(title)
    return p

  def set_current(self, index: int):
    if 0 <= index < self.tabs.count():
      self.tabs.setCurrentIndex(index)
