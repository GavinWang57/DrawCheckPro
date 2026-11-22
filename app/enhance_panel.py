"""左側「影像增強」面板（可收合）。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QGridLayout, QLabel, QPushButton,
                               QRadioButton, QSlider, QToolButton, QVBoxLayout, QWidget)

from app.document import MODE_OFF, MODE_RASTER, MODE_VECTOR, ViewSettings
from app.enhance.vector_enhance import VectorParams
from app.ui import icons

_MODES = ((MODE_VECTOR, "向量加粗（建議）"), (MODE_RASTER, "點陣加粗"), (MODE_OFF, "原始"))


class _Slider:
  def __init__(self, grid: QGridLayout, row: int, label: QWidget, lo: float, hi: float,
               step: float, fmt: str, tip: str):
    self.step, self.fmt = step, fmt
    self.label = label
    label.setToolTip(tip)
    self.slider = QSlider(Qt.Orientation.Horizontal)
    self.slider.setRange(round(lo / step), round(hi / step))
    self.slider.setToolTip(tip)
    self.value_label = QLabel()
    self.value_label.setMinimumWidth(52)
    self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(label, row, 0)
    grid.addWidget(self.slider, row, 1)
    grid.addWidget(self.value_label, row, 2)
    self.slider.valueChanged.connect(self._show)

  def _show(self, _=None):
    self.value_label.setText(self.fmt.format(self.value()))

  def value(self) -> float:
    return round(self.slider.value() * self.step, 4)

  def set_value(self, v: float):
    self.slider.setValue(round(v / self.step))
    self._show()

  def set_enabled(self, on: bool, label_too: bool = True):
    self.slider.setEnabled(on)
    self.value_label.setEnabled(on)
    if label_too:
      self.label.setEnabled(on)


def _box() -> tuple[QFrame, QGridLayout]:
  f = QFrame()
  f.setObjectName("SubBox")
  g = QGridLayout(f)
  g.setContentsMargins(10, 8, 10, 8)
  g.setVerticalSpacing(7)
  g.setColumnStretch(1, 1)
  return f, g


def _title(text: str) -> QLabel:
  t = QLabel(text)
  t.setObjectName("SectionTitle")
  return t


class EnhancePanel(QWidget):
  settingsChanged = Signal(object)  # ViewSettings

  def __init__(self, settings: ViewSettings, parent=None):
    super().__init__(parent)
    self._loading = False
    self._debounce = QTimer(self)
    self._debounce.setSingleShot(True)
    self._debounce.setInterval(250)
    self._debounce.timeout.connect(lambda: self.settingsChanged.emit(self.settings()))

    self.header = QToolButton()
    self.header.setObjectName("SectionHeader")
    self.header.setText("  影像增強")
    self.header.setIcon(icons.icon("enhance"))
    self.header.setIconSize(QSize(16, 16))
    self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    self.header.setCheckable(True)
    self.header.setChecked(True)
    self.chevron = QLabel()
    head_row = QGridLayout()
    head_row.addWidget(self.header, 0, 0)
    head_row.addWidget(self.chevron, 0, 1, Qt.AlignmentFlag.AlignRight)

    mode_box, mg = _box()
    self.mode_group = QButtonGroup(self)
    self.mode_buttons: dict[str, QRadioButton] = {}
    for i, (key, text) in enumerate(_MODES):
      rb = QRadioButton(text)
      self.mode_group.addButton(rb)
      self.mode_buttons[key] = rb
      mg.addWidget(rb, i, 0, 1, 3)

    vec_box, vg = _box()
    self.line_mult = _Slider(vg, 0, QLabel("線寬倍率"), 1.0, 4.0, 0.1, "x{:.1f}",
                             "所有線條寬度乘上此倍率")
    self.min_line_pt = _Slider(vg, 1, QLabel("最小線寬"), 0.0, 1.0, 0.05, "{:.2f}pt",
                               "比這個細的線（包含 0 寬度的 hairline）一律加粗到此寬度")
    self.text_pt = _Slider(vg, 2, QLabel("文字加粗"), 0.0, 0.5, 0.01, "{:.2f}pt",
                           "替文字加上同色描邊")
    self.fill_pt = _Slider(vg, 3, QLabel("填色加粗"), 0.0, 0.3, 0.01, "{:.2f}pt",
                           "替填色圖形加描邊，適用於 CAD 轉成外框的文字與箭頭")

    disp_box, dg = _box()
    self.min_px_on = QCheckBox("最細線像素")
    self.min_px = _Slider(dg, 0, self.min_px_on, 0.25, 3.0, 0.25, "{:.2f}px",
                          "不論縮放比例，線條至少顯示這麼多像素寬")
    self.raster_on = QCheckBox("點陣擴張")
    self.radius = _Slider(dg, 1, self.raster_on, 1, 3, 1, "{:.0f}px",
                          "點陣加粗模式的擴張像素（向量解析失敗的頁面也會使用）")
    self.gamma_on = QCheckBox("加深")
    self.gamma = _Slider(dg, 2, self.gamma_on, 1.1, 3.0, 0.1, "{:.1f}", "讓淺灰色的細線變深")
    self.dark = QCheckBox("深色模式")
    self.dark.setToolTip("黑白反轉、保留顏色（D）")
    dg.addWidget(self.dark, 3, 0, 1, 3)

    reset = QPushButton("恢復預設值")
    reset.clicked.connect(lambda: self.load(ViewSettings(dark=self.dark.isChecked()), emit=True))

    self.body = QWidget()
    bl = QVBoxLayout(self.body)
    bl.setContentsMargins(0, 0, 0, 0)
    bl.setSpacing(5)
    for w in (_title("增強模式"), mode_box, _title("向量參數"), vec_box, _title("顯示"), disp_box):
      bl.addWidget(w)
    bl.addSpacing(6)
    bl.addWidget(reset)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(10, 4, 10, 10)
    lay.addLayout(head_row)
    lay.addWidget(self.body)

    self.header.toggled.connect(self._set_expanded)
    self._set_expanded(True)
    self._vector_sliders = (self.line_mult, self.min_line_pt, self.text_pt, self.fill_pt)
    for s in (*self._vector_sliders, self.min_px, self.radius, self.gamma):
      s.slider.valueChanged.connect(self._changed)
    for cb in (self.min_px_on, self.raster_on, self.gamma_on):
      cb.toggled.connect(self._changed)
    self.mode_group.buttonToggled.connect(self._changed)
    self.dark.toggled.connect(self._changed_now)
    self.load(settings)

  def _set_expanded(self, on: bool):
    self.body.setVisible(on)
    self.chevron.setPixmap(icons.icon("chevron_up" if on else "chevron_down", "#8fa6c4")
                           .pixmap(QSize(16, 16)))

  def load(self, s: ViewSettings, emit: bool = False):
    self._loading = True
    self.mode_buttons.get(s.mode, self.mode_buttons[MODE_VECTOR]).setChecked(True)
    self.line_mult.set_value(s.vector.line_mult)
    self.min_line_pt.set_value(s.vector.min_line_pt)
    self.text_pt.set_value(s.vector.text_stroke_pt)
    self.fill_pt.set_value(s.vector.fill_stroke_pt)
    self.min_px.set_value(s.min_line_px)
    self.radius.set_value(s.raster_radius)
    self.gamma.set_value(s.gamma)
    self.min_px_on.setChecked(s.min_px_on)
    self.raster_on.setChecked(s.raster_on)
    self.gamma_on.setChecked(s.gamma_on)
    self.dark.setChecked(s.dark)
    self._loading = False
    self._update_enabled()
    if emit:
      self.settingsChanged.emit(self.settings())

  def settings(self) -> ViewSettings:
    mode = next(k for k, b in self.mode_buttons.items() if b.isChecked())
    return ViewSettings(
      mode=mode,
      vector=VectorParams(line_mult=self.line_mult.value(), min_line_pt=self.min_line_pt.value(),
                          text_stroke_pt=self.text_pt.value(),
                          fill_stroke_pt=self.fill_pt.value()),
      min_line_px=self.min_px.value(),
      raster_radius=int(self.radius.value()),
      gamma=self.gamma.value(),
      dark=self.dark.isChecked(),
      min_px_on=self.min_px_on.isChecked(),
      raster_on=self.raster_on.isChecked(),
      gamma_on=self.gamma_on.isChecked(),
    )

  def toggle_dark(self):
    self.dark.setChecked(not self.dark.isChecked())

  def _update_enabled(self):
    mode = self.settings().mode
    for s in self._vector_sliders:
      s.set_enabled(mode == MODE_VECTOR)
    active = mode != MODE_OFF
    for cb, s in ((self.min_px_on, self.min_px), (self.raster_on, self.radius),
                  (self.gamma_on, self.gamma)):
      cb.setEnabled(active)
      s.set_enabled(active and cb.isChecked(), label_too=False)

  def _changed(self, *_):
    if self._loading:
      return
    self._update_enabled()
    self._debounce.start()

  def _changed_now(self, *_):
    if not self._loading:
      self.settingsChanged.emit(self.settings())
