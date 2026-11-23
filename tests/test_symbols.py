import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as fitz  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.marks.model import Mark  # noqa: E402
from app.marks.symbols import SYMBOL_GROUPS  # noqa: E402

ALL_SYMBOLS = "".join(sym for _g, items in SYMBOL_GROUPS for sym, _n in items)
needs_symbol_font = pytest.mark.skipif(
  not os.path.exists(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguisym.ttf")),
  reason="需要 Windows 的 Segoe UI Symbol")


@pytest.fixture(scope="module")
def qapp():
  return QApplication.instance() or QApplication([])


@needs_symbol_font
def test_text_runs_use_symbol_font_only_for_missing_glyphs():
  from app.marks.pdf_export import text_runs
  runs = text_runs("Ø8 H7 ⌖0.05Ⓜ 平面度⏥", bold=False)
  fonts = [spec[0] for _t, spec in runs]
  text = {t: spec[0] for t, spec in runs}
  assert "".join(t for t, _s in runs) == "Ø8 H7 ⌖0.05Ⓜ 平面度⏥"
  assert text["Ø8 H7 "] == "msjh"
  assert text["⌖"] == "seguisym" and text["Ⓜ"] == "seguisym" and text["⏥"] == "seguisym"
  assert fonts.count("seguisym") == 3


@needs_symbol_font
@pytest.mark.parametrize("rotate", [0, 90])
def test_pdf_export_keeps_all_symbols(tmp_path, rotate):
  from app.document import DrawingDocument
  from app.marks.pdf_export import save_pdf
  src = fitz.open()
  page = src.new_page(width=842, height=595)
  if rotate:
    page.set_rotation(rotate)
  p = tmp_path / "S.pdf"
  src.save(p)
  half = len(ALL_SYMBOLS) // 2
  text = f"{ALL_SYMBOLS[:half]}\n{ALL_SYMBOLS[half:]}"
  m = Mark(page=0, kind="text", rect=[40, 40, 600, 120], text=text, no=1,
           style={"font_size": 14, "italic": True})
  out = tmp_path / "S_out.pdf"
  save_pdf(DrawingDocument(p), [m], [0], False, out)
  res = fitz.open(out)
  got = res[0].get_text().replace("\n", "").replace(" ", "")
  for ch in ALL_SYMBOLS:
    assert ch in got, f"PDF 中缺少 {ch!r}"
  names = " ".join(f[3] for f in res[0].get_fonts())
  assert "Symbol" in names or "seguisym" in names.lower()


@needs_symbol_font
def test_screen_font_covers_symbols(qapp):
  from PySide6.QtGui import QFontMetricsF
  from app.marks.text_layout import _font
  fm = QFontMetricsF(_font({"bold": False, "italic": False}))
  for ch in ALL_SYMBOLS:
    assert fm.horizontalAdvance(ch) > 0


def test_dialog_symbol_buttons_insert_at_cursor(qapp):
  from app.marks.text_dialog import TextMarkDialog
  dlg = TextMarkDialog("8 H7")
  cur = dlg.text.textCursor()
  cur.setPosition(0)
  dlg.text.setTextCursor(cur)
  dlg.symbol_buttons["Ø"].click()
  dlg.text.moveCursor(dlg.text.textCursor().MoveOperation.End)
  dlg.symbol_buttons["⌖"].click()
  assert dlg.values()["text"] == "Ø8 H7⌖"
  assert len(dlg.symbol_buttons) == len(ALL_SYMBOLS) - 2  # SØ、SR 各是兩個字元
