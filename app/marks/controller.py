"""標記集合 + 復原/重做。所有變更都經過 QUndoStack，畫面與清單透過 signal 同步。"""
from __future__ import annotations

import copy

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from app.marks.model import EDITABLE_FIELDS, Mark, now_iso


class MarkController(QObject):
  added = Signal(object)      # Mark
  removed = Signal(str, int)  # id, page
  changed = Signal(object)    # Mark
  reset = Signal()
  dirtyChanged = Signal(bool)

  def __init__(self, parent=None):
    super().__init__(parent)
    self._marks: dict[str, Mark] = {}
    self.undo_stack = QUndoStack(self)
    self._dirty = False

  # ---- 查詢 ----
  def marks(self) -> list[Mark]:
    return list(self._marks.values())

  def get(self, mid: str) -> Mark | None:
    return self._marks.get(mid)

  def marks_on_page(self, page: int) -> list[Mark]:
    return [m for m in self._marks.values() if m.page == page]

  @property
  def dirty(self) -> bool:
    return self._dirty

  def set_dirty(self, v: bool):
    if v != self._dirty:
      self._dirty = v
      self.dirtyChanged.emit(v)

  def load(self, marks: list[Mark]):
    self.undo_stack.clear()
    self._marks = {m.id: m for m in marks}
    used = set()
    for m in self._marks.values():
      if m.no <= 0 or m.no in used:
        m.no = 0
      used.add(m.no)
    for m in self._marks.values():
      if m.no == 0:
        m.no = self._next_no()
    self.set_dirty(False)
    self.reset.emit()

  def _next_no(self) -> int:
    return max((m.no for m in self._marks.values()), default=0) + 1

  # ---- 變更（可復原）----
  def add_mark(self, mark: Mark):
    if mark.no <= 0:
      mark.no = self._next_no()
    self.undo_stack.push(_AddCmd(self, [mark], "新增標記"))

  def delete_marks(self, ids: list[str]):
    marks = [self._marks[i] for i in ids if i in self._marks]
    if marks:
      self.undo_stack.push(_DeleteCmd(self, marks, f"刪除 {len(marks)} 個標記"))

  def update_marks(self, ids: list[str], text: str = "修改標記", **changes):
    changes = {k: v for k, v in changes.items() if k in EDITABLE_FIELDS}
    before, after = {}, {}
    for i in ids:
      m = self._marks.get(i)
      if not m:
        continue
      old = {k: copy.deepcopy(getattr(m, k)) for k in changes}
      if old == changes:
        continue
      before[i], after[i] = old, dict(changes)
    if before:
      self.undo_stack.push(_UpdateCmd(self, before, after, text))

  # ---- 給 command 用的底層操作 ----
  def _insert(self, m: Mark):
    self._marks[m.id] = m
    self.set_dirty(True)
    self.added.emit(m)

  def _remove(self, m: Mark):
    self._marks.pop(m.id, None)
    self.set_dirty(True)
    self.removed.emit(m.id, m.page)

  def _apply(self, mid: str, fields: dict):
    m = self._marks.get(mid)
    if not m:
      return
    for k, v in fields.items():
      setattr(m, k, copy.deepcopy(v))
    m.updated = now_iso()
    self.set_dirty(True)
    self.changed.emit(m)


class _AddCmd(QUndoCommand):
  def __init__(self, ctl: MarkController, marks: list[Mark], text: str):
    super().__init__(text)
    self.ctl, self.marks = ctl, marks

  def redo(self):
    for m in self.marks:
      self.ctl._insert(m)

  def undo(self):
    for m in self.marks:
      self.ctl._remove(m)


class _DeleteCmd(_AddCmd):
  def redo(self):
    super().undo()

  def undo(self):
    super().redo()


class _UpdateCmd(QUndoCommand):
  def __init__(self, ctl, before: dict, after: dict, text: str):
    super().__init__(text)
    self.ctl, self.before, self.after = ctl, before, after

  def redo(self):
    for mid, f in self.after.items():
      self.ctl._apply(mid, f)

  def undo(self):
    for mid, f in self.before.items():
      self.ctl._apply(mid, f)
