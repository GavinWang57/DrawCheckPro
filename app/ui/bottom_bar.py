"""底部列：訊息、換頁、檢視模式、縮放滑桿與百分比。"""
from __future__ import annotations

import math

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QSlider, QSpinBox, QToolButton,
                               QWidget)

from app.ui import icons

PCT_MIN, PCT_MAX = 5, 4800
_SLIDER_STEPS = 1000


def _pct_to_slider(p: float) -> int:
  p = min(max(p, PCT_MIN), PCT_MAX)
  return round(math.log(p / PCT_MIN) / math.log(PCT_MAX / PCT_MIN) * _SLIDER_STEPS)


def _slider_to_pct(v: int) -> float:
  return PCT_MIN * (PCT_MAX / PCT_MIN) ** (v / _SLIDER_STEPS)


def _btn(icon_name: str, tip: str) -> QToolButton:
  b = QToolButton()
  b.setIcon(icons.icon(icon_name))
  b.setIconSize(QSize(18, 18))
  b.setToolTip(tip)
  b.setAutoRaise(True)
  return b


class BottomBar(QWidget):
  pageRequested = Signal(int)  # 0-based
  zoomPercentRequested = Signal(float)
  zoomStep = Signal(float)
  fitPage = Signal()
  fitWidth = Signal()

  def __init__(self, parent=None):
    super().__init__(parent)
    self.setObjectName("BottomBar")
    self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    self._sync = False

    self.message = QLabel()
    self.message.setObjectName("Muted")
    self._msg_timer = QTimer(self)
    self._msg_timer.setSingleShot(True)
    self._msg_timer.timeout.connect(self.message.clear)

    self.prev = _btn("prev", "上一頁（PgUp）")
    self.next = _btn("next", "下一頁（PgDn）")
    self._current = 0
    self.page = QLineEdit("1")
    self.page.setValidator(QIntValidator(1, 1, self))
    self.page.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.page.setFixedWidth(52)
    self.total = QLabel("/ 0")

    self.fit_page_btn = _btn("fit_page", "適合頁面（F）")
    self.fit_width_btn = _btn("fit_width", "適合頁寬（W）")
    self.zoom_out = _btn("zoom_out", "縮小")
    self.zoom_in = _btn("zoom_in", "放大")
    self.slider = QSlider(Qt.Orientation.Horizontal)
    self.slider.setRange(0, _SLIDER_STEPS)
    self.slider.setFixedWidth(150)
    self.pct = QSpinBox()
    self.pct.setRange(PCT_MIN, PCT_MAX)
    self.pct.setSuffix("%")
    self.pct.setFixedWidth(84)
    self.pct.setKeyboardTracking(False)

    lay = QHBoxLayout(self)
    lay.setContentsMargins(10, 3, 10, 3)
    lay.setSpacing(6)
    lay.addWidget(self.message, 1)
    for w in (self.prev, self.page, self.total, self.next):
      lay.addWidget(w)
    lay.addSpacing(28)
    for w in (self.fit_page_btn, self.fit_width_btn):
      lay.addWidget(w)
    lay.addSpacing(28)
    for w in (self.zoom_out, self.slider, self.zoom_in, self.pct):
      lay.addWidget(w)
    lay.addStretch(1)

    self.prev.clicked.connect(lambda: self.pageRequested.emit(self._current - 1))
    self.next.clicked.connect(lambda: self.pageRequested.emit(self._current + 1))
    self.page.editingFinished.connect(self._page_entered)
    self.fit_page_btn.clicked.connect(self.fitPage)
    self.fit_width_btn.clicked.connect(self.fitWidth)
    self.zoom_out.clicked.connect(lambda: self.zoomStep.emit(0.8))
    self.zoom_in.clicked.connect(lambda: self.zoomStep.emit(1.25))
    self.slider.valueChanged.connect(
      lambda v: not self._sync and self.zoomPercentRequested.emit(_slider_to_pct(v)))
    self.pct.valueChanged.connect(lambda v: not self._sync and self.zoomPercentRequested.emit(float(v)))

  def _page_entered(self):
    text = self.page.text()
    if text.isdigit() and int(text) - 1 != self._current:
      self.pageRequested.emit(int(text) - 1)
    else:
      self.page.setText(str(self._current + 1))

  def set_pages(self, current: int, total: int):
    self._sync = True
    self._current = current
    self.page.validator().setTop(max(total, 1))
    self.page.setText(str(current + 1))
    self.total.setText(f"/ {total}")
    self.prev.setEnabled(current > 0)
    self.next.setEnabled(current < total - 1)
    self._sync = False

  def set_zoom_percent(self, pct: float):
    self._sync = True
    self.slider.setValue(_pct_to_slider(pct))
    self.pct.setValue(round(pct))
    self._sync = False

  def show_message(self, text: str, ms: int = 4000):
    self.message.setText(text)
    self._msg_timer.start(ms) if ms > 0 else self._msg_timer.stop()
