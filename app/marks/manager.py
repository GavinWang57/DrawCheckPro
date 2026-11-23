"""標記管理視窗：多條件篩選、多選、刪除、輸出選取標記的 PDF。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout)

from app.marks.controller import MarkController
from app.marks.filtering import MarkFilter, filter_marks
from app.marks.model import KIND_LABELS, KINDS, STATUS_COLORS, STATUS_LABELS, STATUSES, Mark
from app.marks.text_dialog import STATUS_ICONS
from app.ui import icons

COLUMNS = ("#", "頁", "類型", "狀態", "實測值", "內容 / 備註", "標記人", "更新時間")


class _SortItem(QTableWidgetItem):
  """數字欄位依數值排序。"""

  def __lt__(self, other):
    a, b = self.data(Qt.ItemDataRole.UserRole + 1), other.data(Qt.ItemDataRole.UserRole + 1)
    if a is not None and b is not None:
      return a < b
    return super().__lt__(other)


class MarkManagerDialog(QDialog):
  markActivated = Signal(str)
  editRequested = Signal(str)
  exportRequested = Signal(list)  # 選取的 mark id

  def __init__(self, ctl: MarkController, parent=None):
    super().__init__(parent)
    self.setWindowTitle("標記管理")
    self.ctl = ctl
    self._syncing = False

    self.status_buttons: dict[str, QToolButton] = {}
    srow = QHBoxLayout()
    srow.addWidget(QLabel("狀態"))
    for st in STATUSES:
      b = QToolButton()
      b.setText(STATUS_LABELS[st])
      b.setIcon(icons.icon(STATUS_ICONS[st]))
      b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
      b.setCheckable(True)
      b.setObjectName("StatusChip")
      b.setChecked(True)
      b.toggled.connect(self.refresh)
      self.status_buttons[st] = b
      srow.addWidget(b)
    srow.addSpacing(16)
    srow.addWidget(QLabel("類型"))
    self.kind_boxes: dict[str, QCheckBox] = {}
    for k in KINDS:
      cb = QCheckBox(KIND_LABELS[k])
      cb.setChecked(True)
      cb.toggled.connect(self.refresh)
      self.kind_boxes[k] = cb
      srow.addWidget(cb)
    srow.addStretch(1)

    self.page = QComboBox()
    self.checker = QComboBox()
    self.keyword = QLineEdit()
    self.keyword.setPlaceholderText("搜尋內容、備註、實測值、標記人、#編號")
    self.keyword.setClearButtonEnabled(True)
    clear = QPushButton("清除篩選")
    clear.clicked.connect(self.clear_filter)
    frow = QHBoxLayout()
    frow.addWidget(QLabel("頁碼"))
    frow.addWidget(self.page)
    frow.addWidget(QLabel("標記人"))
    frow.addWidget(self.checker)
    frow.addWidget(self.keyword, 1)
    frow.addWidget(clear)
    self.page.currentIndexChanged.connect(self.refresh)
    self.checker.currentIndexChanged.connect(self.refresh)
    self.keyword.textChanged.connect(self.refresh)

    self.table = QTableWidget(0, len(COLUMNS))
    self.table.setHorizontalHeaderLabels(COLUMNS)
    self.table.verticalHeader().setVisible(False)
    self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    self.table.setSortingEnabled(True)
    self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    hh = self.table.horizontalHeader()
    for col in range(len(COLUMNS)):
      hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
    self.table.itemSelectionChanged.connect(self._on_selection)
    self.table.cellDoubleClicked.connect(lambda row, _c: self.editRequested.emit(self._row_id(row)))

    self.count = QLabel()
    self.btn_all = QPushButton("全選")
    self.btn_none = QPushButton("取消選取")
    self.btn_delete = QPushButton(icons.icon("delete"), "刪除選取…")
    self.btn_export = QPushButton(icons.icon("export"), "輸出選取的 PDF…")
    self.btn_all.clicked.connect(self.table.selectAll)
    self.btn_none.clicked.connect(self.table.clearSelection)
    self.btn_delete.clicked.connect(self.delete_selected)
    self.btn_export.clicked.connect(lambda: self.exportRequested.emit(self.selected_ids()))
    brow = QHBoxLayout()
    brow.addWidget(self.count, 1)
    for b in (self.btn_all, self.btn_none, self.btn_delete, self.btn_export):
      brow.addWidget(b)

    QShortcut(QKeySequence.StandardKey.Delete, self.table, self.delete_selected)
    QShortcut(QKeySequence.StandardKey.Undo, self, ctl.undo_stack.undo)
    QShortcut(QKeySequence.StandardKey.Redo, self, ctl.undo_stack.redo)

    lay = QVBoxLayout(self)
    lay.addLayout(srow)
    lay.addLayout(frow)
    lay.addWidget(self.table, 1)
    lay.addLayout(brow)

    for sig in (ctl.added, ctl.changed, ctl.removed, ctl.reset):
      sig.connect(self.refresh)
    self.refresh()
    self.resize(900, 560)

  # ---- 篩選 ----
  def current_filter(self) -> MarkFilter:
    return MarkFilter(
      statuses={s for s, b in self.status_buttons.items() if b.isChecked()},
      kinds={k for k, cb in self.kind_boxes.items() if cb.isChecked()},
      page=self.page.currentData(),
      checker=self.checker.currentData(),
      keyword=self.keyword.text(),
    )

  def clear_filter(self):
    self._syncing = True
    for w in (*self.status_buttons.values(), *self.kind_boxes.values()):
      w.setChecked(True)
    self.page.setCurrentIndex(0)
    self.checker.setCurrentIndex(0)
    self.keyword.clear()
    self._syncing = False
    self.refresh()

  def _fill_combo(self, combo: QComboBox, all_label: str, items: list[tuple[str, object]]):
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(all_label, None)
    for text, data in items:
      combo.addItem(text, data)
    idx = combo.findData(current) if current is not None else 0
    combo.setCurrentIndex(max(idx, 0))
    combo.blockSignals(False)

  def _update_choices(self, marks: list[Mark]):
    pages = sorted({m.page for m in marks})
    self._fill_combo(self.page, "全部頁", [(f"第 {p + 1} 頁", p) for p in pages])
    checkers = sorted({m.checker for m in marks if m.checker})
    self._fill_combo(self.checker, "全部", [(c, c) for c in checkers])

  # ---- 表格 ----
  def refresh(self, *_):
    if self._syncing:
      return
    self._syncing = True
    all_marks = self.ctl.marks()
    self._update_choices(all_marks)
    selected = set(self.selected_ids())
    visible = filter_marks(all_marks, self.current_filter())
    self.table.setSortingEnabled(False)
    self.table.setRowCount(0)
    self.table.setRowCount(len(visible))
    for row, m in enumerate(visible):
      content = "　".join(x.replace("\n", " ") for x in (m.text, m.note) if x)
      cells = [(f"#{m.no}", m.no), (str(m.page + 1), m.page), (KIND_LABELS.get(m.kind, ""), None),
               (STATUS_LABELS[m.status], None), (m.measured, None), (content, None),
               (m.checker, None), (m.updated, None)]
      for col, (text, key) in enumerate(cells):
        it = _SortItem(text)
        it.setData(Qt.ItemDataRole.UserRole, m.id)
        if key is not None:
          it.setData(Qt.ItemDataRole.UserRole + 1, key)
        if col == 3:
          it.setForeground(QColor(STATUS_COLORS[m.status]))
        self.table.setItem(row, col, it)
    self.table.setSortingEnabled(True)
    sel_model = self.table.selectionModel()
    for row in range(self.table.rowCount()):
      if self._row_id(row) in selected:
        sel_model.select(self.table.model().index(row, 0),
                         sel_model.SelectionFlag.Select | sel_model.SelectionFlag.Rows)
    self._syncing = False
    self._update_count()

  def _row_id(self, row: int) -> str:
    return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

  def visible_ids(self) -> list[str]:
    return [self._row_id(r) for r in range(self.table.rowCount())]

  def selected_ids(self) -> list[str]:
    rows = sorted({i.row() for i in self.table.selectedIndexes()})
    return [self._row_id(r) for r in rows]

  def _update_count(self):
    n = len(self.selected_ids())
    self.count.setText(f"顯示 {self.table.rowCount()} / 共 {len(self.ctl.marks())}，已選 {n}")
    self.btn_delete.setEnabled(n > 0)
    self.btn_export.setEnabled(n > 0)

  def _on_selection(self):
    if self._syncing:
      return
    self._update_count()
    ids = self.selected_ids()
    if len(ids) == 1:
      self.markActivated.emit(ids[0])

  # ---- 動作 ----
  def delete_selected(self):
    ids = self.selected_ids()
    if not ids:
      return
    ans = QMessageBox.question(self, "刪除標記", f"刪除 {len(ids)} 個標記？（可用 Ctrl+Z 復原）")
    if ans == QMessageBox.StandardButton.Yes:
      self.ctl.delete_marks(ids)
