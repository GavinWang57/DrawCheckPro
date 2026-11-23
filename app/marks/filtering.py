"""標記的多條件篩選（給標記管理視窗用）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.marks.model import KINDS, STATUSES, Mark


@dataclass
class MarkFilter:
  statuses: set[str] = field(default_factory=lambda: set(STATUSES))
  kinds: set[str] = field(default_factory=lambda: set(KINDS))
  page: int | None = None      # None = 全部頁
  checker: str | None = None   # None = 全部標記人
  keyword: str = ""


def _matches_keyword(m: Mark, keyword: str) -> bool:
  kw = keyword.strip().lower()
  if not kw:
    return True
  fields = (m.text, m.note, m.measured, m.checker, m.link, f"#{m.no}")
  return any(kw in f.lower() for f in fields)


def filter_marks(marks: list[Mark], f: MarkFilter) -> list[Mark]:
  out = [m for m in marks
         if m.status in f.statuses and m.kind in f.kinds
         and (f.page is None or m.page == f.page)
         and (f.checker is None or m.checker == f.checker)
         and _matches_keyword(m, f.keyword)]
  return sorted(out, key=lambda m: (m.page, m.no))
