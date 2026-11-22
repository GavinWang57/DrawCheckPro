"""列印含標記的圖面。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QWidget

from app.document import DrawingDocument
from app.marks.model import Mark
from app.marks.pdf_export import _page_image, build_marked_document

MAX_PRINT_DPI = 300


def _fit(img_w: int, img_h: int, area: QRectF) -> QRectF:
  k = min(area.width() / img_w, area.height() / img_h)
  w, h = img_w * k, img_h * k
  return QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)


def print_marked(parent: QWidget, drawing: DrawingDocument, marks: list[Mark], pages: list[int],
                 enhanced: bool, title: str) -> bool:
  printer = QPrinter(QPrinter.PrinterMode.HighResolution)
  printer.setDocName(title)
  dlg = QPrintDialog(printer, parent)
  dlg.setWindowTitle("列印")
  dlg.setOption(QPrintDialog.PrintDialogOption.PrintPageRange, False)
  if dlg.exec() != QPrintDialog.DialogCode.Accepted:
    return False
  paint_to_printer(printer, drawing, marks, pages, enhanced)
  return True


def paint_to_printer(printer: QPrinter, drawing: DrawingDocument, marks: list[Mark],
                     pages: list[int], enhanced: bool):
  dpi = min(printer.resolution(), MAX_PRINT_DPI)
  doc = build_marked_document(drawing, marks, pages, enhanced)
  painter = QPainter()
  if not painter.begin(printer):
    doc.close()
    raise RuntimeError("無法開始列印，請確認印表機狀態。")
  try:
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for i, page in enumerate(doc):
      if i:
        printer.newPage()
      arr = _page_image(page, dpi)
      img = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0],
                   QImage.Format.Format_RGB888).copy()
      area = QRectF(printer.pageRect(QPrinter.Unit.DevicePixel))
      area.moveTo(0, 0)
      # 頁面方向和紙張方向不同時旋轉 90°，讓圖面盡量填滿紙張
      if (img.width() > img.height()) != (area.width() > area.height()):
        img = img.transformed(QTransform().rotate(90), Qt.TransformationMode.SmoothTransformation)
      painter.drawImage(_fit(img.width(), img.height(), area), img)
  finally:
    painter.end()
    doc.close()
