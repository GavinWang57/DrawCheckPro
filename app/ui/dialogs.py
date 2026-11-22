"""設定與說明對話框。"""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QTextBrowser, QVBoxLayout)

from app.marks.model import default_marker
from app.marks.store import sidecar_path
from app.ui import manual


class HelpDialog(QDialog):
  def __init__(self, app_name: str, version: str, parent=None):
    super().__init__(parent)
    self.setWindowTitle("使用說明")
    tb = QTextBrowser()
    tb.setHtml(manual.html(app_name, version))
    tb.setOpenExternalLinks(True)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addWidget(tb)
    lay.addWidget(buttons)
    self.resize(680, 760)


class SettingsDialog(QDialog):
  def __init__(self, checker: str, pdf_path=None, parent=None):
    super().__init__(parent)
    self.setWindowTitle("設定")
    self.checker = QLineEdit(checker)
    self.checker.setPlaceholderText(f"留空＝使用電腦使用者（{default_marker()}）")
    form = QFormLayout()
    form.addRow("標記人", self.checker)
    if pdf_path:
      side = QLabel(str(sidecar_path(pdf_path)))
      side.setObjectName("Muted")
      side.setWordWrap(True)
      form.addRow("目前標記檔", side)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addLayout(form)
    lay.addWidget(buttons)
    self.resize(460, 150)

  def checker_name(self) -> str:
    return self.checker.text().strip()
