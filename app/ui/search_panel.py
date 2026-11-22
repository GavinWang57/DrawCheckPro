"""搜尋圖面文字。CAD 以線條繪製的文字無法搜尋，只能找到真正的 PDF 文字。"""
from __future__ import annotations

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QVBoxLayout, QWidget)

from app.document import DrawingDocument
from app.ui import icons

MAX_HITS = 500
LIVE_DELAY_MS = 250


def search_document(doc: DrawingDocument, text: str) -> list[tuple[int, fitz.Rect, str]]:
  """回傳 (頁碼, 未旋轉座標的 rect, 前後文)。"""
  hits = []
  for pno in range(doc.page_count):
    page = doc.base[pno]
    for r in page.search_for(text):
      ctx_rect = fitz.Rect(r.x0 - 60, r.y0 - 1, r.x1 + 60, r.y1 + 1)
      ctx = " ".join(page.get_textbox(ctx_rect).split()) or text
      hits.append((pno, fitz.Rect(r), ctx))
      if len(hits) >= MAX_HITS:
        return hits
  return hits


class SearchPanel(QWidget):
  hitsChanged = Signal(list)        # [(page, Rect)]
  hitActivated = Signal(int, int)   # index, page

  def __init__(self, parent=None):
    super().__init__(parent)
    self.doc: DrawingDocument | None = None
    self.hits: list[tuple[int, fitz.Rect, str]] = []

    self.edit = QLineEdit()
    self.edit.setPlaceholderText("輸入尺寸、公差或文字，會即時顯示結果")
    self.edit.setClearButtonEnabled(True)
    self.edit.addAction(icons.icon("search", "#8fa6c4"), QLineEdit.ActionPosition.LeadingPosition)
    row = QHBoxLayout()
    row.addWidget(self.edit, 1)
    self._live = QTimer(self)
    self._live.setSingleShot(True)
    self._live.setInterval(LIVE_DELAY_MS)
    self._live.timeout.connect(self.run)

    self.status = QLabel("")
    self.status.setObjectName("Muted")
    self.status.setWordWrap(True)
    self.list = QListWidget()

    lay = QVBoxLayout(self)
    lay.setContentsMargins(8, 10, 8, 8)
    lay.addLayout(row)
    lay.addWidget(self.status)
    lay.addWidget(self.list, 1)

    self.edit.returnPressed.connect(self.run)
    self.edit.textChanged.connect(self._on_text)
    self.list.currentRowChanged.connect(
      lambda i: i >= 0 and self.hitActivated.emit(i, self.hits[i][0]))

  def _on_text(self, text: str):
    if text.strip():
      self._live.start()
    else:
      self._live.stop()
      self.clear()

  def set_document(self, doc: DrawingDocument | None):
    self.doc = doc
    self.edit.clear()
    self.clear()

  def clear(self):
    self.hits = []
    self.list.clear()
    self.status.setText("")
    self.hitsChanged.emit([])

  def run(self):
    self._live.stop()
    text = self.edit.text().strip()
    if not self.doc or not text:
      self.clear()
      return
    self.hits = search_document(self.doc, text)
    self.list.blockSignals(True)
    self.list.clear()
    for pno, _r, ctx in self.hits:
      it = QListWidgetItem(f"第 {pno + 1} 頁　{ctx}")
      it.setToolTip(ctx)
      self.list.addItem(it)
    self.list.blockSignals(False)
    if self.hits:
      more = f"（只顯示前 {MAX_HITS} 筆）" if len(self.hits) >= MAX_HITS else ""
      self.status.setText(f"找到 {len(self.hits)} 筆{more}")
    else:
      self.status.setText("找不到。注意：CAD 用線條繪製的文字（例如部分尺寸數字）無法搜尋。")
    self.hitsChanged.emit([(p, r) for p, r, _ in self.hits])
    if self.hits:
      self.list.setCurrentRow(0)
