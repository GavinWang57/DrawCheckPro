from __future__ import annotations

import getpass
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

KIND_STAMP = "stamp"
KIND_RECT = "rect"
KIND_ELLIPSE = "ellipse"
KIND_TEXT = "text"
KINDS = (KIND_STAMP, KIND_RECT, KIND_ELLIPSE, KIND_TEXT)

STATUS_NONE = "none"       # 純標記，不代表核對結果
STATUS_OK = "ok"
STATUS_NG = "ng"
STATUS_PENDING = "pending"
STATUSES = (STATUS_NONE, STATUS_OK, STATUS_NG, STATUS_PENDING)
STATUS_LABELS = {STATUS_NONE: "無狀態", STATUS_OK: "OK", STATUS_NG: "NG", STATUS_PENDING: "待確認"}
STATUS_COLORS = {STATUS_NONE: "#536dfe", STATUS_OK: "#1e9e4a", STATUS_NG: "#e0262b",
                 STATUS_PENDING: "#e8a400"}
KIND_LABELS = {KIND_STAMP: "戳記", KIND_RECT: "矩形", KIND_ELLIPSE: "橢圓", KIND_TEXT: "文字"}

# 文字框樣式；顏色為 #AARRGGBB（含透明度）或 #RRGGBB
DEFAULT_TEXT_STYLE = {
  "font_size": 10.0,     # pt
  "bold": False,
  "text_color": "#ff0b3d91",
  "fill_color": "#e6fff59d",
  "border_color": "#ffe8a400",
  "border_width": 0.8,   # pt，0 = 無框線
  "italic": False,
  "underline": "none",   # none / single / double
  "strike": False,
}
UNDERLINES = ("none", "single", "double")

EDITABLE_FIELDS = ("status", "note", "measured", "checker", "rect", "text", "link", "style")


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_iso() -> str:
  """標記時間，例：2026-11-21 23:00:01。"""
  return datetime.now().strftime(TIME_FORMAT)


def normalize_time(value: str) -> str:
  """舊標記檔的 ISO 格式（2026-11-21T23:00:01）轉成目前的顯示格式。"""
  try:
    return datetime.fromisoformat(str(value)).strftime(TIME_FORMAT)
  except ValueError:
    return str(value)


def default_marker() -> str:
  """預設標記人：目前登入電腦的使用者名稱。"""
  try:
    return getpass.getuser()
  except Exception:
    return os.environ.get("USERNAME", "")


def text_style(style: dict | None) -> dict:
  return {**DEFAULT_TEXT_STYLE, **(style or {})}


def parse_color(value: str) -> tuple[tuple[float, float, float], float]:
  """#AARRGGBB 或 #RRGGBB → ((r, g, b) 0~1, alpha 0~1)。"""
  v = (value or "#000000").lstrip("#")
  if len(v) == 8:
    a, v = int(v[:2], 16) / 255, v[2:]
  else:
    a = 1.0
  r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
  return (r, g, b), a


@dataclass
class Mark:
  page: int
  kind: str
  rect: list[float]  # 未旋轉的 PDF 頁面座標 (pt)：x0, y0, x1, y1
  status: str = STATUS_NONE
  note: str = ""
  measured: str = ""
  checker: str = ""
  text: str = ""     # 文字框內容
  link: str = ""     # 網址或檔案路徑
  style: dict = field(default_factory=dict)
  no: int = 0
  id: str = field(default_factory=lambda: uuid.uuid4().hex)
  created: str = field(default_factory=now_iso)
  updated: str = field(default_factory=now_iso)

  def to_dict(self) -> dict:
    return asdict(self)

  @classmethod
  def from_dict(cls, d: dict) -> "Mark":
    known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
    m = cls(**known)
    if m.kind not in KINDS:
      m.kind = KIND_RECT
    if m.status not in STATUSES:
      m.status = STATUS_PENDING
    m.rect = [float(v) for v in m.rect][:4]
    if not isinstance(m.style, dict):
      m.style = {}
    m.created, m.updated = normalize_time(m.created), normalize_time(m.updated)
    return m

  def summary(self) -> str:
    """清單與書籤用的簡短說明。"""
    parts = [self.text.replace("\n", " ") if self.kind == KIND_TEXT else "",
             self.measured and f"實測 {self.measured}", self.note.replace("\n", " ")]
    return "　".join(p for p in parts if p)
