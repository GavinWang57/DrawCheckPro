import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QRect, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.marks.model import KIND_TEXT  # noqa: E402


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


def test_text_dialog_controls(qapp):
  from app.marks.text_dialog import TextMarkDialog
  dlg = TextMarkDialog("尺寸", {"font_size": 10, "border_width": 0.8})
  assert dlg.font_size.isEditable()
  dlg.font_size.setCurrentText("13.5")
  dlg.fill_clear.setChecked(True)
  dlg.border_width.setCurrentIndex(dlg.border_width.findData(3.0))
  before = dlg.render_preview().toImage()
  dlg.border_color.set_value("#ff00a000")
  after = dlg.render_preview().toImage()
  assert before != after, "換框線顏色後預覽應該改變"
  st = dlg.values()["style"]
  assert st["font_size"] == 13.5
  assert QColor(st["fill_color"]).alpha() == 0
  assert st["border_width"] == 3.0 and st["border_color"] == "#ff00a000"
  assert not dlg.fill_color.isEnabled()


def test_hover_toolbar_and_duplicate(window, qapp):
  v = window.view
  v.create_text_mark(QPointF(150, 150), {"text": "量測點", "link": "https://a.b",
                                         "style": {"font_size": 10.0}})
  m = window.ctl.marks()[0]
  v.scene().clearSelection()
  center = v.mapFromScene(v.mark_display_rect(m).center())
  QTest.mouseMove(v.viewport(), center)
  qapp.processEvents()
  bar = v.hover_bar
  assert bar.isVisible() and bar.mark_id == m.id
  assert bar.btn_link.isVisible()

  bar.btn_copy.click()
  marks = window.ctl.marks()
  assert len(marks) == 2
  copy = next(x for x in marks if x.id != m.id)
  assert copy.kind == KIND_TEXT and copy.text == m.text and copy.style == m.style
  assert copy.rect != m.rect

  QTest.mouseMove(v.viewport(), v.mapFromScene(v.mark_display_rect(copy).center()))
  qapp.processEvents()
  v.hover_bar.btn_delete.click()
  assert window.ctl.get(copy.id) is None


def test_snapshot_overlay_flow(window, qapp):
  from app.viewer import page_view as pv
  window.tool_actions[pv.TOOL_SNAP].trigger()
  ov = window.view.snap_overlay
  assert ov.isVisible() and not ov.frame.isEmpty()
  assert ov.bar.isVisible()

  start = ov.frame.center()
  QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=start)
  QTest.mouseMove(ov, start + QPoint(30, 20))
  QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=start + QPoint(30, 20))
  moved = QRect(ov.frame)
  assert moved.center().x() > start.x() + 20

  br = moved.bottomRight()
  QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=br)
  QTest.mouseMove(ov, br - QPoint(50, 40))
  QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=br - QPoint(50, 40))
  assert ov.frame.width() < moved.width() and ov.frame.height() < moved.height()

  QGuiApplication.clipboard().clear()
  ov._confirm("copy")
  qapp.processEvents()
  img = QGuiApplication.clipboard().image()
  assert not img.isNull() and img.width() > ov.frame.width()
  assert not ov.isVisible()
  assert window.view.tool == pv.TOOL_SELECT
  assert window.tool_actions[pv.TOOL_SELECT].isChecked()


def test_snapshot_cancel_returns_to_select(window, qapp):
  from app.viewer import page_view as pv
  window.tool_actions[pv.TOOL_SNAP].trigger()
  QTest.keyClick(window.view.snap_overlay, Qt.Key.Key_Escape)
  assert not window.view.snap_overlay.isVisible()
  assert window.view.tool == pv.TOOL_SELECT
