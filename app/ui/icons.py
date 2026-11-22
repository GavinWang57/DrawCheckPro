"""內建 SVG 線條圖示（24×24 viewBox），不依賴外部圖檔。"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

DEFAULT = "#dbe6f5"
BLUE = "#4fb3ff"
YELLOW = "#ffc340"
GREEN = "#3ddc84"
RED = "#ff5a5f"
AMBER = "#ffb020"
ORANGE = "#ff8a3d"


def _gear() -> str:
  pts = []
  for i in range(16):
    a = math.pi * 2 * i / 16
    r = 9.5 if i % 2 == 0 else 7.2
    for da in (-0.13, 0.13):
      pts.append((12 + r * math.cos(a + da), 12 + r * math.sin(a + da)))
  d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z"
  return f'<path d="{d}"/><circle cx="12" cy="12" r="3.2"/>'


_PATHS: dict[str, str] = {
  "open": '<path d="M3 7.5V18a1.5 1.5 0 0 0 1.5 1.5h13.2a1.5 1.5 0 0 0 1.45-1.1L21.4 11'
          'a1 1 0 0 0-.97-1.25H7.6a1.5 1.5 0 0 0-1.44 1.08L3.6 19"/>'
          '<path d="M3 7.5V6a1.5 1.5 0 0 1 1.5-1.5h4.2l2 2.2h6.3A1.5 1.5 0 0 1 18.5 8.2v1.5"/>',
  "recent": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.2 2"/>'
            '<path d="M3.5 12H2M3.8 7.5 2.6 6.6"/>',
  "save": '<path d="M5 3.5h11.5l3 3V19a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 19V5'
          'A1.5 1.5 0 0 1 6 3.5z"/><path d="M8 3.5v5h7.5v-5M7.5 20.5v-6h9v6"/>',
  "export": '<path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10'
            'a1.5 1.5 0 0 0 1.5-1.5V8.5z"/><path d="M13.5 3.5v5h5"/>'
            '<path d="M9 14.5h7M13.5 12l2.5 2.5-2.5 2.5"/>',
  "fit_page": '<rect x="6" y="5" width="12" height="14" rx="1"/>'
              '<path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5"/>',
  "fit_width": '<rect x="6" y="4" width="12" height="16" rx="1"/>'
               '<path d="M2 12h4M18 12h4M4 10l-2 2 2 2M20 10l2 2-2 2"/>',
  "actual": '<rect x="3" y="5" width="18" height="14" rx="1.5"/>'
            '<path d="M8 10v5M7 10.5 8 10M16 10v5M15 10.5l1-.5M12 11v.01M12 14v.01"/>',
  "zoom_in": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5M8 10.5h5M10.5 8v5"/>',
  "zoom_out": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5M8 10.5h5"/>',
  "fullscreen": '<path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5"/>',
  "pan": '<path d="M18 11V6.5a1.75 1.75 0 0 0-3.5 0M14.5 10V4.75a1.75 1.75 0 0 0-3.5 0V10'
         'M11 10.5V6a1.75 1.75 0 0 0-3.5 0v8"/><path d="M18 8.5a1.75 1.75 0 0 1 3.5 0V14'
         'a7.5 7.5 0 0 1-7.5 7.5h-1.5c-2.6 0-4.2-.8-5.6-2.2l-3.4-3.4a1.75 1.75 0 0 1 2.5-2.5'
         'L7.5 15"/>',
  "select": '<path d="M5 3.5 18.5 10l-5.8 1.7L10 17.5z"/><path d="m12.8 11.8 5 5"/>',
  "stamp_ok": '<circle cx="12" cy="12" r="8.5"/><path d="m8 12.3 2.8 2.8L16.2 9"/>',
  "stamp_ng": '<circle cx="12" cy="12" r="8.5"/><path d="m8.8 8.8 6.4 6.4M15.2 8.8l-6.4 6.4"/>',
  "stamp_pending": '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3'
                   'c-.7.3-1 .8-1 1.5v.5"/><path d="M12 16.8v.2"/>',
  "rect": '<rect x="3.5" y="6" width="17" height="12" rx="1" stroke-dasharray="3 2"/>',
  "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="6.5" stroke-dasharray="3 2"/>',
  "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
  "settings": _gear(),
  "help": '<circle cx="12" cy="12" r="9"/><path d="M9.3 9.3a2.8 2.8 0 1 1 3.8 2.6'
          'c-.7.3-1.1.9-1.1 1.6v.6"/><path d="M12 17.2v.2"/>',
  "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
  "prev": '<path d="m15 5-7 7 7 7"/>',
  "next": '<path d="m9 5 7 7-7 7"/>',
  "info": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/>'
          '<path d="M7.5 9h5M7.5 12.5h9M7.5 16h9"/>',
  "list": '<path d="M9 6.5h11M9 12h11M9 17.5h11"/><path d="m3.5 6.5 1.2 1.2 2-2.2'
          'M3.5 12l1.2 1.2 2-2.2M3.5 17.5l1.2 1.2 2-2.2"/>',
  "thumbs": '<rect x="4" y="3.5" width="16" height="17" rx="1.5"/><path d="M7.5 8h9M7.5 12h9M7.5 16h5"/>',
  "enhance": '<rect x="3.5" y="3.5" width="17" height="17" rx="2"/><path d="M3.5 9.5h17M9.5 9.5v11"/>',
  "file": '<path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10'
          'a1.5 1.5 0 0 0 1.5-1.5V8.5z"/><path d="M13.5 3.5v5h5"/>',
  "star": '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.9z" '
          'fill="{c}"/>',
  "chevron_up": '<path d="m6 15 6-6 6 6"/>',
  "chevron_down": '<path d="m6 9 6 6 6-6"/>',
  "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
  "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  "text": '<rect x="3.5" y="3.5" width="17" height="17" rx="2"/><path d="M8 8h8M12 8v9"/>',
  "export_list": '<path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10'
                 'a1.5 1.5 0 0 0 1.5-1.5V8.5z"/><path d="M13.5 3.5v5h5M8.5 12.5h7M8.5 16h7"/>',
  "pdf_out": '<path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10'
             'a1.5 1.5 0 0 0 1.5-1.5V8.5z"/><path d="M13.5 3.5v5h5"/>'
             '<rect x="2.5" y="11" width="12" height="7" rx="1.2" fill="#e53935" stroke="#e53935"/>'
             '<path d="M5 16.3v-3.6h1.3a1.1 1.1 0 0 1 0 2.2H5M8.6 16.3v-3.6h.9a1.8 1.8 0 0 1 0 3.6z'
             'M12.2 16.3v-3.6h1.8M12.2 14.5h1.4" stroke="#ffffff" stroke-width="0.9"/>',
  "save_page": '<rect x="4.5" y="3.5" width="15" height="17" rx="1.5"/>'
               '<path d="M8 8h8M8 11.5h5"/><circle cx="16" cy="16.5" r="3.2" fill="{c}"/>'
               '<path d="m14.6 16.5 1 1 1.8-1.9" stroke="#0e1f37" stroke-width="1.3"/>',
  "print": '<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="1.5"/>'
           '<path d="M7 14h10v6.5H7z"/><path d="M17 12h.01"/>',
  "snapshot": '<path d="M7 3.5H5A1.5 1.5 0 0 0 3.5 5v2M17 3.5h2A1.5 1.5 0 0 1 20.5 5v2'
              'M20.5 17v2a1.5 1.5 0 0 1-1.5 1.5h-2M7 20.5H5A1.5 1.5 0 0 1 3.5 19v-2"/>'
              '<circle cx="12" cy="12.5" r="3"/><path d="M8.5 9h1.2l.8-1.3h3l.8 1.3h1.2v6.5h-7z"/>',
  "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
          '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  "copy": '<rect x="8" y="8" width="12.5" height="12.5" rx="1.5"/>'
          '<path d="M16 8V5A1.5 1.5 0 0 0 14.5 3.5H5A1.5 1.5 0 0 0 3.5 5v9.5A1.5 1.5 0 0 0 5 16h3"/>',
  "status_none": '<circle cx="12" cy="12" r="8.5" stroke-dasharray="3 2.4"/>',
  "delete": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5"/>',
  "collapse_left": '<path d="m11 17-5-5 5-5M18 17l-5-5 5-5"/>',
  "collapse_right": '<path d="m13 17 5-5-5-5M6 17l5-5-5-5"/>',
}

ICON_COLORS = {
  "open": YELLOW, "recent": DEFAULT, "save": DEFAULT, "export": DEFAULT,
  "stamp_ok": GREEN, "stamp_ng": RED, "stamp_pending": AMBER,
  "rect": BLUE, "ellipse": BLUE, "settings": DEFAULT, "help": DEFAULT,
  "star": YELLOW, "info": BLUE, "list": BLUE, "thumbs": BLUE, "enhance": BLUE,
  "text": ORANGE, "save_page": GREEN, "snapshot": "#26d4c4", "link": BLUE, "delete": RED,
  "status_none": "#8c9eff",
}


def svg(name: str, color: str | None = None, width: float = 1.7) -> str:
  c = color or ICON_COLORS.get(name, DEFAULT)
  body = _PATHS[name].replace("{c}", c)
  return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" '
          f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def render_pixmap(name: str, size: int, color: str | None = None) -> QPixmap:
  r = QSvgRenderer(QByteArray(svg(name, color).encode()))
  pm = QPixmap(size, size)
  pm.fill(Qt.GlobalColor.transparent)
  p = QPainter(pm)
  p.setRenderHint(QPainter.RenderHint.Antialiasing)
  r.render(p, QRectF(0, 0, size, size))
  p.end()
  return pm


@lru_cache(maxsize=None)
def icon(name: str, color: str | None = None) -> QIcon:
  ic = QIcon()
  for s in (16, 24, 32, 48, 64):
    ic.addPixmap(render_pixmap(name, s, color))
  return ic
