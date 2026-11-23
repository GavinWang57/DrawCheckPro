"""標記的 QGraphicsItem。座標為顯示座標（已旋轉）；與 Mark.rect（未旋轉）之間由 view 換算。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSimpleTextItem

from app.marks import text_layout
from app.marks.model import (KIND_ELLIPSE, KIND_STAMP, KIND_TEXT, STATUS_COLORS, STATUS_NG,
                             STATUS_NONE, STATUS_OK, STATUS_PENDING, Mark, text_style)

SELECT_COLOR = QColor("#2f7df6")
HANDLE_PX = 9  # 縮放把手的螢幕像素大小


def _symbol_path(status: str, r: QRectF) -> QPainterPath:
  p = QPainterPath()
  w, h = r.width(), r.height()
  x, y = r.left(), r.top()
  if status == STATUS_OK:
    p.moveTo(x + w * 0.24, y + h * 0.52)
    p.lineTo(x + w * 0.43, y + h * 0.70)
    p.lineTo(x + w * 0.76, y + h * 0.32)
  elif status == STATUS_NG:
    p.moveTo(x + w * 0.30, y + h * 0.30)
    p.lineTo(x + w * 0.70, y + h * 0.70)
    p.moveTo(x + w * 0.70, y + h * 0.30)
    p.lineTo(x + w * 0.30, y + h * 0.70)
  elif status == STATUS_PENDING:
    p.moveTo(x + w * 0.34, y + h * 0.36)
    p.cubicTo(x + w * 0.34, y + h * 0.18, x + w * 0.68, y + h * 0.18, x + w * 0.66, y + h * 0.38)
    p.cubicTo(x + w * 0.64, y + h * 0.50, x + w * 0.50, y + h * 0.50, x + w * 0.50, y + h * 0.62)
    p.addEllipse(QPointF(x + w * 0.50, y + h * 0.77), w * 0.025, h * 0.025)
  return p


def status_badge_rect(box: QRectF, style: dict | None) -> QRectF:
  """文字框右下角的狀態徽章：圓心落在框的右下角，直徑約為字級。"""
  d = max(text_style(style)["font_size"] * 1.05, 3.0)
  return QRectF(box.right() - d * 0.6, box.bottom() - d * 0.6, d, d)


def paint_status_badge(painter, badge: QRectF, status: str):
  painter.save()
  painter.setRenderHint(painter.RenderHint.Antialiasing, True)
  d = badge.width()
  painter.setPen(QPen(QColor("white"), d * 0.08))
  painter.setBrush(QColor(STATUS_COLORS[status]))
  painter.drawEllipse(badge)
  pen = QPen(QColor("white"), d * 0.13, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
             Qt.PenJoinStyle.RoundJoin)
  painter.setPen(pen)
  painter.setBrush(Qt.BrushStyle.NoBrush)
  painter.drawPath(_symbol_path(status, badge))
  painter.restore()


class MarkItem(QGraphicsItem):
  def __init__(self, mark: Mark, display_rect: QRectF):
    super().__init__()
    self.mark_id = mark.id
    self._mark = mark
    self._size = QRectF()
    self.setFlags(
      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    )
    self.setAcceptHoverEvents(True)
    self.setCursor(Qt.CursorShape.SizeAllCursor)
    self.setZValue(10)
    self._label = QGraphicsSimpleTextItem(self)
    self._label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    f = QFont()
    f.setPixelSize(12)
    f.setBold(True)
    self._label.setFont(f)
    self.sync(mark, display_rect)

  def sync(self, mark: Mark, display_rect: QRectF):
    self.prepareGeometryChange()
    self._mark = mark
    self._size = QRectF(0, 0, display_rect.width(), display_rect.height())
    self.setPos(display_rect.topLeft())
    color = QColor(STATUS_COLORS[mark.status])
    self._label.setText(f"#{mark.no}")
    self._label.setBrush(color)
    if mark.kind == KIND_STAMP:
      self._label.setPos(self._size.width(), 0)
      self._label.setTransform(QTransform())
    else:
      # 標籤以螢幕像素往上偏移，貼在框的左上角外側，不蓋住尺寸文字
      self._label.setPos(0, 0)
      self._label.setTransform(QTransform.fromTranslate(0, -15))
    self.setToolTip("" if mark.kind == KIND_TEXT else self._tooltip())
    self.setCursor(Qt.CursorShape.PointingHandCursor if mark.kind == KIND_TEXT
                   else Qt.CursorShape.SizeAllCursor)
    self.update()

  def _tooltip(self) -> str:
    m = self._mark
    lines = [f"#{m.no}"]
    if m.link:
      lines.append(f"連結：{m.link}（Ctrl+點擊開啟）")
    if m.measured:
      lines.append(f"實測：{m.measured}")
    if m.note:
      lines.append(f"備註：{m.note}")
    if m.checker:
      lines.append(f"標記人：{m.checker}  {m.updated}")
    return "\n".join(lines)

  def display_rect(self) -> QRectF:
    return self._size.translated(self.pos())

  def resizable(self) -> bool:
    return self._mark.kind == KIND_STAMP

  def set_display_rect(self, r: QRectF):
    """拖曳縮放時的即時預覽；放開後由 view 寫回 Mark。"""
    self.prepareGeometryChange()
    self._size = QRectF(0, 0, r.width(), r.height())
    self.setPos(r.topLeft())
    self._label.setPos(self._size.width(), 0)
    self.update()

  def boundingRect(self) -> QRectF:
    pad = max(self._size.width(), self._size.height()) * 0.08 + 1
    if self._mark.kind == KIND_TEXT:
      pad = max(pad, status_badge_rect(self._size, self._mark.style).width() * 0.6 + 1)
    return self._size.adjusted(-pad, -pad, pad, pad)

  def shape(self) -> QPainterPath:
    p = QPainterPath()
    p.addRect(self.boundingRect())
    return p

  def paint(self, painter, option, widget=None):
    m = self._mark
    color = QColor(STATUS_COLORS[m.status])
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    r = self._size
    if m.kind == KIND_TEXT:
      text_layout.paint(painter, r, m.text, m.style)
      if m.status != STATUS_NONE:
        paint_status_badge(painter, status_badge_rect(r, m.style), m.status)
      if m.link:
        self._paint_link_badge(painter, r)
    elif m.kind == KIND_STAMP:
      fill = QColor(color)
      fill.setAlpha(40)
      painter.setPen(QPen(color, r.width() * 0.07))
      painter.setBrush(QBrush(fill))
      painter.drawEllipse(r.adjusted(r.width() * 0.04, r.height() * 0.04,
                                     -r.width() * 0.04, -r.height() * 0.04))
      pen = QPen(color, r.width() * 0.10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                 Qt.PenJoinStyle.RoundJoin)
      painter.setPen(pen)
      painter.setBrush(Qt.BrushStyle.NoBrush)
      painter.drawPath(_symbol_path(m.status, r))
    else:
      fill = QColor(color)
      fill.setAlpha(28)
      pen = QPen(color, 2)
      pen.setCosmetic(True)
      painter.setPen(pen)
      painter.setBrush(QBrush(fill))
      if m.kind == KIND_ELLIPSE:
        painter.drawEllipse(r)
      else:
        painter.drawRect(r)
    self._paint_selection(painter)

  def _paint_link_badge(self, painter, r: QRectF):
    d = min(max(r.height() * 0.35, 3.0), 10.0)
    badge = QRectF(r.right() - d * 0.6, r.top() - d * 0.4, d, d)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1e88e5"))
    painter.drawEllipse(badge)
    pen = QPen(QColor("white"), d * 0.12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    c = badge.center()
    painter.drawLine(QPointF(c.x() - d * 0.2, c.y() + d * 0.2), QPointF(c.x() + d * 0.2, c.y() - d * 0.2))
    painter.drawArc(QRectF(c.x() - d * 0.38, c.y() - d * 0.05, d * 0.36, d * 0.36), 45 * 16, 180 * 16)
    painter.drawArc(QRectF(c.x() + d * 0.02, c.y() - d * 0.31, d * 0.36, d * 0.36), 225 * 16, 180 * 16)

  def _paint_selection(self, painter):
    if self.isSelected():
      pen = QPen(SELECT_COLOR, 1.5, Qt.PenStyle.DashLine)
      pen.setCosmetic(True)
      painter.setPen(pen)
      painter.setBrush(Qt.BrushStyle.NoBrush)
      painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))
      if self.resizable():
        self._paint_handle(painter)

  def _paint_handle(self, painter):
    scale = painter.worldTransform().m11() or 1.0
    d = HANDLE_PX / scale
    c = self._size.bottomRight()
    pen = QPen(SELECT_COLOR, 1.2)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(QColor("white"))
    painter.drawRect(QRectF(c.x() - d, c.y() - d, d, d))
