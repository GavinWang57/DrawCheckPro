import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.marks.model import KIND_STAMP  # noqa: E402


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


def test_edit_text_mark_applies_text_and_size(window, qapp, monkeypatch):
  from app.marks import text_dialog
  v = window.view
  v.create_text_mark(QPointF(150, 150), {"text": "abc", "style": {"font_size": 10.0}})
  m = window.ctl.marks()[0]
  old_w = v.items_by_id[m.id].display_rect().width()

  def fake_exec(dlg):
    dlg.text.setPlainText("hello world")
    dlg.font_size.setCurrentText("20")
    dlg.status_buttons["ng"].click()
    return 1

  monkeypatch.setattr(text_dialog.TextMarkDialog, "exec", fake_exec)
  window.edit_mark(m.id)
  m = window.ctl.get(m.id)
  assert m.text == "hello world" and m.style["font_size"] == 20 and m.status == "ng"
  assert v.items_by_id[m.id].display_rect().width() > old_w
  window.ctl.undo_stack.undo()
  assert window.ctl.get(m.id).text == "abc"


def test_text_dialog_status_buttons_and_mm(qapp):
  from app.marks.text_dialog import MM_PER_PT, TextMarkDialog
  dlg = TextMarkDialog("尺寸", {"font_size": 10}, status="ok", font_unit="mm")
  assert dlg.status() == "ok" and dlg.status_buttons["ok"].isChecked()
  assert dlg.unit() == "mm"
  assert float(dlg.font_size.currentText()) == pytest.approx(10 * MM_PER_PT, abs=0.01)
  dlg.font_size.setCurrentText("3.5")
  assert dlg.values()["style"]["font_size"] == pytest.approx(3.5 / MM_PER_PT, abs=0.01)
  dlg.font_unit.setCurrentIndex(dlg.font_unit.findData("pt"))
  assert float(dlg.font_size.currentText()) == pytest.approx(9.9, abs=0.05)
  dlg.status_buttons["pending"].click()
  assert dlg.status() == "pending"


def _click(view, scene_pt, qapp):
  pos = view.mapFromScene(scene_pt)
  QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
  qapp.processEvents()


def test_stamp_resize_and_size_remembered(window, qapp):
  from app.viewer import page_view as pv
  v = window.view
  v.set_tool(pv.TOOL_OK)
  _click(v, QPointF(100, 100), qapp)
  m = window.ctl.marks()[0]
  assert m.kind == KIND_STAMP
  v.set_tool(pv.TOOL_SELECT)
  item = v.items_by_id[m.id]
  item.setSelected(True)
  r = item.display_rect()
  start = v.mapFromScene(r.bottomRight()) - QPoint(3, 3)
  end = start + QPoint(40, 40)
  vp = v.viewport()
  QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
  QTest.mouseMove(vp, end)
  QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
  qapp.processEvents()
  new = v.mark_display_rect(window.ctl.get(m.id))
  assert new.width() > r.width() * 1.3
  assert new.width() == pytest.approx(new.height())
  assert new.topLeft() == r.topLeft()
  assert v.stamp_size_pt == pytest.approx(new.width(), abs=0.01)
  assert float(window.qs.value("stamp_size_pt")) == pytest.approx(new.width(), abs=0.01)

  v.zoom_by(2.0)
  v.set_tool(pv.TOOL_NG)
  _click(v, QPointF(200, 150), qapp)
  second = [x for x in window.ctl.marks() if x.id != m.id][0]
  assert v.mark_display_rect(second).width() == pytest.approx(new.width(), abs=0.01)


def test_shift_middle_pans(window, qapp):
  v = window.view
  v.set_zoom_percent(800)
  qapp.processEvents()
  h0 = v.horizontalScrollBar().value()
  vp = v.viewport()
  QTest.mousePress(vp, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.ShiftModifier, QPoint(400, 300))
  QTest.mouseMove(vp, QPoint(300, 300))
  QTest.mouseRelease(vp, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.ShiftModifier,
                     QPoint(300, 300))
  assert v.horizontalScrollBar().value() != h0


def test_wheel_direction_setting(window, qapp):
  from PySide6.QtCore import QPointF as P
  from PySide6.QtGui import QWheelEvent
  v = window.view

  def wheel(delta):
    s0 = v.current_scale()
    ev = QWheelEvent(P(300, 300), P(300, 300), QPoint(), QPoint(0, delta),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    v.wheelEvent(ev)
    return v.current_scale() / s0

  assert wheel(120) > 1
  v.wheel_up_zooms_in = False
  assert wheel(120) < 1
  from app.ui.dialogs import SettingsDialog
  dlg = SettingsDialog("", wheel_up_zooms_in=False)
  assert dlg.wheel_up_zooms_in() is False
