"""在記憶體副本上改寫 PDF 內容串流，讓細線與細字變粗。原始檔案不會被修改。"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import pymupdf as fitz


@dataclass(frozen=True)
class VectorParams:
  line_mult: float = 1.5
  min_line_pt: float = 0.35
  text_stroke_pt: float = 0.12
  fill_stroke_pt: float = 0.08


_DELIMS = b"()<>[]{}/%"
_WS = b" \t\r\n\f\x00"
_TOKEN_RE = re.compile(
  rb"[ \t\r\n\f\x00]+"
  rb"|%[^\r\n]*"
  rb"|/[^ \t\r\n\f\x00()<>\[\]{}/%]*"
  rb"|<<|>>"
  rb"|<[0-9A-Fa-f \t\r\n\f]*>"
  rb"|[\[\]{}]"
  rb"|[+-]?(?:\d+\.?\d*|\.\d+)"
  rb"|[A-Za-z][A-Za-z0-9*]*|'|\""
)
_OPERAND_KEYWORDS = {b"true", b"false", b"null"}

PATH_OPS = {b"m", b"l", b"c", b"v", b"y", b"h", b"re"}
STROKE_PAINT = {b"S", b"s", b"B", b"B*", b"b", b"b*"}
FILL_ONLY = {b"f": b"B", b"F": b"B", b"f*": b"B*"}
PAINT_OPS = STROKE_PAINT | set(FILL_ONLY) | {b"n"}
CLIP_OPS = {b"W", b"W*"}
FILL_COLOR_OPS = {b"g", b"rg", b"k", b"cs", b"sc", b"scn"}
STROKE_COLOR_OPS = {b"G", b"RG", b"K", b"CS", b"SC", b"SCN"}
TEXT_REPLAY_OPS = (
  {b"Tf", b"Tc", b"Tw", b"Tz", b"TL", b"Ts", b"Tr", b"w", b"J", b"j", b"M", b"d",
   b"ri", b"i", b"gs", b"cm"} | FILL_COLOR_OPS | STROKE_COLOR_OPS
)
_FILL_TO_STROKE = {b"g": b"G", b"rg": b"RG", b"k": b"K", b"cs": b"CS", b"sc": b"SC", b"scn": b"SCN"}
_TR_MAP = {0: 2, 4: 6}


class ContentParseError(Exception):
  pass


def _read_string(data: bytes, pos: int) -> int:
  depth = 0
  n = len(data)
  i = pos
  while i < n:
    ch = data[i]
    if ch == 0x5C:  # backslash
      i += 2
      continue
    if ch == 0x28:
      depth += 1
    elif ch == 0x29:
      depth -= 1
      if depth == 0:
        return i + 1
    i += 1
  raise ContentParseError("unterminated string")


def _read_inline_image(data: bytes, pos: int) -> int:
  m = re.compile(rb"[ \t\r\n\f\x00]ID[ \t\r\n\f\x00]").search(data, pos)
  if not m:
    raise ContentParseError("inline image without ID")
  e = re.compile(rb"[ \t\r\n\f\x00]EI(?=[ \t\r\n\f\x00]|$)").search(data, m.end())
  if not e:
    raise ContentParseError("inline image without EI")
  return e.end()


def iter_ops(data: bytes):
  """將內容串流切成 (operator, operands)；inline image 以 (b"BI", [raw]) 整段回傳。"""
  operands: list[bytes] = []
  pos = 0
  n = len(data)
  while pos < n:
    ch = data[pos]
    if ch == 0x28:
      end = _read_string(data, pos)
      operands.append(data[pos:end])
      pos = end
      continue
    m = _TOKEN_RE.match(data, pos)
    if not m:
      raise ContentParseError(f"unexpected byte at {pos}")
    tok = m.group()
    first = tok[0]
    if first in _WS or first == 0x25:
      pos = m.end()
      continue
    if first == 0x2F or first in b"<>[]{}+-.0123456789" or tok in _OPERAND_KEYWORDS:
      operands.append(tok)
      pos = m.end()
      continue
    if tok == b"BI":
      end = _read_inline_image(data, pos)
      yield b"BI", [data[pos:end]]
      operands = []
      pos = end
      continue
    yield tok, operands
    operands = []
    pos = m.end()
  if operands:
    yield None, operands


def _mat_mul(a, b):
  return (
    a[0] * b[0] + a[1] * b[2],
    a[0] * b[1] + a[1] * b[3],
    a[2] * b[0] + a[3] * b[2],
    a[2] * b[1] + a[3] * b[3],
    a[4] * b[0] + a[5] * b[2] + b[4],
    a[4] * b[1] + a[5] * b[3] + b[5],
  )


def _fmt(v: float) -> bytes:
  return (b"%.4f" % v).rstrip(b"0").rstrip(b".") or b"0"


def _op_bytes(op: bytes, operands) -> bytes:
  return b" ".join([*operands, op])


class _State:
  __slots__ = ("ctm", "lw", "fill_cs", "fill_color", "tr")

  def __init__(self):
    self.ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    self.lw = 1.0
    self.fill_cs: list[bytes] | None = None
    self.fill_color: tuple[bytes, list[bytes]] | None = None
    self.tr = 0

  def copy(self):
    s = _State()
    s.ctm, s.lw, s.fill_cs, s.fill_color, s.tr = (
      self.ctm, self.lw, self.fill_cs, self.fill_color, self.tr)
    return s

  def scale(self) -> float:
    a, b, c, d = self.ctm[:4]
    return math.sqrt(abs(a * d - b * c)) or 1.0

  def stroke_from_fill(self) -> list[bytes]:
    out = []
    if self.fill_cs is not None:
      out.append(_op_bytes(b"CS", self.fill_cs))
    if self.fill_color is not None:
      op, args = self.fill_color
      out.append(_op_bytes(_FILL_TO_STROKE[op], args))
    if not out:
      out.append(b"0 G")
    return out


class _Rewriter:
  def __init__(self, params: VectorParams):
    self.p = params
    self.st = _State()
    self.stack: list[_State] = []
    self.out: list[bytes] = []
    self.path: list[bytes] = []
    self.path_clip = False
    self.in_text = False
    self.text_replay: list[bytes] = []

  def run(self, data: bytes) -> bytes:
    for op, args in iter_ops(data):
      if op is None:
        self.out.append(b" ".join(args))
        continue
      self._handle(op, args)
    if self.path:
      self.out.extend(self.path)
    return b"\n".join(self.out) + b"\n"

  def _track(self, op: bytes, args: list[bytes]):
    st = self.st
    try:
      if op == b"w" and args:
        st.lw = float(args[-1])
      elif op == b"cm" and len(args) >= 6:
        m = tuple(float(x) for x in args[-6:])
        st.ctm = _mat_mul(m, st.ctm)
      elif op == b"Tr" and args:
        st.tr = int(float(args[-1]))
      elif op == b"cs":
        st.fill_cs = list(args)
        st.fill_color = None
      elif op in (b"g", b"rg", b"k"):
        st.fill_cs = None
        st.fill_color = (op, list(args))
      elif op in (b"sc", b"scn"):
        st.fill_color = (op, list(args))
    except ValueError:
      pass

  def _handle(self, op: bytes, args: list[bytes]):
    if op in PATH_OPS or op in CLIP_OPS:
      if op in CLIP_OPS:
        self.path_clip = True
      self.path.append(_op_bytes(op, args))
      return
    if op in PAINT_OPS:
      self._paint(op, args)
      return
    if self.path:
      self.out.extend(self.path)
      self.path = []
      self.path_clip = False

    if op == b"BI":
      self.out.append(args[0])
      return
    if op == b"q":
      self.stack.append(self.st.copy())
      self.out.append(b"q")
      return
    if op == b"Q":
      if self.stack:
        self.st = self.stack.pop()
      self.out.append(b"Q")
      return
    if op == b"BT":
      self._begin_text()
      return
    if op == b"ET" and self.in_text:
      self._end_text()
      return
    if self.in_text:
      self._text_op(op, args)
      return
    self._track(op, args)
    self.out.append(_op_bytes(op, args))

  def _paint(self, op: bytes, args: list[bytes]):
    path = self.path
    self.path = []
    clip = self.path_clip
    self.path_clip = False
    scale = self.st.scale()
    if op in STROKE_PAINT:
      lw = max(self.st.lw * self.p.line_mult, self.p.min_line_pt / scale)
      self.out.append(_fmt(lw) + b" w")
      self.out.extend(path)
      self.out.append(_op_bytes(op, args))
      self.out.append(_fmt(self.st.lw) + b" w")
      return
    if op in FILL_ONLY and self.p.fill_stroke_pt > 0 and not clip:
      self.out.append(b"q")
      self.out.extend(self.st.stroke_from_fill())
      self.out.append(_fmt(self.p.fill_stroke_pt / scale) + b" w 1 j")
      self.out.extend(path)
      self.out.append(FILL_ONLY[op])
      self.out.append(b"Q")
      return
    self.out.extend(path)
    self.out.append(_op_bytes(op, args))

  def _begin_text(self):
    self.in_text = True
    self.text_replay = []
    if self.p.text_stroke_pt <= 0:
      self.out.append(b"BT")
      return
    self.out.append(b"q")
    self.out.extend(self.st.stroke_from_fill())
    self.out.append(_fmt(self.p.text_stroke_pt / self.st.scale()) + b" w 1 j")
    if self.st.tr in _TR_MAP:
      self.out.append(b"%d Tr" % _TR_MAP[self.st.tr])
    self.out.append(b"BT")

  def _end_text(self):
    self.in_text = False
    self.out.append(b"ET")
    if self.p.text_stroke_pt <= 0:
      return
    self.out.append(b"Q")
    self.out.extend(self.text_replay)
    self.text_replay = []

  def _text_op(self, op: bytes, args: list[bytes]):
    self._track(op, args)
    if self.p.text_stroke_pt <= 0:
      self.out.append(_op_bytes(op, args))
      return
    raw = _op_bytes(op, args)
    if op in TEXT_REPLAY_OPS:
      self.text_replay.append(raw)
    if op == b"Tr":
      self.out.append(b"%d Tr" % _TR_MAP.get(self.st.tr, self.st.tr))
    elif op in FILL_COLOR_OPS:
      self.out.append(raw)
      self.out.extend(self.st.stroke_from_fill())
    elif op in STROKE_COLOR_OPS or op == b"w":
      pass
    else:
      self.out.append(raw)


def rewrite_stream(data: bytes, params: VectorParams) -> bytes:
  return _Rewriter(params).run(data)


def _is_form(doc: fitz.Document, xref: int) -> bool:
  try:
    return doc.xref_get_key(xref, "Subtype") == ("name", "/Form")
  except Exception:
    return False


def enhance_forms(doc: fitz.Document, params: VectorParams):
  """改寫所有 Form XObject（CAD 常把圖塊放在 Form 內）。單一 Form 失敗時保留原樣。"""
  for xref in range(1, doc.xref_length()):
    if not _is_form(doc, xref):
      continue
    try:
      doc.update_stream(xref, rewrite_stream(doc.xref_stream(xref), params))
    except Exception:
      pass


def enhance_page(doc: fitz.Document, page: fitz.Page, params: VectorParams):
  xrefs = page.get_contents()
  if not xrefs:
    return
  data = b"\n".join(doc.xref_stream(x) or b"" for x in xrefs)
  new = rewrite_stream(data, params)
  doc.update_stream(xrefs[0], new)
  for x in xrefs[1:]:
    doc.update_stream(x, b"")
