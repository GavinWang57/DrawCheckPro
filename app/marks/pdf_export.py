"""把標記畫進 PDF 副本（向量），並產生書籤與連結；也可輸出 PNG。原始 PDF 不會被修改。"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pymupdf as fitz

from app.document import DrawingDocument
from app.marks.model import (KIND_ELLIPSE, KIND_LABELS, KIND_STAMP, KIND_TEXT, STATUS_COLORS,
                             STATUS_PENDING,
                             STATUS_LABELS, STATUS_NG, STATUS_NONE, STATUS_OK, Mark, parse_color,
                             text_style)

FALLBACK_FONT = "china-t"  # PyMuPDF 內建；缺少 Ø 等符號，英數為全形寬度，只在找不到系統字型時使用
_FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
SYSTEM_FONTS = {False: ("msjh", _FONTS_DIR / "msjh.ttc"), True: ("msjhbd", _FONTS_DIR / "msjhbd.ttc")}
LABEL_FONT_PT = 6.0
STITCH_GAP_PX = 24
MAX_STITCH_PIXELS = 400_000_000  # 約 1.2GB RGB；超過就拒絕，避免記憶體爆掉


def _hex_rgb(hex_color: str) -> tuple[float, float, float]:
  return parse_color(hex_color)[0]


def _draw_stamp(page: fitz.Page, r: fitz.Rect, status: str):
  col = _hex_rgb(STATUS_COLORS[status])
  w = r.width
  c = fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
  shape = page.new_shape()
  shape.draw_circle(c, w * 0.46)
  shape.finish(color=col, fill=col, fill_opacity=0.16, width=w * 0.07)
  x, y = r.x0, r.y0

  def pt(fx, fy):
    return fitz.Point(x + w * fx, y + r.height * fy)

  if status == STATUS_OK:
    shape.draw_polyline([pt(0.24, 0.52), pt(0.43, 0.70), pt(0.76, 0.32)])
  elif status == STATUS_NG:
    shape.draw_line(pt(0.30, 0.30), pt(0.70, 0.70))
    shape.draw_line(pt(0.70, 0.30), pt(0.30, 0.70))
  elif status != STATUS_NONE:
    shape.draw_bezier(pt(0.34, 0.36), pt(0.34, 0.18), pt(0.68, 0.18), pt(0.66, 0.38))
    shape.draw_bezier(pt(0.66, 0.38), pt(0.64, 0.50), pt(0.50, 0.50), pt(0.50, 0.62))
  if status != STATUS_NONE:
    shape.finish(color=col, width=w * 0.10, lineCap=1, lineJoin=1, closePath=False)
  if status == STATUS_PENDING:
    shape.draw_circle(pt(0.50, 0.77), w * 0.035)
    shape.finish(color=col, fill=col)
  shape.commit()


def _draw_box(page: fitz.Page, r: fitz.Rect, status: str, ellipse: bool):
  col = _hex_rgb(STATUS_COLORS[status])
  if ellipse:
    page.draw_oval(r, color=col, fill=col, fill_opacity=0.11, width=1.2)
  else:
    page.draw_rect(r, color=col, fill=col, fill_opacity=0.11, width=1.2)


def _draw_text(page: fitz.Page, r: fitz.Rect, m: Mark):
  s = text_style(m.style)
  fill, fill_a = parse_color(s["fill_color"])
  border, border_a = parse_color(s["border_color"])
  bw = s["border_width"]
  if fill_a > 0 or bw > 0:
    page.draw_rect(r, color=border if bw > 0 else None, fill=fill if fill_a > 0 else None,
                   fill_opacity=fill_a, stroke_opacity=border_a, width=bw if bw > 0 else 0)
  _draw_text_lines(page, r, m.text, s)
  if m.status != STATUS_NONE:
    _draw_status_badge(page, r, s["font_size"], m.status)
  if m.link:
    _add_link(page, r, m.link)


def _draw_status_badge(page: fitz.Page, r: fitz.Rect, font_size: float, status: str):
  """與畫面相同：圓心落在文字框右下角（顯示方向）。"""
  disp = (r * page.rotation_matrix).normalize()
  d = max(font_size * 1.05, 3.0)
  x0, y0 = disp.x1 - d * 0.6, disp.y1 - d * 0.6
  derot = page.derotation_matrix

  def pt(fx, fy):
    return fitz.Point(x0 + d * fx, y0 + d * fy) * derot

  white = (1, 1, 1)
  col = _hex_rgb(STATUS_COLORS[status])
  shape = page.new_shape()
  shape.draw_circle(pt(0.5, 0.5), d / 2)
  shape.finish(color=white, fill=col, width=d * 0.08)
  if status == STATUS_OK:
    shape.draw_polyline([pt(0.24, 0.52), pt(0.43, 0.70), pt(0.76, 0.32)])
  elif status == STATUS_NG:
    shape.draw_line(pt(0.30, 0.30), pt(0.70, 0.70))
    shape.draw_line(pt(0.70, 0.30), pt(0.30, 0.70))
  else:
    shape.draw_bezier(pt(0.34, 0.36), pt(0.34, 0.18), pt(0.68, 0.18), pt(0.66, 0.38))
    shape.draw_bezier(pt(0.66, 0.38), pt(0.64, 0.50), pt(0.50, 0.50), pt(0.50, 0.62))
  shape.finish(color=white, width=d * 0.13, lineCap=1, lineJoin=1, closePath=False)
  if status not in (STATUS_OK, STATUS_NG):
    shape.draw_circle(pt(0.50, 0.77), d * 0.05)
    shape.finish(color=white, fill=white)
  shape.commit()


_font_cache: dict[str, fitz.Font] = {}


def _font_for(bold: bool) -> tuple[str, str | None, fitz.Font]:
  """(資源名稱, 字型檔路徑, 量測用 Font)。優先用微軟正黑體（與畫面一致），找不到時用內建字型。"""
  name, path = SYSTEM_FONTS[bold]
  if not path.exists():
    name, path = SYSTEM_FONTS[False]
  if path.exists():
    key, fontfile = str(path), str(path)
  else:
    name, key, fontfile = FALLBACK_FONT, FALLBACK_FONT, None
  if key not in _font_cache:
    _font_cache[key] = fitz.Font(fontfile=fontfile) if fontfile else fitz.Font(FALLBACK_FONT)
  return name, fontfile, _font_cache[key]


ITALIC_SHEAR = 0.2  # 正值＝往右傾的一般斜體（已用實際輸出驗證方向）


def _draw_text_lines(page: fitz.Page, r: fitz.Rect, text: str, s: dict):
  """逐行寫入文字並自行畫底線 / 雙底線 / 刪除線。

  先在「顯示座標」（使用者看到的方向）排版，再換算回未旋轉座標；insert_text 以
  rotate=頁面旋轉 讓文字在旋轉頁面上也正著顯示。斜體以 morph 在顯示方向傾斜。
  """
  fontname, fontfile, font = _font_for(bool(s["bold"]))
  text_rgb, text_a = parse_color(s["text_color"])
  disp = (r * page.rotation_matrix).normalize()
  derot = page.derotation_matrix
  rot_l = fitz.Matrix(page.rotation_matrix)
  rot_l.e = rot_l.f = 0
  derot_l = fitz.Matrix(derot)
  derot_l.e = derot_l.f = 0
  italic = bool(s.get("italic"))
  shear = rot_l * fitz.Matrix(1, 0, ITALIC_SHEAR, 1, 0, 0) * derot_l

  pad = s["font_size"] * 0.35 + s["border_width"]
  lines = text.split("\n")
  size = s["font_size"]
  widest = max((font.text_length(line, size) for line in lines), default=0)
  if italic:
    widest += size * 0.15
  room = disp.width - 2 * pad
  if widest > room > 0:
    size *= room / widest  # 字寬和畫面量測略有差異時縮小，避免超出框線
  line_h = size * (font.ascender - font.descender)
  thick = max(size * 0.06, 0.3)

  for i, line in enumerate(lines):
    base = fitz.Point(disp.x0 + pad, disp.y0 + pad + font.ascender * size + i * line_h)
    origin = base * derot
    if line:
      page.insert_text(origin, line, fontsize=size, fontname=fontname, fontfile=fontfile,
                       color=text_rgb, fill_opacity=text_a, rotate=page.rotation,
                       morph=(origin, shear) if italic else None, overlay=True)
    width = font.text_length(line, size)
    if width <= 0:
      continue
    offsets = []
    if s.get("underline") in ("single", "double"):
      offsets.append(size * 0.12)
    if s.get("underline") == "double":
      offsets.append(size * 0.12 + thick * 2.2)
    if s.get("strike"):
      offsets.append(-size * 0.3)
    for dy in offsets:
      a, b = fitz.Point(base.x, base.y + dy), fitz.Point(base.x + width, base.y + dy)
      page.draw_line(a * derot, b * derot, color=text_rgb, stroke_opacity=text_a, width=thick)


def _add_link(page: fitz.Page, r: fitz.Rect, link: str):
  # insert_link 的 from 使用未旋轉座標（已用 PDF 內實際的 /Rect 驗證）
  if link.lower().startswith(("http://", "https://", "mailto:", "file:")):
    page.insert_link({"kind": fitz.LINK_URI, "from": r, "uri": link})
  else:
    page.insert_link({"kind": fitz.LINK_LAUNCH, "from": r, "file": link})


def _draw_label(page: fitz.Page, r: fitz.Rect, m: Mark):
  col = _hex_rgb(STATUS_COLORS[m.status])
  disp = (r * page.rotation_matrix).normalize()
  if m.kind == KIND_STAMP:
    anchor = fitz.Point(disp.x1 + 1, disp.y0 + LABEL_FONT_PT)
  else:
    anchor = fitz.Point(disp.x0, disp.y0 - 1.5)
  p = anchor * page.derotation_matrix
  page.insert_text(p, f"#{m.no}", fontsize=LABEL_FONT_PT, fontname="helv", color=col,
                   rotate=page.rotation, overlay=True)


def draw_marks(page: fitz.Page, marks: list[Mark]):
  for m in sorted(marks, key=lambda m: m.no):
    r = fitz.Rect(m.rect)
    if m.kind == KIND_STAMP:
      _draw_stamp(page, r, m.status)
    elif m.kind == KIND_TEXT:
      _draw_text(page, r, m)
    else:
      _draw_box(page, r, m.status, ellipse=m.kind == KIND_ELLIPSE)
    _draw_label(page, r, m)


def bookmark_title(m: Mark) -> str:
  status = "" if m.status == STATUS_NONE else f" {STATUS_LABELS[m.status]}"
  title = f"#{m.no}{status} {KIND_LABELS.get(m.kind, '')}"
  s = m.summary()
  return f"{title}：{s[:60]}" if s else title


def build_toc(doc: fitz.Document, marks: list[Mark], page_map: dict[int, int]) -> list:
  """page_map：原始頁碼 → 輸出文件頁碼（0 起算）。"""
  toc = []
  for src in sorted(page_map):
    on_page = sorted((m for m in marks if m.page == src), key=lambda m: m.no)
    if not on_page:
      continue
    out = page_map[src]
    toc.append([1, f"第 {src + 1} 頁（{len(on_page)} 個標記）", out + 1])
    page = doc[out]
    for m in on_page:
      disp = (fitz.Rect(m.rect) * page.rotation_matrix).normalize()
      toc.append([2, bookmark_title(m), out + 1,
                  {"kind": fitz.LINK_GOTO, "page": out, "to": fitz.Point(disp.x0, disp.y0),
                   "zoom": 0}])
  return toc


def build_marked_document(drawing: DrawingDocument, marks: list[Mark], pages: list[int],
                          enhanced: bool) -> fitz.Document:
  doc = drawing.fresh_copy(enhanced)
  for pno in pages:
    draw_marks(doc[pno], [m for m in marks if m.page == pno])
  if len(pages) != doc.page_count:
    doc.select(pages)
  page_map = {src: i for i, src in enumerate(pages)}
  doc.set_toc(build_toc(doc, marks, page_map))
  return doc


def save_pdf(drawing: DrawingDocument, marks: list[Mark], pages: list[int], enhanced: bool,
             out_path: str | Path):
  if Path(out_path).resolve() == drawing.path.resolve():
    raise ValueError("不能覆蓋原始圖面，請換一個檔名。")
  doc = build_marked_document(drawing, marks, pages, enhanced)
  if any(m.kind == KIND_TEXT and m.page in pages for m in marks):
    try:
      doc.subset_fonts()  # 只保留用到的字，否則嵌入完整的中文字型會多出 20MB 以上
    except Exception:
      pass
  tmp = f"{out_path}.tmp"
  doc.save(tmp, garbage=3, deflate=True)
  doc.close()
  os.replace(tmp, out_path)


def _page_image(page: fitz.Page, dpi: int) -> np.ndarray:
  pix = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
  a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
  return a.reshape(pix.height, pix.width, 3)


def render_images(drawing: DrawingDocument, marks: list[Mark], pages: list[int], enhanced: bool,
                  dpi: int) -> list[np.ndarray]:
  doc = build_marked_document(drawing, marks, pages, enhanced)
  try:
    return [_page_image(p, dpi).copy() for p in doc]
  finally:
    doc.close()


def stitch_vertical(images: list[np.ndarray], gap: int = STITCH_GAP_PX) -> np.ndarray:
  w = max(i.shape[1] for i in images)
  h = sum(i.shape[0] for i in images) + gap * (len(images) - 1)
  if w * h > MAX_STITCH_PIXELS:
    raise ValueError(f"合併後的圖片太大（{w}×{h}），請降低解析度或改存成多個檔案。")
  out = np.full((h, w, 3), 255, np.uint8)
  y = 0
  for img in images:
    x = (w - img.shape[1]) // 2
    out[y:y + img.shape[0], x:x + img.shape[1]] = img
    y += img.shape[0] + gap
  return out


def save_png(img: np.ndarray, out_path: str | Path):
  img = np.ascontiguousarray(img)
  pix = fitz.Pixmap(fitz.csRGB, img.shape[1], img.shape[0], img.tobytes(), False)
  pix.set_dpi(150, 150)
  pix.save(str(out_path))


def estimate_pixels(drawing: DrawingDocument, pages: list[int], dpi: int) -> int:
  total = 0
  for p in pages:
    r = drawing.page_rect(p)
    total += math.ceil(r.width / 72 * dpi) * math.ceil(r.height / 72 * dpi)
  return total
