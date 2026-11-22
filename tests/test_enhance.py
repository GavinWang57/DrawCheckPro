import numpy as np
import pymupdf as fitz

from app.document import MODE_OFF, MODE_RASTER, MODE_VECTOR, DrawingDocument, file_sha256
from app.enhance import raster_enhance as rx
from app.enhance.vector_enhance import VectorParams, iter_ops, rewrite_stream


def dark_pixels(img: np.ndarray) -> int:
  return int((img.min(axis=2) < 128).sum())


def test_lexer_keeps_strings_and_inline_images():
  data = b"BT /F1 5 Tf (1 w \\) S) Tj ET BI /W 1 /H 1 ID \x00w S EI 0.3 w"
  ops = [op for op, _ in iter_ops(data)]
  assert ops == [b"BT", b"Tf", b"Tj", b"ET", b"BI", b"w"]


def test_rewrite_passes_inline_image_through_once():
  img = b"BI /W 1 /H 1 /CS /G /BPC 8 ID \x80 EI"
  out = rewrite_stream(b"q " + img + b" Q 0 0 m 1 1 l S", VectorParams())
  assert out.count(b"BI") == 1 and img in out
  assert [op for op, _ in iter_ops(out)].count(b"S") == 1


def test_rewrite_tolerates_color_ops_inside_path():
  """CATIA 會把顏色設定放在路徑與 S 之間。"""
  out = rewrite_stream(b"0 0 m 10 0 l 0 0 0 RG 0 0 0 rg S", VectorParams(min_line_pt=0.5))
  ops = [op for op, _ in iter_ops(out)]
  assert ops.index(b"l") < ops.index(b"S") and b"S" in ops


def test_rewrite_enforces_min_width_with_ctm():
  out = rewrite_stream(b"0.25 0 0 0.25 0 0 cm 0 w 0 0 m 10 0 l S",
                       VectorParams(line_mult=1.0, min_line_pt=0.5, text_stroke_pt=0))
  assert b"2 w\n0 0 m" in out


def test_rewrite_text_state_restored_after_block():
  out = rewrite_stream(b"BT /F1 5 Tf 1 0 0 rg (A) Tj ET BT (B) Tj ET",
                       VectorParams(text_stroke_pt=0.1))
  assert out.count(b"q") == 2 and out.count(b"Q") == 2
  second = out.split(b"ET", 1)[1]
  assert b"/F1 5 Tf" in second.split(b"BT")[0]
  assert b"1 0 0 RG" in second


def test_rewrite_keeps_clip_paths_untouched():
  out = rewrite_stream(b"0 0 10 10 re W n 0 g 0 0 5 5 re f",
                       VectorParams(fill_stroke_pt=0.1))
  assert b"re\nW\nn" in out
  assert b"B\nQ" in out


def test_vector_mode_thickens(drawing_pdf):
  doc = DrawingDocument(drawing_pdf)
  doc.set_settings(doc.settings.with_(mode=MODE_OFF))
  off, _ = doc.render(0, 2.0)
  doc.set_settings(doc.settings.with_(mode=MODE_VECTOR, gamma=1.0, min_line_px=0))
  on, _ = doc.render(0, 2.0)
  assert on.shape == off.shape
  assert dark_pixels(on) > dark_pixels(off) * 1.5


def test_raster_mode_thickens_and_tiles_align(drawing_pdf):
  doc = DrawingDocument(drawing_pdf)
  doc.set_settings(doc.settings.with_(mode=MODE_RASTER, raster_radius=1, gamma=1.0))
  full, rect = doc.render(0, 2.0)
  tile, trect = doc.render(0, 2.0, fitz.Rect(0, 80, 210, 160))
  y0, x0 = trect.y0 - rect.y0, trect.x0 - rect.x0
  assert np.array_equal(full[y0:y0 + tile.shape[0], x0:x0 + tile.shape[1]], tile)


def test_original_file_untouched(drawing_pdf):
  before = file_sha256(drawing_pdf)
  doc = DrawingDocument(drawing_pdf)
  doc.render(0, 1.0)
  doc.close()
  assert file_sha256(drawing_pdf) == before


def test_rotated_page_renders_rotated(tmp_path):
  from tests.conftest import make_drawing_pdf
  p = tmp_path / "rot.pdf"
  make_drawing_pdf(p, rotate=90)
  doc = DrawingDocument(p)
  img, _ = doc.render(0, 1.0)
  assert img.shape[0] > img.shape[1]


def test_invert_lightness_keeps_hue():
  img = np.array([[[255, 255, 255], [0, 0, 0], [255, 0, 0]]], dtype=np.uint8)
  out = rx.invert_lightness(img)
  assert out[0, 0].tolist() == [0, 0, 0]
  assert out[0, 1].tolist() == [255, 255, 255]
  assert out[0, 2].tolist() == [255, 0, 0]
