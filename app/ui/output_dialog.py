"""輸出標記檔／列印的選項。"""
from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QLabel, QRadioButton, QVBoxLayout)

PAGE_PDF = "page_pdf"
ALL_PDF = "all_pdf"
PAGE_PNG = "page_png"
ALL_PNG = "all_png"
FORMATS = (
  (PAGE_PDF, "本頁 → 單頁 PDF"),
  (ALL_PDF, "全部頁 → PDF"),
  (PAGE_PNG, "本頁 → PNG 圖片"),
  (ALL_PNG, "全部頁 → 合併成一張 PNG"),
)
DPI_CHOICES = (96, 150, 200, 300)

SCOPE_PAGE = "page"
SCOPE_ALL = "all"


def _enhance_box(checked: bool) -> tuple[QGroupBox, QCheckBox]:
  box = QGroupBox("圖面")
  lay = QVBoxLayout(box)
  cb = QCheckBox("套用目前的向量加粗設定（細線較清楚，但線寬和原圖不同）")
  cb.setChecked(checked)
  lay.addWidget(cb)
  hint = QLabel("PDF 中的標記一律為向量；書籤會依頁面列出每個標記。")
  hint.setObjectName("Muted")
  hint.setWordWrap(True)
  lay.addWidget(hint)
  return box, cb


class OutputDialog(QDialog):
  def __init__(self, preset: str, current_page: int, page_count: int, enhanced: bool = False,
               parent=None):
    super().__init__(parent)
    self.setWindowTitle("輸出含標記的圖面")
    fmt_box = QGroupBox("範圍與格式")
    fl = QVBoxLayout(fmt_box)
    self.group = QButtonGroup(self)
    self.buttons: dict[str, QRadioButton] = {}
    for key, text in FORMATS:
      if key == PAGE_PDF or key == PAGE_PNG:
        text = text.replace("本頁", f"本頁（第 {current_page + 1} 頁）")
      if key in (ALL_PDF, ALL_PNG):
        text += f"（共 {page_count} 頁）"
      rb = QRadioButton(text)
      self.group.addButton(rb)
      self.buttons[key] = rb
      fl.addWidget(rb)
    self.buttons.get(preset, self.buttons[ALL_PDF]).setChecked(True)

    self.dpi = QComboBox()
    for d in DPI_CHOICES:
      self.dpi.addItem(f"{d} dpi", d)
    self.dpi.setCurrentIndex(DPI_CHOICES.index(200))
    png_form = QFormLayout()
    png_form.addRow("PNG 解析度", self.dpi)

    enh_box, self.enhanced = _enhance_box(enhanced)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                          | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("輸出…")
    bb.accepted.connect(self.accept)
    bb.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addWidget(fmt_box)
    lay.addLayout(png_form)
    lay.addWidget(enh_box)
    lay.addWidget(bb)
    self.group.buttonToggled.connect(self._update)
    self._update()
    self.resize(440, 0)

  def _update(self, *_):
    self.dpi.setEnabled(self.choice() in (PAGE_PNG, ALL_PNG))

  def choice(self) -> str:
    return next(k for k, b in self.buttons.items() if b.isChecked())


class PrintOptionsDialog(QDialog):
  def __init__(self, current_page: int, page_count: int, enhanced: bool = False, parent=None):
    super().__init__(parent)
    self.setWindowTitle("列印含標記的圖面")
    scope = QGroupBox("範圍")
    sl = QVBoxLayout(scope)
    self.page = QRadioButton(f"本頁（第 {current_page + 1} 頁）")
    self.all = QRadioButton(f"全部頁（共 {page_count} 頁）")
    (self.all if page_count > 1 else self.page).setChecked(True)
    sl.addWidget(self.page)
    sl.addWidget(self.all)
    enh_box, self.enhanced = _enhance_box(enhanced)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                          | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("下一步：選擇印表機…")
    bb.accepted.connect(self.accept)
    bb.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addWidget(scope)
    lay.addWidget(enh_box)
    lay.addWidget(bb)
    self.resize(440, 0)

  def scope(self) -> str:
    return SCOPE_PAGE if self.page.isChecked() else SCOPE_ALL
