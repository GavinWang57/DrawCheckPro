import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.document import DrawingDocument  # noqa: E402
from app.ui.info_panel import paper_name, pdf_date  # noqa: E402
from app.ui.search_panel import search_document  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
  return QApplication.instance() or QApplication([])


def test_search_finds_text_and_rotated_coords(tmp_path):
  from tests.conftest import make_drawing_pdf
  p = tmp_path / "rot.pdf"
  make_drawing_pdf(p, rotate=90)
  doc = DrawingDocument(p)
  hits = search_document(doc, "H7")
  assert len(hits) == 1
  pno, r, ctx = hits[0]
  assert pno == 0 and "H7" in ctx
  d = r * doc.rotation_matrix(0)
  assert doc.page_rect(0).contains(d)


def test_paper_and_date_helpers():
  assert paper_name(842, 595) == "A4 橫式"
  assert paper_name(1684, 1191) == "A2 橫式"
  assert paper_name(595, 842) == "A4 直式"
  assert pdf_date("D:20250604103200+08'00'") == "2025-06-04 10:32"
  assert pdf_date("") == ""


def test_bottom_bar_page_entry(qapp):
  from app.ui.bottom_bar import BottomBar
  b = BottomBar()
  got = []
  b.pageRequested.connect(got.append)
  b.set_pages(0, 3)
  b.page.setText("3")
  b.page.editingFinished.emit()
  b.next.click()
  assert got == [2, 1]
  assert not b.prev.isEnabled()
  b.set_zoom_percent(250)
  assert b.pct.value() == 250


def test_ribbon_sides_and_multipage_thumbs(qapp, tmp_path):
  import pymupdf as fitz
  from PySide6.QtCore import QSettings
  QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "cfg"))
  from app.main_window import MainWindow
  from app.ui.side_panel import STRIP_W
  pdf = tmp_path / "multi.pdf"
  d = fitz.open()
  for i in range(3):
    d.new_page(width=842, height=595).insert_text((50, 50), f"P{i + 1}")
  d.save(pdf)

  w = MainWindow()
  w.resize(1400, 850)
  w.show()
  w.open_pdf(str(pdf))
  for _ in range(20):
    qapp.processEvents()
  assert w.thumbs.count() == 3
  assert all(not w.thumbs.item(i).icon().isNull() for i in range(3))

  w.ribbon.tabs.setCurrentIndex(3)
  assert w.ribbon.stack.currentIndex() == 3

  w.view.set_page(2)
  assert w.thumbs.currentRow() == 2

  before = w.splitter.sizes()
  w.left_side.collapse()
  qapp.processEvents()
  sizes = w.splitter.sizes()
  assert sizes[0] == STRIP_W and sizes[1] > before[1]
  w.left_side.expand()
  qapp.processEvents()
  assert w.splitter.sizes()[0] > STRIP_W
  w.ctl.set_dirty(False)
  w.close()


def test_recent_files_and_search_highlight(qapp, tmp_path, drawing_pdf):
  from PySide6.QtCore import QSettings
  QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "cfg"))
  from app.main_window import MainWindow
  w = MainWindow()
  w.show()
  w.open_pdf(str(drawing_pdf))
  assert w._recent()[0].endswith("A001.pdf")
  w.focus_search()
  w.search_panel.edit.setText("H7")
  w.search_panel.run()
  assert len(w.view._hit_items) == 1
  w.search_panel.edit.clear()
  assert w.view._hit_items == []
  w.ctl.set_dirty(False)
  w.close()
