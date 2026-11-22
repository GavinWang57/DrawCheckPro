import numpy as np
import pymupdf as fitz
import pytest

from app.document import DrawingDocument, file_sha256
from app.marks.model import (KIND_ELLIPSE, KIND_RECT, KIND_STAMP, KIND_TEXT, STATUS_NG,
                             STATUS_OK, Mark)
from app.marks.pdf_export import render_images, save_pdf, stitch_vertical
from tests.conftest import make_drawing_pdf


def three_page_pdf(tmp_path, rotate=0):
  single = tmp_path / "single.pdf"
  make_drawing_pdf(single, rotate=rotate)
  src = fitz.open(single)
  doc = fitz.open()
  for _ in range(3):
    doc.insert_pdf(src)
  path = tmp_path / "multi.pdf"
  doc.save(path)
  return path


def sample_marks():
  return [
    Mark(page=0, kind=KIND_STAMP, rect=[300, 30, 312, 42], status=STATUS_OK, no=1),
    Mark(page=0, kind=KIND_RECT, rect=[18, 33, 130, 43], status=STATUS_NG, no=2, note="偏大"),
    Mark(page=2, kind=KIND_ELLIPSE, rect=[16, 52, 46, 64], no=3),
    Mark(page=2, kind=KIND_TEXT, rect=[200, 150, 330, 175], no=4, text="請確認公差",
         link="https://example.com/spec"),
  ]


def test_all_pages_pdf_has_marks_bookmarks_links(tmp_path):
  path = three_page_pdf(tmp_path)
  before = file_sha256(path)
  doc = DrawingDocument(path)
  out = tmp_path / "out.pdf"
  save_pdf(doc, sample_marks(), [0, 1, 2], enhanced=False, out_path=out)
  res = fitz.open(out)
  assert res.page_count == 3
  toc = res.get_toc()
  assert [t[:3] for t in toc if t[0] == 1] == [[1, "第 1 頁（2 個標記）", 1],
                                                [1, "第 3 頁（2 個標記）", 3]]
  assert any("請確認公差" in t[1] for t in toc)
  assert "請確認公差" in res[2].get_text()
  assert [l["uri"] for l in res[2].get_links()] == ["https://example.com/spec"]
  assert len(res[0].get_drawings()) > len(fitz.open(path)[0].get_drawings())
  assert file_sha256(path) == before


def test_single_page_pdf_keeps_only_that_page(tmp_path):
  path = three_page_pdf(tmp_path)
  doc = DrawingDocument(path)
  out = tmp_path / "p3.pdf"
  save_pdf(doc, sample_marks(), [2], enhanced=True, out_path=out)
  res = fitz.open(out)
  assert res.page_count == 1
  assert res.get_toc()[0][:3] == [1, "第 3 頁（2 個標記）", 1]


def test_refuses_to_overwrite_original(tmp_path):
  path = three_page_pdf(tmp_path)
  with pytest.raises(ValueError):
    save_pdf(DrawingDocument(path), [], [0], False, path)


def test_rotated_page_link_matches_mark(tmp_path):
  path = three_page_pdf(tmp_path, rotate=90)
  doc = DrawingDocument(path)
  m = Mark(page=0, kind=KIND_TEXT, rect=[20, 40, 60, 160], text="A", link="https://x.y", no=1)
  out = tmp_path / "rot.pdf"
  save_pdf(doc, [m], [0], False, out)
  res = fitz.open(out)
  page = res[0]
  annot_xref = int(res.xref_get_key(page.xref, "Annots")[1].strip("[]").split()[0])
  raw = [float(v) for v in res.xref_get_key(annot_xref, "Rect")[1].strip("[]").split()]
  h = page.mediabox.height
  x0, y0, x1, y1 = m.rect
  assert raw == pytest.approx([x0, h - y1, x1, h - y0], abs=0.5)


def test_png_render_and_stitch(tmp_path):
  path = three_page_pdf(tmp_path)
  doc = DrawingDocument(path)
  imgs = render_images(doc, sample_marks(), [0, 1, 2], False, dpi=72)
  assert len(imgs) == 3
  plain = render_images(doc, [], [0], False, dpi=72)[0]
  assert (imgs[0] != plain).any()
  big = stitch_vertical(imgs, gap=10)
  assert big.shape[0] == sum(i.shape[0] for i in imgs) + 20
  assert np.array_equal(big[:imgs[0].shape[0], :imgs[0].shape[1]], imgs[0])
