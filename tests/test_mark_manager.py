import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as fitz  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.marks.filtering import MarkFilter, filter_marks  # noqa: E402
from app.marks.model import Mark  # noqa: E402


def _marks():
  return [
    Mark(page=1, kind="stamp", rect=[10, 10, 20, 20], status="ok", checker="王", no=3),
    Mark(page=0, kind="rect", rect=[30, 30, 60, 50], status="ng", note="孔位偏移", no=2),
    Mark(page=0, kind="text", rect=[100, 100, 150, 120], status="none", text="Ø8 H7",
         checker="李", no=1),
    Mark(page=2, kind="ellipse", rect=[50, 50, 80, 70], status="pending", measured="12.03",
         no=4),
  ]


def test_filter_marks():
  ms = _marks()
  assert [m.no for m in filter_marks(ms, MarkFilter())] == [1, 2, 3, 4]
  assert [m.no for m in filter_marks(ms, MarkFilter(statuses={"ok", "ng"}))] == [2, 3]
  assert [m.no for m in filter_marks(ms, MarkFilter(kinds={"text"}))] == [1]
  assert [m.no for m in filter_marks(ms, MarkFilter(page=0))] == [1, 2]
  assert [m.no for m in filter_marks(ms, MarkFilter(checker="王"))] == [3]
  assert [m.no for m in filter_marks(ms, MarkFilter(keyword="h7"))] == [1]
  assert [m.no for m in filter_marks(ms, MarkFilter(keyword="12.03"))] == [4]
  assert [m.no for m in filter_marks(ms, MarkFilter(keyword="#2"))] == [2]
  assert filter_marks(ms, MarkFilter(page=0, statuses={"ok"})) == []


@pytest.fixture(scope="module")
def qapp():
  return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
  doc = fitz.open()
  for _ in range(3):
    doc.new_page(width=420, height=297)
  pdf = tmp_path / "B001.pdf"
  doc.save(pdf)
  QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "cfg"))
  from app.main_window import MainWindow
  w = MainWindow()
  w.show()
  w.open_pdf(str(pdf))
  w.ctl.load(_marks())
  qapp.processEvents()
  yield w
  if w.mark_manager:
    w.mark_manager.close()
  w.ctl.set_dirty(False)
  w.close()


def _select(dlg, ids):
  sel = dlg.table.selectionModel()
  dlg.table.clearSelection()
  for row in range(dlg.table.rowCount()):
    if dlg._row_id(row) in ids:
      sel.select(dlg.table.model().index(row, 0),
                 sel.SelectionFlag.Select | sel.SelectionFlag.Rows)


def test_manager_filter_delete_undo(window, qapp, monkeypatch):
  window.open_mark_manager()
  dlg = window.mark_manager
  assert dlg.isVisible() and dlg.table.rowCount() == 4
  dlg.status_buttons["none"].setChecked(False)
  assert dlg.table.rowCount() == 3
  dlg.keyword.setText("孔位")
  assert dlg.table.rowCount() == 1
  dlg.clear_filter()
  assert dlg.table.rowCount() == 4
  assert dlg.page.count() == 4 and dlg.checker.count() == 3

  ids = [m.id for m in window.ctl.marks() if m.no in (1, 4)]
  _select(dlg, ids)
  assert sorted(dlg.selected_ids()) == sorted(ids)
  monkeypatch.setattr(QMessageBox, "question",
                      lambda *a, **k: QMessageBox.StandardButton.Yes)
  dlg.delete_selected()
  assert len(window.ctl.marks()) == 2 and dlg.table.rowCount() == 2
  window.ctl.undo_stack.undo()
  assert len(window.ctl.marks()) == 4 and dlg.table.rowCount() == 4

  m = next(m for m in window.ctl.marks() if m.no == 2)
  window.ctl.update_marks([m.id], status="ok")
  row = next(r for r in range(dlg.table.rowCount()) if dlg._row_id(r) == m.id)
  assert dlg.table.item(row, 3).text() == "OK"


@pytest.mark.parametrize("all_pages", [False, True])
def test_export_selected(window, qapp, monkeypatch, tmp_path, all_pages):
  from app.ui import output_dialog
  out = tmp_path / ("all.pdf" if all_pages else "sel.pdf")

  def fake_exec(dlg):
    (dlg.all_pages if all_pages else dlg.marked_only).setChecked(True)
    return 1

  monkeypatch.setattr(output_dialog.SelectedExportDialog, "exec", fake_exec)
  monkeypatch.setattr(window, "_ask_save", lambda *a: str(out))
  ids = [m.id for m in window.ctl.marks() if m.no in (2, 4)]
  window.export_selected_marks(ids)
  res = fitz.open(out)
  assert res.page_count == (3 if all_pages else 2)
  toc = res.get_toc(simple=False)
  marks_in_toc = [t[1] for t in toc if t[0] == 2]
  assert len(marks_in_toc) == 2 and marks_in_toc[0].startswith("#2")
  for t in toc:
    if t[0] == 2:
      assert t[3]["zoom"] > 1


def test_bookmark_dest_centers_mark():
  from app.marks.pdf_export import BOOKMARK_VIEW_PX, bookmark_dest
  disp = fitz.Rect(200, 150, 220, 160)
  d = bookmark_dest(disp, 0)
  zoom = d["zoom"]
  vw, vh = BOOKMARK_VIEW_PX[0] / zoom, BOOKMARK_VIEW_PX[1] / zoom
  view = fitz.Rect(d["to"].x, d["to"].y, d["to"].x + vw, d["to"].y + vh)
  assert 1 < zoom <= 8 and view.contains(disp)
  assert view.width >= disp.width * 3


def test_bookmark_on_rotated_page(tmp_path):
  from app.document import DrawingDocument
  from app.marks.pdf_export import save_pdf
  src = fitz.open()
  src.new_page(width=420, height=297).set_rotation(90)
  p = tmp_path / "R.pdf"
  src.save(p)
  drawing = DrawingDocument(p)
  m = Mark(page=0, kind="rect", rect=[300, 40, 340, 60], no=1)
  out = tmp_path / "R_out.pdf"
  save_pdf(drawing, [m], [0], False, out)
  res = fitz.open(out)
  dest = [t for t in res.get_toc(simple=False) if t[0] == 2][0][3]
  disp = (fitz.Rect(m.rect) * res[0].rotation_matrix).normalize()
  assert dest["zoom"] > 1
  assert dest["to"].x <= disp.x0 and dest["to"].y <= disp.y0
