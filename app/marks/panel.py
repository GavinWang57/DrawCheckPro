"""右側標記清單與編輯對話框。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from app.marks.controller import MarkController
from app.marks.export import summary
from app.marks.model import STATUS_COLORS, STATUS_LABELS, STATUSES, Mark
from app.ui import icons

_FILTER_ALL = "all"


class MarksPanel(QWidget):
  markActivated = Signal(str)
  editRequested = Signal(str)
  manageRequested = Signal()

  def __init__(self, ctl: MarkController, parent=None):
    super().__init__(parent)
    self.ctl = ctl
    self.current_page = 0
    self._syncing = False

    self.filter = QComboBox()
    self.filter.addItem("全部狀態", _FILTER_ALL)
    for s in STATUSES:
      self.filter.addItem(STATUS_LABELS[s], s)
    self.only_page = QCheckBox("僅本頁")
    self.manage = QPushButton(icons.icon("list"), "標記管理")
    self.manage.setToolTip("開啟標記管理：多條件篩選、多選刪除、輸出選取標記的 PDF（Ctrl+M）")
    self.manage.clicked.connect(self.manageRequested)
    top = QHBoxLayout()
    top.addWidget(self.filter, 1)
    top.addWidget(self.only_page)
    top.addWidget(self.manage)

    self.table = QTableWidget(0, 5)
    self.table.setHorizontalHeaderLabels(["#", "頁", "狀態", "實測值", "內容 / 備註"])
    self.table.verticalHeader().setVisible(False)
    self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    hh = self.table.horizontalHeader()
    for col in range(4):
      hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    self.summary = QLabel()
    self.summary.setWordWrap(True)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.addLayout(top)
    lay.addWidget(self.table, 1)
    lay.addWidget(self.summary)

    self.filter.currentIndexChanged.connect(self.refresh)
    self.only_page.toggled.connect(self.refresh)
    self.table.itemSelectionChanged.connect(self._on_row_selected)
    self.table.cellDoubleClicked.connect(
      lambda row, _c: self.editRequested.emit(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)))
    for sig in (ctl.added, ctl.changed, ctl.reset):
      sig.connect(self.refresh)
    ctl.removed.connect(self.refresh)
    self.refresh()

  def set_page(self, pno: int):
    self.current_page = pno
    if self.only_page.isChecked():
      self.refresh()

  def _visible_marks(self) -> list[Mark]:
    f = self.filter.currentData()
    marks = self.ctl.marks()
    if f != _FILTER_ALL:
      marks = [m for m in marks if m.status == f]
    if self.only_page.isChecked():
      marks = [m for m in marks if m.page == self.current_page]
    return sorted(marks, key=lambda m: (m.page, m.no))

  def refresh(self, *_):
    self._syncing = True
    selected = set(self._selected_ids())
    self.table.setRowCount(0)
    for m in self._visible_marks():
      row = self.table.rowCount()
      self.table.insertRow(row)
      content = "　".join(x.replace("\n", " ") for x in (m.text, m.note) if x)
      cells = [f"#{m.no}", str(m.page + 1), STATUS_LABELS[m.status], m.measured, content]
      for col, text in enumerate(cells):
        it = QTableWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, m.id)
        if col == 2:
          it.setForeground(QColor(STATUS_COLORS[m.status]))
        self.table.setItem(row, col, it)
      if m.id in selected:
        self.table.selectRow(row)
    s = summary(self.ctl.marks())
    self.summary.setText("　".join(f"{k}：{v}" for k, v in s.items()))
    self._syncing = False

  def _selected_ids(self) -> list[str]:
    rows = {i.row() for i in self.table.selectedIndexes()}
    return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in sorted(rows)]

  def select_ids(self, ids: list[str]):
    if self._syncing:
      return
    self._syncing = True
    self.table.clearSelection()
    wanted = set(ids)
    mode = self.table.selectionMode()
    self.table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
    for row in range(self.table.rowCount()):
      if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) in wanted:
        self.table.selectRow(row)
    self.table.setSelectionMode(mode)
    self._syncing = False

  def _on_row_selected(self):
    if self._syncing:
      return
    ids = self._selected_ids()
    if len(ids) == 1:
      self.markActivated.emit(ids[0])


class MarkEditDialog(QDialog):
  def __init__(self, mark: Mark, parent=None):
    super().__init__(parent)
    self.setWindowTitle(f"標記 #{mark.no}（第 {mark.page + 1} 頁）")
    self.status = QComboBox()
    for s in STATUSES:
      self.status.addItem(STATUS_LABELS[s], s)
    self.status.setCurrentIndex(STATUSES.index(mark.status) if mark.status in STATUSES else 0)
    self.measured = QLineEdit(mark.measured)
    self.checker = QLineEdit(mark.checker)
    self.note = QPlainTextEdit(mark.note)
    self.note.setMinimumHeight(90)

    form = QFormLayout()
    form.addRow("狀態", self.status)
    form.addRow("實測值", self.measured)
    form.addRow("標記人", self.checker)
    form.addRow("備註", self.note)
    form.addRow("建立 / 更新", QLabel(f"{mark.created}\n{mark.updated}"))
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    lay = QVBoxLayout(self)
    lay.addLayout(form)
    lay.addWidget(buttons)
    self.resize(380, 320)

  def values(self) -> dict:
    return {
      "status": self.status.currentData(),
      "measured": self.measured.text().strip(),
      "checker": self.checker.text().strip(),
      "note": self.note.toPlainText().strip(),
    }
