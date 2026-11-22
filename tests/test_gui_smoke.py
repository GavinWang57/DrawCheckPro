import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.document import file_sha256  # noqa: E402
from app.marks.model import KIND_RECT, STATUS_OK  # noqa: E402
from app.marks.store import load_marks, sidecar_path  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
  return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
  from PySide6.QtCore import QSettings
  QSettings.setDefaultFormat(QSettings.Format.IniFormat)
  QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "cfg"))
  from app.main_window import MainWindow
  w = MainWindow()
  w.resize(1200, 800)
  w.show()
  yield w
  w.ctl.set_dirty(False)
  w.close()


def _pump(qapp, n=20):
  for _ in range(n):
    qapp.processEvents()


def test_open_mark_save_reopen(window, qapp, drawing_pdf, tmp_path):
  sha = file_sha256(drawing_pdf)
  window.open_pdf(str(drawing_pdf))
  _pump(qapp)
  view = window.view
  assert view.page_item is not None

  view._create_mark(KIND_RECT, "pending", QRectF(20, 30, 80, 15))
  ids = view.selected_ids()
  assert len(ids) == 1
  window.set_selected_status(STATUS_OK)
  assert window.marks_panel.table.rowCount() == 1

  view.zoom_by(4)
  _pump(qapp, 50)
  assert view.cache.used > 0

  window.enhance_panel.toggle_dark()
  _pump(qapp, 20)
  view.grab().save(str(tmp_path / "shot.png"))

  assert window.save_marks()
  res = load_marks(drawing_pdf, sha)
  assert len(res.marks) == 1 and res.marks[0].status == STATUS_OK
  assert file_sha256(drawing_pdf) == sha
  assert sidecar_path(drawing_pdf).exists()

  window.open_pdf(str(drawing_pdf))
  _pump(qapp)
  assert len(view.items_by_id) == 1
  item = next(iter(view.items_by_id.values()))
  r = item.display_rect()
  assert abs(r.left() - 20) < 0.01 and abs(r.width() - 80) < 0.01


def test_rotated_page_mark_coords(window, qapp, tmp_path):
  from tests.conftest import make_drawing_pdf
  p = tmp_path / "rot.pdf"
  make_drawing_pdf(p, rotate=90)
  window.open_pdf(str(p))
  _pump(qapp)
  view = window.view
  disp = QRectF(10, 50, 40, 20)
  view._create_mark(KIND_RECT, "pending", disp)
  m = window.ctl.marks()[0]
  back = view.mark_display_rect(m)
  assert abs(back.left() - 10) < 0.01 and abs(back.top() - 50) < 0.01
  assert abs(back.width() - 40) < 0.01 and abs(back.height() - 20) < 0.01
  assert m.rect != [10, 50, 50, 70]
