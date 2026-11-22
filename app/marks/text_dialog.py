"""文字框標記的編輯對話框：內容、文字／框線格式、連結、核對狀態，附即時預覽。"""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDoubleValidator, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from app.marks import text_layout
from app.marks.model import STATUS_LABELS, STATUS_NONE, STATUSES, UNDERLINES, text_style

FONT_SIZES = (6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72)
FONT_MIN, FONT_MAX = 2.0, 200.0
BORDER_WIDTHS = (0.0, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
PREVIEW_W, PREVIEW_H = 400, 120


def _fmt(v: float) -> str:
  return f"{v:g}"


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
               status: str = "none", checker: str = "", title: str = "文字標記", parent=None):
    super().__init__(parent)
    self.setWindowTitle(title)
    s = text_style(style)

    self.text = QPlainTextEdit(text)
    self.text.setPlaceholderText("輸入要顯示在圖面上的文字（可多行）")
    self.text.setMinimumHeight(70)

    fmt = QGroupBox("格式")
    ff = QFormLayout(fmt)
    self.font_size = QComboBox()
    self.font_size.setEditable(True)
    self.font_size.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    self.font_size.addItems([_fmt(v) for v in FONT_SIZES])
    self.font_size.setValidator(QDoubleValidator(FONT_MIN, FONT_MAX, 1, self))
    self.font_size.setCurrentText(_fmt(s["font_size"]))
    self.font_size.setToolTip("直接輸入或從清單選擇（單位 pt）")
    self.font_size.setFixedWidth(90)
    row = QHBoxLayout()
    row.addWidget(self.font_size)
    row.addWidget(QLabel("pt"))
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

    self.status = QComboBox()
    for st in STATUSES:
      self.status.addItem(STATUS_LABELS[st], st)
    self.status.setCurrentIndex(STATUSES.index(status) if status in STATUSES else 0)
    self.checker = QLineEdit(checker)
    meta = QFormLayout()
    meta.addRow("核對狀態", self.status)
    meta.addRow("標記人", self.checker)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(self._accept)
    buttons.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addWidget(self.text)
    lay.addWidget(fmt)
    lay.addWidget(link_box)
    lay.addLayout(meta)
    lay.addWidget(buttons)

    for sig in (self.text.textChanged, self.font_size.currentTextChanged, self.bold.toggled,
                self.italic.toggled, self.strike.toggled, self.underline.currentIndexChanged,
                self.text_color.changed, self.fill_color.changed, self.fill_clear.toggled,
                self.border_color.changed, self.border_width.currentIndexChanged,
                self.status.currentIndexChanged, self.link.textChanged):
      sig.connect(self._refresh)
    self._refresh()
    self.resize(500, 0)

  def _font_size(self) -> float:
    try:
      v = float(self.font_size.currentText())
    except ValueError:
      return text_style(None)["font_size"]
    return min(max(v, FONT_MIN), FONT_MAX)

  def _style(self) -> dict:
    return {
      "font_size": round(self._font_size(), 1),
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
    if self.status.currentData() != STATUS_NONE:
      paint_status_badge(p, badge, self.status.currentData())
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
      "status": self.status.currentData(),
      "checker": self.checker.text().strip(),
      "style": self._style(),
    }
