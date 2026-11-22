"""文字框的量測與繪製（場景座標單位 = pt）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from app.marks.model import text_style

FONT_FAMILY = "Microsoft JhengHei"
_BASE_PX = 100  # 先用 100px 的字量測/繪製，再縮放到實際 pt，避免小數點字級被取整
_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextExpandTabs


def _font(style: dict) -> QFont:
  f = QFont(FONT_FAMILY)
  f.setPixelSize(_BASE_PX)
  f.setBold(bool(style.get("bold")))
  f.setItalic(bool(style.get("italic")))
  return f


def padding(style: dict) -> float:
  return style["font_size"] * 0.35 + style["border_width"]


def measure(text: str, style: dict | None) -> tuple[float, float]:
  """回傳文字框寬高（pt）。"""
  s = text_style(style)
  fm = QFontMetricsF(_font(s))
  r = fm.boundingRect(QRectF(0, 0, 1e6, 1e6), _FLAGS, text or " ")
  if s["italic"]:
    r.setWidth(r.width() + fm.height() * 0.15)  # 斜體最後一個字會往右傾
  k = s["font_size"] / _BASE_PX
  pad = padding(s)
  return r.width() * k + 2 * pad, r.height() * k + 2 * pad


def color(value: str) -> QColor:
  c = QColor(value)
  return c if c.isValid() else QColor("#000000")


def _decorate(painter: QPainter, fm: QFontMetricsF, text: str, s: dict, pen_color: QColor):
  """底線 / 雙底線 / 刪除線：依每一行的實際寬度畫線（座標為 _BASE_PX 字級的單位）。"""
  underline, strike = s.get("underline", "none"), bool(s.get("strike"))
  if underline == "none" and not strike:
    return
  thick = max(fm.lineWidth(), _BASE_PX * 0.05)
  painter.setPen(QPen(pen_color, thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
  for i, line in enumerate(text.split("\n")):
    w = fm.horizontalAdvance(line)
    if w <= 0:
      continue
    base = i * fm.lineSpacing() + fm.ascent()
    ys = []
    if underline in ("single", "double"):
      ys.append(base + max(fm.underlinePos(), thick * 1.2))
    if underline == "double":
      ys.append(ys[0] + thick * 2.2)
    if strike:
      ys.append(base - fm.strikeOutPos())
    for y in ys:
      painter.drawLine(QPointF(0, y), QPointF(w, y))


def paint(painter: QPainter, rect: QRectF, text: str, style: dict | None):
  s = text_style(style)
  bw = s["border_width"]
  painter.save()
  painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
  painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
  pen = QPen(color(s["border_color"]), bw) if bw > 0 else QPen(Qt.PenStyle.NoPen)
  painter.setPen(pen)
  painter.setBrush(color(s["fill_color"]))
  painter.drawRect(rect.adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2))
  pad = padding(s)
  k = s["font_size"] / _BASE_PX
  painter.translate(rect.left() + pad, rect.top() + pad)
  painter.scale(k, k)
  font = _font(s)
  painter.setFont(font)
  text_color = color(s["text_color"])
  painter.setPen(text_color)
  inner = QRectF(0, 0, (rect.width() - 2 * pad) / k, (rect.height() - 2 * pad) / k)
  painter.drawText(inner, _FLAGS, text)
  _decorate(painter, QFontMetricsF(font), text, s, text_color)
  painter.restore()
