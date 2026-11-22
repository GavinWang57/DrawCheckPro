import pymupdf as fitz
import pytest


def make_drawing_pdf(path, rotate: int = 0):
  """模擬 CAD 匯出：hairline、0.1pt 細線、Form XObject 內的細線、小字。"""
  doc = fitz.open()
  page = doc.new_page(width=420, height=297)
  page.insert_text((20, 40), "R12.5 +0.02/-0.01  (1 w) test", fontsize=5)
  page.insert_text((20, 60), "Ø8 H7", fontsize=4)
  xref = page.get_contents()[0]
  extra = (
    b"\nq 0 G 0 w 20 100 m 400 100 l S Q"
    b"\nq 0 G 0.1 w 20 120 m 400 120 l S Q"
    b"\nq 0.25 0 0 0.25 0 0 cm 0 G 0.4 w 80 560 m 1600 560 l S Q"
    b"\nq 0 g 20 150 100 0.2 re f Q\n"
  )
  doc.update_stream(xref, doc.xref_stream(xref) + extra)

  src = fitz.open()
  sp = src.new_page(width=100, height=50)
  sp.draw_line((5, 25), (95, 25), width=0.05)
  page.show_pdf_page(fitz.Rect(20, 200, 220, 300), src, 0)
  if rotate:
    page.set_rotation(rotate)
  doc.save(path)


@pytest.fixture
def drawing_pdf(tmp_path):
  p = tmp_path / "A001.pdf"
  make_drawing_pdf(p)
  return p
