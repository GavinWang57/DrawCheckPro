"""屬性資訊：檔案資訊卡片。"""
from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.document import DrawingDocument
from app.ui import icons

_ISO = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}
_PDF_DATE = re.compile(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?")


def pdf_date(raw: str) -> str:
  m = _PDF_DATE.match(raw or "")
  if not m:
    return ""
  y, mo, d, h, mi = (g or "00" for g in m.groups())
  return f"{y}-{mo if mo != '00' else '01'}-{d if d != '00' else '01'} {h}:{mi}"


def human_size(n: int) -> str:
  for unit in ("B", "KB", "MB", "GB"):
    if n < 1024 or unit == "GB":
      return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
    n /= 1024
  return ""


def paper_name(w_pt: float, h_pt: float) -> str:
  w, h = w_pt / 72 * 25.4, h_pt / 72 * 25.4
  short, long_ = sorted((w, h))
  orient = "橫式" if w > h else "直式"
  for name, (a, b) in _ISO.items():
    if abs(short - a) < 4 and abs(long_ - b) < 4:
      return f"{name} {orient}"
  return f"{w:.0f}×{h:.0f} mm"


class _Card(QFrame):
  def __init__(self, icon_name: str, title: str):
    super().__init__()
    self.setObjectName("Card")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(12, 10, 12, 12)
    head = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(icons.icon(icon_name).pixmap(QSize(16, 16)))
    t = QLabel(title)
    t.setObjectName("CardTitle")
    head.addWidget(ic)
    head.addWidget(t)
    head.addStretch(1)
    lay.addLayout(head)
    self.grid = QGridLayout()
    self.grid.setHorizontalSpacing(14)
    self.grid.setVerticalSpacing(9)
    self.grid.setColumnStretch(1, 1)
    lay.addLayout(self.grid)
    self._rows: dict[str, QLabel] = {}

  def set_rows(self, rows: list[tuple[str, str]]):
    while self.grid.count():
      w = self.grid.takeAt(0).widget()
      if w:
        w.setParent(None)
        w.deleteLater()
    for i, (k, v) in enumerate(rows):
      kl = QLabel(k)
      kl.setObjectName("Muted")
      vl = QLabel(v)
      vl.setToolTip(v)
      vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
      vl.setMinimumWidth(10)
      self.grid.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
      self.grid.addWidget(vl, i, 1)


class InfoPanel(QWidget):
  def __init__(self, parent=None):
    super().__init__(parent)
    self.file_card = _Card("star", "檔案資訊")
    lay = QVBoxLayout(self)
    lay.setContentsMargins(8, 10, 8, 8)
    lay.setSpacing(10)
    lay.addWidget(self.file_card)
    lay.addStretch(1)
    self.set_document(None)

  def set_document(self, doc: DrawingDocument | None):
    if doc is None:
      self.file_card.set_rows([("檔名", "—"), ("頁數", "—")])
      return
    meta = doc.base.metadata or {}
    st = doc.path.stat()
    r = doc.page_rect(0)
    created = pdf_date(meta.get("creationDate", "")) or \
      datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M")
    modified = pdf_date(meta.get("modDate", "")) or \
      datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
    name = doc.path.name
    shown = name if len(name) <= 26 else name[:24] + "…"
    rows = [
      ("檔名", shown),
      ("頁數", f"{doc.page_count} 頁"),
      ("檔案大小", human_size(st.st_size)),
      ("圖紙", paper_name(r.width, r.height)),
      ("建立日期", created),
      ("修改日期", modified),
      ("PDF 版本", (meta.get("format") or "").replace("PDF ", "") or "—"),
      ("產生軟體", meta.get("creator") or meta.get("producer") or "—"),
    ]
    self.file_card.set_rows(rows)
    self.file_card.grid.itemAtPosition(0, 1).widget().setToolTip(str(doc.path))
