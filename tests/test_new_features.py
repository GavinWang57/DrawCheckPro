import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.marks.model import KIND_TEXT, Mark, parse_color  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
  return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path, drawing_pdf):
  QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "cfg"))
  from app.main_window import MainWindow
  w = MainWindow()
  w.resize(1400, 850)
  w.show()
  w.open_pdf(str(drawing_pdf))
  for _ in range(10):
    qapp.processEvents()
  yield w
  w.ctl.set_dirty(False)
  w.close()


def _wait(qapp, ms):
  end = time.perf_counter() + ms / 1000
  while time.perf_counter() < end:
    qapp.processEvents()


def test_live_search_runs_while_typing(window, qapp):
  sp = window.search_panel
  sp.edit.setText("H7")
  assert sp.hits == []
  _wait(qapp, 400)
  assert len(sp.hits) == 1
  sp.edit.setText("")
  assert sp.hits == [] and window.view._hit_items == []


def test_text_mark_create_edit_undo(window):
  v = window.view
  style = {"font_size": 8.0, "bold": True, "text_color": "#ffff0000",
           "fill_color": "#80ffffff", "border_color": "#ff0000ff", "border_width": 1.0}
  v.create_text_mark(QPointF(50, 80), {"text": "孔位待確認", "link": "https://a.b",
                                       "style": style, "status": "pending", "checker": "QC"})
  m = window.ctl.marks()[0]
  assert m.kind == KIND_TEXT and m.text == "孔位待確認" and m.link == "https://a.b"
  r = v.mark_display_rect(m)
  assert abs(r.left() - 50) < 0.01 and r.width() > 20 and r.height() > 8
  assert "孔位待確認" in window.marks_panel.table.item(0, 4).text()

  longer = v.resized_text_rect(m, "孔位待確認，請量測 Ø8 H7 的真圓度", style)
  window.ctl.update_marks([m.id], text="孔位待確認，請量測 Ø8 H7 的真圓度", rect=longer)
  assert window.ctl.get(m.id).rect[2] - window.ctl.get(m.id).rect[0] > r.width()
  window.ctl.undo_stack.undo()
  assert window.ctl.get(m.id).text == "孔位待確認"


def test_snapshot_renders_region_with_marks(window):
  v = window.view
  v.create_text_mark(QPointF(20, 100), {"text": "X", "style": {"font_size": 12.0}})
  img = v.render_snapshot(QRectF(10, 90, 200, 70))
  assert not img.isNull()
  assert img.width() >= 400 and abs(img.width() / img.height() - 200 / 70) < 0.1
  pixels = [img.pixelColor(x, y) for x in range(img.width()) for y in range(img.height())]
  assert any(max(c.red(), c.green(), c.blue()) < 90 for c in pixels), "圖面線條應該被渲染"
  assert any(c.red() > 230 and c.green() > 220 and c.blue() < 200 for c in pixels), \
    "文字框的黃色底色應該疊在截圖上"
  assert all(it.isVisible() for it in v.items_by_id.values())
  assert v.page_item.isVisible()


def test_print_pipeline_to_pdf_printer(qapp, tmp_path, drawing_pdf):
  import pymupdf as fitz
  from PySide6.QtGui import QPageLayout, QPageSize
  from PySide6.QtPrintSupport import QPrinter
  from app.document import DrawingDocument
  from app.printing import paint_to_printer
  printer = QPrinter(QPrinter.PrinterMode.HighResolution)
  printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
  out = tmp_path / "printed.pdf"
  printer.setOutputFileName(str(out))
  printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
  printer.setPageOrientation(QPageLayout.Orientation.Portrait)
  m = Mark(page=0, kind=KIND_TEXT, rect=[100, 150, 260, 175], text="列印測試", no=1)
  paint_to_printer(printer, DrawingDocument(drawing_pdf), [m], [0], enhanced=True)
  res = fitz.open(out)
  assert res.page_count == 1
  pix = res[0].get_pixmap(dpi=30)
  assert len(set(pix.samples)) > 2  # 有實際內容，不是空白頁


def test_parse_color():
  assert parse_color("#80ff0000") == ((1.0, 0.0, 0.0), pytest.approx(128 / 255))
  assert parse_color("#00ff00") == ((0.0, 1.0, 0.0), 1.0)


def test_export_contains_text_mark(tmp_path, drawing_pdf):
  import pymupdf as fitz
  from app.document import DrawingDocument
  from app.marks.pdf_export import save_pdf
  doc = DrawingDocument(drawing_pdf)
  m = Mark(page=0, kind=KIND_TEXT, rect=[100, 150, 260, 175], text="真圓度 0.01", no=1,
           style={"font_size": 9})
  out = tmp_path / "t.pdf"
  save_pdf(doc, [m], [0], False, out)
  assert "真圓度" in fitz.open(out)[0].get_text()
