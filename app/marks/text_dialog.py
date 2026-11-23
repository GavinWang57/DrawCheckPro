"""文字框標記的編輯對話框：內容、文字／框線格式、連結、核對狀態，附即時預覽。"""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDoubleValidator, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QToolButton,
                               QVBoxLayout)

from app.marks import text_layout
from app.marks.model import STATUS_LABELS, STATUS_NONE, STATUSES, UNDERLINES, text_style
from app.marks.symbols import SYMBOL_GROUPS
from app.ui import icons

UNIT_PT, UNIT_MM = "pt", "mm"
MM_PER_PT = 25.4 / 72
FONT_SIZES = {
  UNIT_PT: (6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72),
  UNIT_MM: (1.8, 2.5, 3.5, 5, 7, 10, 14, 20),  # ISO 3098 字高系列
}
FONT_MIN, FONT_MAX = 2.0, 200.0  # pt
STATUS_ICONS = {"none": "status_none", "ok": "stamp_ok", "ng": "stamp_ng",
                "pending": "stamp_pending"}
BORDER_WIDTHS = (0.0, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
PREVIEW_W, PREVIEW_H = 400, 120


def _fmt(v: float) -> str:
  return f"{v:g}"


def pt_to_unit(pt: float, unit: str) -> float:
  return round(pt * MM_PER_PT, 2) if unit == UNIT_MM else round(pt, 1)


def unit_to_pt(value: float, unit: str) -> float:
  return value / MM_PER_PT if unit == UNIT_MM else value


class ColorButton(QPushButton):
  changed = Signal(str)

  def __init__(self, value: str):
    super().__init__()
    self.setFixedWidth(70)
    self.value = value
    self._paint()
    self.clicked.connect(self._pick)

  def _paint(self):
    c = QColor(self.value)
    self.setStyleSheet(
      f"QPushButton {{ background: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()});"
      " border: 1px solid #5d7ea8; border-radius: 4px; min-height: 20px; }"
      "QPushButton:disabled { background: transparent; border-style: dashed; }")
    self.setToolTip(f"{c.name(QColor.NameFormat.HexArgb)}（點選變更，可設定透明度）")

  def set_value(self, value: str):
    self.value = value
    self._paint()
    self.changed.emit(value)

  def _pick(self):
    c = QColorDialog.getColor(QColor(self.value), self, "選擇顏色",
                              QColorDialog.ColorDialogOption.ShowAlphaChannel)
    if c.isValid():
      self.set_value(c.name(QColor.NameFormat.HexArgb))


def link_url(link: str) -> QUrl:
  if link.lower().startswith(("http://", "https://", "mailto:", "file:")):
    return QUrl(link)
  return QUrl.fromLocalFile(os.path.abspath(link))


def open_link(link: str) -> bool:
  return bool(link) and QDesktopServices.openUrl(link_url(link))


def _transparent(hex_argb: str) -> str:
  c = QColor(hex_argb)
  c.setAlpha(0)
  return c.name(QColor.NameFormat.HexArgb)


class TextMarkDialog(QDialog):
  def __init__(self, text: str = "", style: dict | None = None, link: str = "",
               status: str = "none", checker: str = "", title: str = "文字標記", parent=None,
               font_unit: str = UNIT_PT):
    super().__init__(parent)
    self.setWindowTitle(title)
    s = text_style(style)

    status_row = QHBoxLayout()
    status_row.addWidget(QLabel("核對狀態"))
    self.status_group = QButtonGroup(self)
    self.status_group.setExclusive(True)
    self.status_buttons: dict[str, QToolButton] = {}
    for st in STATUSES:
      b = QToolButton()
      b.setText(STATUS_LABELS[st])
      b.setIcon(icons.icon(STATUS_ICONS[st]))
      b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
      b.setCheckable(True)
      b.setObjectName("StatusChip")
      b.setMinimumWidth(80)
      self.status_group.addButton(b)
      self.status_buttons[st] = b
      status_row.addWidget(b)
    status_row.addStretch(1)
    self.status_buttons[status if status in STATUSES else STATUS_NONE].setChecked(True)

    self.text = QPlainTextEdit(text)
    self.text.setPlaceholderText("輸入要顯示在圖面上的文字（可多行）")
    self.text.setMinimumHeight(70)
    symbols_box = self._build_symbols()

    fmt = QGroupBox("格式")
    ff = QFormLayout(fmt)
    self.font_size = QComboBox()
    self.font_size.setEditable(True)
    self.font_size.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    self.font_size.setToolTip("直接輸入或從清單選擇")
    self.font_size.setFixedWidth(90)
    self.font_unit = QComboBox()
    self.font_unit.addItem("pt", UNIT_PT)
    self.font_unit.addItem("mm", UNIT_MM)
    self.font_unit.setToolTip("字級單位；mm 為圖面上的實際字高（1 pt ≈ 0.353 mm）")
    self._unit = font_unit if font_unit in (UNIT_PT, UNIT_MM) else UNIT_PT
    self.font_unit.setCurrentIndex(self.font_unit.findData(self._unit))
    self._fill_font_sizes(s["font_size"])
    self.font_unit.currentIndexChanged.connect(self._on_unit_changed)
    row = QHBoxLayout()
    row.addWidget(self.font_size)
    row.addWidget(self.font_unit)
    row.addStretch(1)
    ff.addRow("字級", row)

    self.bold = QCheckBox("粗體")
    self.bold.setChecked(bool(s["bold"]))
    self.italic = QCheckBox("斜體")
    self.italic.setChecked(bool(s["italic"]))
    self.strike = QCheckBox("刪除線")
    self.strike.setChecked(bool(s["strike"]))
    self.underline = QComboBox()
    for key, label in (("none", "無底線"), ("single", "底線"), ("double", "雙底線")):
      self.underline.addItem(label, key)
    self.underline.setCurrentIndex(max(0, UNDERLINES.index(s["underline"])
                                       if s["underline"] in UNDERLINES else 0))
    srow = QHBoxLayout()
    for w in (self.bold, self.italic, self.underline, self.strike):
      srow.addWidget(w)
    srow.addStretch(1)
    ff.addRow("字型", srow)

    self.text_color = ColorButton(s["text_color"])
    ff.addRow("文字顏色", self.text_color)

    fill_q = QColor(s["fill_color"])
    self.fill_color = ColorButton(s["fill_color"] if fill_q.alpha() else "#e6fff59d")
    self.fill_clear = QCheckBox("透明")
    self.fill_clear.setChecked(fill_q.alpha() == 0)
    frow = QHBoxLayout()
    frow.addWidget(self.fill_color)
    frow.addWidget(self.fill_clear)
    frow.addStretch(1)
    ff.addRow("底色", frow)

    self.border_color = ColorButton(s["border_color"])
    self.border_width = QComboBox()
    for w in BORDER_WIDTHS:
      self.border_width.addItem("無框線" if w == 0 else f"{_fmt(w)} pt", w)
    current = min(BORDER_WIDTHS, key=lambda w: abs(w - s["border_width"]))
    self.border_width.setCurrentIndex(BORDER_WIDTHS.index(current))
    self.border_width.setFixedWidth(100)
    brow = QHBoxLayout()
    brow.addWidget(self.border_color)
    brow.addWidget(self.border_width)
    brow.addStretch(1)
    ff.addRow("框線", brow)

    self.preview = QLabel()
    self.preview.setFixedSize(PREVIEW_W, PREVIEW_H)
    self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.preview.setObjectName("TextPreview")
    ff.addRow("預覽", self.preview)

    link_box = QGroupBox("連結")
    lf = QHBoxLayout(link_box)
    self.link = QLineEdit(link)
    self.link.setPlaceholderText("https://… 或檔案路徑（可留空）")
    browse = QPushButton("瀏覽…")
    test = QPushButton("開啟")
    lf.addWidget(self.link, 1)
    lf.addWidget(browse)
    lf.addWidget(test)
    browse.clicked.connect(self._browse)
    test.clicked.connect(lambda: open_link(self.link.text().strip()))

    self.checker = QLineEdit(checker)
    meta = QFormLayout()
    meta.addRow("標記人", self.checker)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(self._accept)
    buttons.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addLayout(status_row)
    lay.addWidget(self.text)
    lay.addWidget(symbols_box)
    lay.addWidget(fmt)
    lay.addWidget(link_box)
    lay.addLayout(meta)
    lay.addWidget(buttons)

    for sig in (self.text.textChanged, self.font_size.currentTextChanged, self.bold.toggled,
                self.italic.toggled, self.strike.toggled, self.underline.currentIndexChanged,
                self.text_color.changed, self.fill_color.changed, self.fill_clear.toggled,
                self.border_color.changed, self.border_width.currentIndexChanged,
                self.status_group.buttonToggled, self.link.textChanged):
      sig.connect(self._refresh)
    self._refresh()
    self.resize(500, 0)

  def _build_symbols(self) -> QGroupBox:
    box = QGroupBox("插入符號")
    grid = QGridLayout(box)
    grid.setHorizontalSpacing(4)
    grid.setVerticalSpacing(4)
    self.symbol_buttons: dict[str, QToolButton] = {}
    for row, (group, items) in enumerate(SYMBOL_GROUPS):
      label = QLabel(group)
      label.setObjectName("Muted")
      grid.addWidget(label, row, 0)
      line = QHBoxLayout()
      line.setSpacing(3)
      for sym, name in items:
        b = QToolButton()
        b.setObjectName("SymbolButton")
        b.setText(sym)
        b.setToolTip(f"{name}　{sym}")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(lambda _=False, s=sym: self.insert_symbol(s))
        self.symbol_buttons[sym] = b
        line.addWidget(b)
      line.addStretch(1)
      grid.addLayout(line, row, 1)
    grid.setColumnStretch(1, 1)
    return box

  def insert_symbol(self, sym: str):
    self.text.insertPlainText(sym)
    self.text.setFocus()

  def _fill_font_sizes(self, pt: float):
    lo, hi = pt_to_unit(FONT_MIN, self._unit), pt_to_unit(FONT_MAX, self._unit)
    self.font_size.blockSignals(True)
    self.font_size.clear()
    self.font_size.addItems([_fmt(v) for v in FONT_SIZES[self._unit]])
    self.font_size.setValidator(QDoubleValidator(lo, hi, 2 if self._unit == UNIT_MM else 1, self))
    self.font_size.setCurrentText(_fmt(pt_to_unit(pt, self._unit)))
    self.font_size.blockSignals(False)

  def _on_unit_changed(self, *_):
    pt = self._font_size()
    self._unit = self.font_unit.currentData()
    self._fill_font_sizes(pt)
    self._refresh()

  def unit(self) -> str:
    return self._unit

  def _font_size(self) -> float:
    """目前字級（pt）。"""
    try:
      v = unit_to_pt(float(self.font_size.currentText()), self._unit)
    except ValueError:
      return text_style(None)["font_size"]
    return min(max(v, FONT_MIN), FONT_MAX)

  def status(self) -> str:
    for st, b in self.status_buttons.items():
      if b.isChecked():
        return st
    return STATUS_NONE

  def _style(self) -> dict:
    return {
      "font_size": round(self._font_size(), 2),
      "bold": self.bold.isChecked(),
      "text_color": self.text_color.value,
      "fill_color": _transparent(self.fill_color.value) if self.fill_clear.isChecked()
      else self.fill_color.value,
      "border_color": self.border_color.value,
      "border_width": self.border_width.currentData(),
      "italic": self.italic.isChecked(),
      "underline": self.underline.currentData(),
      "strike": self.strike.isChecked(),
    }

  def _refresh(self, *_):
    self.fill_color.setEnabled(not self.fill_clear.isChecked())
    self.border_color.setEnabled(self.border_width.currentData() > 0)
    self.preview.setPixmap(self.render_preview())

  def render_preview(self) -> QPixmap:
    """以實際比例畫出文字框（放不下時縮小），背景用淺色格紋以便看出透明底色。"""
    from app.marks.items import paint_status_badge, status_badge_rect
    style = self._style()
    text = self.text.toPlainText().strip() or "預覽文字"
    w, h = text_layout.measure(text, style)
    badge = status_badge_rect(QRectF(0, 0, w, h), style)
    full_w, full_h = badge.right() + 4, badge.bottom() + 4
    k = min(2.0, (PREVIEW_W - 16) / full_w, (PREVIEW_H - 16) / full_h)
    pm = QPixmap(PREVIEW_W, PREVIEW_H)
    pm.fill(QColor("#ffffff"))
    p = QPainter(pm)
    for y in range(0, PREVIEW_H, 10):
      for x in range(0, PREVIEW_W, 10):
        if (x // 10 + y // 10) % 2:
          p.fillRect(x, y, 10, 10, QColor("#eef1f5"))
    p.translate((PREVIEW_W - full_w * k) / 2, (PREVIEW_H - full_h * k) / 2)
    p.scale(k, k)
    box = QRectF(0, 0, w, h)
    text_layout.paint(p, box, text, style)
    if self.status() != STATUS_NONE:
      paint_status_badge(p, badge, self.status())
    p.end()
    return pm

  def _browse(self):
    path, _ = QFileDialog.getOpenFileName(self, "選擇連結的檔案")
    if path:
      self.link.setText(path)

  def _accept(self):
    if not self.text.toPlainText().strip():
      self.text.setFocus()
      self.text.setPlaceholderText("請輸入文字")
      return
    self.accept()

  def values(self) -> dict:
    return {
      "text": self.text.toPlainText().strip(),
      "link": self.link.text().strip(),
      "status": self.status(),
      "checker": self.checker.text().strip(),
      "style": self._style(),
    }
