import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as fitz  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QSignalSpy, QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.marks.model import KIND_TEXT, STATUS_NONE, STATUS_OK, Mark  # noqa: E402


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


def test_time_format_and_legacy_iso():
  import re
  from app.marks.model import now_iso
  assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", now_iso())
  m = Mark.from_dict({"page": 0, "kind": "rect", "rect": [0, 0, 1, 1],
                      "created": "2026-11-21T23:00:01", "updated": "2026-11-21T23:05:09"})
  assert m.created == "2026-11-21 23:00:01" and m.updated == "2026-11-21 23:05:09"


def test_marker_defaults_to_computer_user(window):
  import getpass
  v = window.view
  assert v.checker == getpass.getuser()
  v._create_mark("rect", STATUS_NONE, QRectF(20, 30, 50, 10))
  v.create_text_mark(QPointF(100, 100), {"text": "A", "style": {}})
  assert {m.checker for m in window.ctl.marks()} == {getpass.getuser()}


def test_new_marks_default_to_no_status(window):
  v = window.view
  v._create_mark("rect", STATUS_NONE, QRectF(20, 30, 50, 10))
  v.create_text_mark(QPointF(100, 100), {"text": "純文字", "style": {}})
  assert all(m.status == STATUS_NONE for m in window.ctl.marks())
  assert "無狀態：2" in window.marks_panel.summary.text()


def test_set_status_then_back_to_none(window):
  v = window.view
  v.create_text_mark(QPointF(100, 100), {"text": "A", "style": {}})
  m = window.ctl.marks()[0]
  window.a_ok.trigger()
  assert window.ctl.get(m.id).status == STATUS_OK
  window.a_none.trigger()
  assert window.ctl.get(m.id).status == STATUS_NONE
  assert window.a_none.shortcut().toString() == "0"


def test_escape_returns_to_select(window, qapp):
  from app.viewer import page_view as pv
  window.select_tool(pv.TOOL_RECT)
  QTest.keyClick(window.view, Qt.Key.Key_Escape)
  assert window.view.tool == pv.TOOL_SELECT
  assert window.tool_actions[pv.TOOL_SELECT].isChecked()


def test_right_click_in_review_tool_requests_tool_menu(window, qapp):
  from PySide6.QtGui import QContextMenuEvent
  from app.viewer import page_view as pv
  window.view.toolMenuRequested.disconnect()
  spy = QSignalSpy(window.view.toolMenuRequested)
  window.select_tool(pv.TOOL_TEXT)
  pos = window.view.viewport().rect().center()
  ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, window.view.mapToGlobal(pos))
  window.view.contextMenuEvent(ev)
  assert spy.count() == 1


def test_text_format_controls(qapp):
  from app.marks import text_layout
  from app.marks.text_dialog import TextMarkDialog
  dlg = TextMarkDialog("格式 Format")
  dlg.italic.setChecked(True)
  dlg.strike.setChecked(True)
  dlg.underline.setCurrentIndex(dlg.underline.findData("double"))
  st = dlg.values()["style"]
  assert st["italic"] and st["strike"] and st["underline"] == "double"
  assert dlg.values()["status"] == STATUS_NONE
  plain_w, _ = text_layout.measure("格式 Format", {"font_size": 10})
  italic_w, _ = text_layout.measure("格式 Format", {"font_size": 10, "italic": True})
  assert italic_w > plain_w


def test_pdf_text_decorations_and_no_badge(tmp_path, drawing_pdf):
  from app.document import DrawingDocument
  from app.marks.pdf_export import save_pdf

  def drawings(style, status):
    m = Mark(page=0, kind=KIND_TEXT, rect=[100, 150, 230, 170], text="尺寸 Ø8", no=1,
             status=status, style={"font_size": 9, "fill_color": "#00ffffff", "border_width": 0,
                                   **style})
    out = tmp_path / f"d{len(style)}{status}.pdf"
    save_pdf(DrawingDocument(drawing_pdf), [m], [0], False, out)
    return len(fitz.open(out)[0].get_drawings())

  base = drawings({}, STATUS_NONE)
  assert drawings({"underline": "double", "strike": True}, STATUS_NONE) == base + 3
  assert drawings({}, STATUS_OK) > base  # 有狀態才畫徽章
