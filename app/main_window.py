"""主視窗：分組工具列、左右側欄、底部列、存檔與匯出（版面依 UI/UX 設計圖）。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QFrame, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from app.document import DrawingDocument, ViewSettings
from app.enhance.vector_enhance import VectorParams
from app.enhance_panel import EnhancePanel
from app.marks.controller import MarkController
from app.marks.export import export_csv, export_xlsx
from app.marks.model import STATUS_NG, STATUS_NONE, STATUS_OK, STATUS_PENDING, default_marker
from app.marks.panel import MarkEditDialog, MarksPanel
from app.marks.store import SidecarError, load_marks, save_marks, sidecar_path
from app.output_actions import OutputActionsMixin
from app.resources import resource_path
from app.ui import icons, theme
from app.ui.bottom_bar import BottomBar
from app.ui.dialogs import HelpDialog, SettingsDialog
from app.ui.info_panel import InfoPanel
from app.ui.output_dialog import ALL_PDF, PAGE_PDF
from app.ui.ribbon import Ribbon
from app.ui.search_panel import SearchPanel
from app.ui.side_panel import STRIP_W, CollapsibleSide, collapse_button
from app.viewer import page_view as pv
from app.viewer.tile_renderer import to_pixmap

APP_NAME = "DrawCheck Pro"
APP_SUBTITLE = "工程圖檢核專家"
APP_FULL_NAME = f"{APP_NAME}｜{APP_SUBTITLE}"
VERSION = "1.0.0"
SETTINGS_ORG = "DrawCheckPro"
AUTOSAVE_MS = 30_000
THUMB_RENDER_PX = 420
MAX_RECENT = 10


class ThumbList(QListWidget):
  """每頁一列的縮圖清單；縮圖寬度跟著面板寬度，高度依頁面長寬比。"""

  def __init__(self):
    super().__init__()
    self.setObjectName("Thumbs")
    self.setViewMode(QListWidget.ViewMode.IconMode)
    self.setFlow(QListWidget.Flow.LeftToRight)
    self.setWrapping(True)
    self.setMovement(QListWidget.Movement.Static)
    self.setResizeMode(QListWidget.ResizeMode.Adjust)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.aspect = 0.707

  def set_aspect(self, aspect: float):
    self.aspect = min(max(aspect, 0.2), 5.0)
    self.relayout()

  def relayout(self):
    w = max(60, self.viewport().width() - 26)
    h = round(w * self.aspect)
    cell = QSize(w + 16, h + 34)
    self.setIconSize(QSize(w, h))
    self.setGridSize(cell)
    # 明確指定項目大小：否則 Qt 會沿用「還沒有圖示時」算出的位置，縮圖會偏移
    for i in range(self.count()):
      self.item(i).setSizeHint(cell)
    self.doItemsLayout()

  def resizeEvent(self, e):
    super().resizeEvent(e)
    self.relayout()


def _load_view_settings(qs: QSettings) -> ViewSettings:
  raw = qs.value("view_settings", "")
  try:
    d = json.loads(raw) if raw else {}
    vec = VectorParams(**d.pop("vector", {}))
    return ViewSettings(vector=vec, **d)
  except (TypeError, ValueError):
    return ViewSettings()


def _backup(path: Path, tag: str) -> Path:
  dst = path.with_name(f"{path.name}.{tag}-{datetime.now():%Y%m%d-%H%M%S}")
  os.replace(path, dst)
  return dst


def _panel(*widgets, stretch_first=False) -> QFrame:
  f = QFrame()
  f.setObjectName("SidePanel")
  lay = QVBoxLayout(f)
  lay.setContentsMargins(4, 4, 4, 4)
  lay.setSpacing(0)
  for i, w in enumerate(widgets):
    lay.addWidget(w, 1 if (stretch_first and i == 0) else 0)
  return f


class MainWindow(OutputActionsMixin, QMainWindow):
  def __init__(self):
    super().__init__()
    self.qs = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                        SETTINGS_ORG, SETTINGS_ORG)
    self.doc: DrawingDocument | None = None
    self.ctl = MarkController(self)
    self.view = pv.PageView(self.ctl)
    self.view.checker = str(self.qs.value("checker", "")) or default_marker()
    self.setAcceptDrops(True)
    self.setWindowIcon(QIcon(str(resource_path("app_icon.png"))))

    self._build_actions()
    self._build_layout()
    self._connect()

    self.autosave = QTimer(self)
    self.autosave.setInterval(AUTOSAVE_MS)
    self.autosave.timeout.connect(self._autosave)
    self.autosave.start()

    self.resize(1500, 920)
    geo = self.qs.value("geometry")
    if geo:
      self.restoreGeometry(geo)
    split = self.qs.value("splitter")
    if split:
      self.splitter.restoreState(split)
    self.ribbon.set_current(int(self.qs.value("ribbon_tab", 0)))
    self.left_side.set_collapsed(self.qs.value("left_collapsed", "false") == "true")
    self.right_side.set_collapsed(self.qs.value("right_collapsed", "false") == "true")
    theme.dark_title_bar(self)
    self._apply_settings(self.enhance_panel.settings())
    self._update_title()
    self._update_doc_actions()

  # ---- 動作 ----
  def _act(self, text, icon_name=None, slot=None, shortcut=None, checkable=False,
           tip=None) -> QAction:
    a = QAction(text, self)
    if icon_name:
      a.setIcon(icons.icon(icon_name))
    if shortcut:
      a.setShortcuts(shortcut if isinstance(shortcut, list) else [QKeySequence(shortcut)])
    if slot:
      a.triggered.connect(slot)
    a.setCheckable(checkable)
    keys = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
    a.setToolTip(f"{tip or text}（{keys}）" if keys else (tip or text))
    self.addAction(a)
    return a

  def _build_actions(self):
    A = self._act
    self.a_open = A("開啟", "open", self.open_dialog, QKeySequence.StandardKey.Open, tip="開啟 PDF")
    self.a_recent = A("最近檔案", "recent", tip="最近開啟過的檔案")
    self.a_save = A("儲存", "save", self.save_marks, QKeySequence.StandardKey.Save,
                    tip="儲存核對標記（不會修改 PDF）")
    self.a_export = A("匯出清單", "export_list", self.export_dialog, "Ctrl+E",
                      tip="匯出核對清單 xlsx / csv")
    self.a_export_pdf = A("匯出標記PDF", "pdf_out", lambda: self.export_marked(ALL_PDF),
                          "Ctrl+Shift+E", tip="輸出含標記與書籤的 PDF（不修改原檔）")
    self.a_save_page = A("存標記頁面", "save_page", lambda: self.export_marked(PAGE_PDF),
                         "Ctrl+Shift+S", tip="本頁或全部頁存成 PDF / PNG（含標記）")
    self.a_print = A("列印", "print", self.print_marked, QKeySequence.StandardKey.Print,
                     tip="列印含標記的圖面")

    self.a_fit = A("適合頁面", "fit_page", self.view.fit_page, "F")
    self.a_fit_w = A("適合頁寬", "fit_width", self.view.fit_width, "W")
    self.a_actual = A("實際大小", "actual", lambda: self.view.set_zoom_percent(100), "Ctrl+0")
    self.a_zoom_in = A("放大", "zoom_in", lambda: self.view.zoom_by(1.25),
                       [QKeySequence.StandardKey.ZoomIn, QKeySequence("Ctrl+=")])
    self.a_zoom_out = A("縮小", "zoom_out", lambda: self.view.zoom_by(0.8),
                        QKeySequence.StandardKey.ZoomOut)
    self.a_full = A("全螢幕", "fullscreen", self.toggle_fullscreen, "F11", checkable=True)

    group = QActionGroup(self)
    self.tool_actions: dict[str, QAction] = {}
    for tool, text, icon_name, key, tip in (
      (pv.TOOL_PAN, "平移", "pan", "H", "拖曳平移圖面"),
      (pv.TOOL_SELECT, "選取", "select", "V", "選取 / 移動標記，拖曳空白處可框選多個"),
      (pv.TOOL_OK, "OK", "stamp_ok", "C", "點一下放置 OK 戳記"),
      (pv.TOOL_NG, "NG", "stamp_ng", "X", "點一下放置 NG 戳記"),
      (pv.TOOL_PENDING, "待確認", "stamp_pending", "Q", "點一下放置待確認戳記"),
      (pv.TOOL_RECT, "框選", "rect", "R", "拖曳框住尺寸，建立後按 1/2/3 設定狀態"),
      (pv.TOOL_ELLIPSE, "圈選", "ellipse", "E", "拖曳圈住尺寸，建立後按 1/2/3 設定狀態"),
      (pv.TOOL_TEXT, "文字", "text", "T", "點一下放置文字框，可設定格式與連結"),
      (pv.TOOL_SNAP, "截圖", "snapshot", "S",
       "先出現框線，可移動 / 調整大小 / 重新框選，再選擇複製到剪貼簿或另存 PNG"),
    ):
      a = A(text, icon_name, lambda _=False, t=tool: self.view.set_tool(t), key, True, tip)
      group.addAction(a)
      self.tool_actions[tool] = a
    self.tool_actions[pv.TOOL_SELECT].setChecked(True)

    stack = self.ctl.undo_stack
    self.a_undo = A("復原", "undo", stack.undo, QKeySequence.StandardKey.Undo)
    self.a_redo = A("重做", "redo", stack.redo,
                    [QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Shift+Z")])
    self.a_undo.setEnabled(False)
    self.a_redo.setEnabled(False)
    stack.canUndoChanged.connect(self.a_undo.setEnabled)
    stack.canRedoChanged.connect(self.a_redo.setEnabled)
    stack.undoTextChanged.connect(lambda t: self.a_undo.setToolTip(f"復原：{t}" if t else "復原"))
    stack.redoTextChanged.connect(lambda t: self.a_redo.setToolTip(f"重做：{t}" if t else "重做"))

    self.a_none = A("設為無狀態", None, lambda: self.set_selected_status(STATUS_NONE), "0")
    self.a_ok = A("設為 OK", None, lambda: self.set_selected_status(STATUS_OK), "1")
    self.a_ng = A("設為 NG", None, lambda: self.set_selected_status(STATUS_NG), "2")
    self.a_pending = A("設為待確認", None, lambda: self.set_selected_status(STATUS_PENDING), "3")
    self.a_edit = A("編輯內容…", None, self.edit_selected, "Return")
    self.a_delete = A("刪除", None, self.delete_selected, QKeySequence.StandardKey.Delete)
    self.a_open_link = A("開啟連結", "link", self._open_selected_link)

    self.a_settings = A("設定", "settings", self.open_settings, "Ctrl+,")
    self.a_help = A("說明", "help", self.open_help, "F1")
    A("深色模式", None, lambda: self.enhance_panel.toggle_dark(), "D")
    A("上一頁", None, lambda: self.view.set_page(self.view.pno - 1), "PgUp")
    A("下一頁", None, lambda: self.view.set_page(self.view.pno + 1), "PgDown")
    A("搜尋", None, self.focus_search, QKeySequence.StandardKey.Find)

    self.recent_menu = QMenu(self)
    self.recent_menu.aboutToShow.connect(self._fill_recent)

  # ---- 版面 ----
  def _build_layout(self):
    self.ribbon = ribbon = Ribbon()
    g = ribbon.page("檔案")
    g.add(self.a_open)
    g.add(self.a_recent, self.recent_menu)
    g.add(self.a_save)
    g.add(self.a_export)
    g.add_separator()
    g.add(self.a_export_pdf)
    g.add(self.a_save_page)
    g.add(self.a_print)
    g = ribbon.page("檢視")
    for a in (self.a_fit, self.a_fit_w, self.a_actual, self.a_zoom_in, self.a_zoom_out, self.a_full):
      g.add(a)
    g = ribbon.page("工具")
    g.add(self.tool_actions[pv.TOOL_PAN])
    g.add(self.tool_actions[pv.TOOL_SELECT])
    g.add(self.tool_actions[pv.TOOL_SNAP])
    g = ribbon.page("審查")
    for t in (pv.TOOL_OK, pv.TOOL_NG, pv.TOOL_PENDING, pv.TOOL_RECT, pv.TOOL_ELLIPSE,
              pv.TOOL_TEXT):
      g.add(self.tool_actions[t])
    g.add_separator()
    g.add(self.a_undo)
    g.add(self.a_redo)
    g = ribbon.page("設定")
    g.add(self.a_settings)
    g.add(self.a_help)
    ribbon.currentChanged.connect(lambda i: self.qs.setValue("ribbon_tab", i))

    self.thumbs = ThumbList()
    self.left_tabs = QTabWidget()
    self.left_tabs.addTab(self.thumbs, "縮圖")
    left_collapse = collapse_button("left")
    self.left_tabs.setCornerWidget(left_collapse, Qt.Corner.TopRightCorner)
    self._thumb_timer = QTimer(self)
    self._thumb_timer.timeout.connect(self._render_next_thumb)

    self.enhance_panel = EnhancePanel(_load_view_settings(self.qs))
    left = QWidget()
    ll = QVBoxLayout(left)
    ll.setContentsMargins(0, 0, 0, 0)
    ll.setSpacing(8)
    ll.addWidget(_panel(self.left_tabs), 1)
    ll.addWidget(_panel(self.enhance_panel))
    self.left_side = CollapsibleSide("left", left)
    self.left_side.add_section("thumbs", "縮圖",
                               lambda: self.left_tabs.setCurrentWidget(self.thumbs))
    self.left_side.add_section("enhance", "影像增強",
                               lambda: self.enhance_panel.header.setChecked(True))
    left_collapse.clicked.connect(self.left_side.collapse)

    self.info_panel = InfoPanel()
    self.marks_panel = MarksPanel(self.ctl)
    self.search_panel = SearchPanel()
    self.right_tabs = QTabWidget()
    self.right_tabs.setIconSize(QSize(15, 15))
    self.right_tabs.setUsesScrollButtons(False)
    self.right_tabs.setElideMode(Qt.TextElideMode.ElideRight)
    self.right_tabs.addTab(self.info_panel, icons.icon("info", "#ffffff"), "屬性資訊")
    self.right_tabs.addTab(self.marks_panel, icons.icon("list", "#ffffff"), "核對標記")
    self.right_tabs.addTab(self.search_panel, icons.icon("search", "#ffffff"), "搜尋")
    right_collapse = collapse_button("right")
    self.right_tabs.setCornerWidget(right_collapse, Qt.Corner.TopRightCorner)
    self.right_side = CollapsibleSide("right", _panel(self.right_tabs, stretch_first=True))
    for icon_name, tip, page in (("info", "屬性資訊", self.info_panel),
                                 ("list", "核對標記", self.marks_panel),
                                 ("search", "搜尋", self.search_panel)):
      self.right_side.add_section(icon_name, tip,
                                  lambda p=page: self.right_tabs.setCurrentWidget(p))
    right_collapse.clicked.connect(self.right_side.collapse)

    self.splitter = QSplitter(Qt.Orientation.Horizontal)
    self.splitter.setHandleWidth(8)
    for w in (self.left_side, self.view, self.right_side):
      self.splitter.addWidget(w)
    self.splitter.setStretchFactor(1, 1)
    for i in range(3):
      self.splitter.setCollapsible(i, False)
    self.splitter.setSizes([290, 850, 380])
    self._side_widths = {"left": 290, "right": 380}
    self.left_side.collapsedChanged.connect(lambda c: self._on_side_collapsed(self.left_side, c))
    self.right_side.collapsedChanged.connect(lambda c: self._on_side_collapsed(self.right_side, c))

    self.bottom = BottomBar()
    central = QWidget()
    cl = QVBoxLayout(central)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    cl.addWidget(ribbon)
    body = QVBoxLayout()
    body.setContentsMargins(10, 10, 10, 8)
    body.addWidget(self.splitter)
    cl.addLayout(body, 1)
    cl.addWidget(self.bottom)
    self.setCentralWidget(central)

  def _on_side_collapsed(self, side: CollapsibleSide, collapsed: bool):
    idx = self.splitter.indexOf(side)
    sizes = self.splitter.sizes()
    if collapsed:
      if sizes[idx] > STRIP_W:
        self._side_widths[side.side] = sizes[idx]
      target = STRIP_W
    else:
      target = self._side_widths.get(side.side, 300)
    sizes[1] += sizes[idx] - target
    sizes[idx] = target
    self.splitter.setSizes(sizes)
    self.qs.setValue(f"{side.side}_collapsed", "true" if collapsed else "false")

  def _connect(self):
    v = self.view
    v.zoomChanged.connect(lambda _s: self.bottom.set_zoom_percent(v.zoom_percent()))
    v.pageChanged.connect(self._on_page_changed)
    v.selectionChangedIds.connect(self.marks_panel.select_ids)
    v.editRequested.connect(self.edit_mark)
    v.contextMenuRequested.connect(self._mark_menu)
    v.toolMenuRequested.connect(self._tool_menu)
    v.escapePressed.connect(lambda: self.select_tool(pv.TOOL_SELECT))
    v.textPlaceRequested.connect(self.on_text_place)
    v.snapshotRequested.connect(self.on_snapshot)
    v.snapshotCancelled.connect(self.end_snapshot_tool)
    v.linkActivated.connect(self.open_mark_link)
    self.marks_panel.markActivated.connect(v.focus_mark)
    self.marks_panel.editRequested.connect(self.edit_mark)
    self.search_panel.hitsChanged.connect(v.set_search_hits)
    self.search_panel.hitActivated.connect(lambda i, _p: v.focus_hit(i))
    self.enhance_panel.settingsChanged.connect(self._apply_settings)
    self.ctl.dirtyChanged.connect(lambda _d: self._update_title())
    self.thumbs.currentRowChanged.connect(lambda r: r >= 0 and v.set_page(r))
    b = self.bottom
    b.pageRequested.connect(v.set_page)
    b.zoomPercentRequested.connect(v.set_zoom_percent)
    b.zoomStep.connect(v.zoom_by)
    b.fitPage.connect(v.fit_page)
    b.fitWidth.connect(v.fit_width)

  def msg(self, text: str, ms: int = 4000):
    self.bottom.show_message(text, ms)

  # ---- 檔案 ----
  def open_dialog(self):
    start = str(self.qs.value("last_dir", ""))
    path, _ = QFileDialog.getOpenFileName(self, "開啟圖面", start, "PDF (*.pdf)")
    if path:
      self.open_pdf(path)

  def open_pdf(self, path: str):
    if self.doc and self.ctl.dirty and not self.save_marks():
      return
    try:
      doc = DrawingDocument(path)
    except Exception as ex:
      QMessageBox.critical(self, APP_NAME, f"無法開啟檔案：\n{path}\n\n{ex}")
      self._remove_recent(path)
      return
    marks = self._load_sidecar(doc)
    if marks is None:
      doc.close()
      return
    if self.doc:
      self.doc.close()
    self.doc = doc
    doc.set_settings(self.enhance_panel.settings())
    self.qs.setValue("last_dir", str(Path(path).parent))
    self._add_recent(str(Path(path).resolve()))
    self.ctl.load(marks)
    self.view.set_document(doc)
    self.info_panel.set_document(doc)
    self.search_panel.set_document(doc)
    self.bottom.set_pages(0, doc.page_count)
    self._start_thumbs()
    self._update_title()
    self._update_doc_actions()
    self.msg(f"已開啟 {doc.path.name}，載入 {len(marks)} 個標記", 5000)

  def _load_sidecar(self, doc: DrawingDocument):
    """回傳標記清單；使用者取消時回傳 None。"""
    side = sidecar_path(doc.path)
    try:
      res = load_marks(doc.path, doc.sha256)
    except SidecarError as ex:
      bak = _backup(side, "corrupt")
      QMessageBox.warning(self, APP_NAME, f"{ex}\n\n原檔已備份為：\n{bak.name}\n將以空白標記開始。")
      return []
    if not res.hash_mismatch:
      return res.marks
    box = QMessageBox(self)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("圖面可能已改版")
    box.setText(f"「{doc.path.name}」與標記檔建立時的內容不同，"
                f"可能已改版。\n已有 {len(res.marks)} 個標記，位置可能不正確。")
    keep = box.addButton("仍然載入標記", QMessageBox.ButtonRole.AcceptRole)
    fresh = box.addButton("備份舊標記，重新開始", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is keep:
      return res.marks
    if box.clickedButton() is fresh:
      bak = _backup(side, "old")
      self.msg(f"舊標記已備份為 {bak.name}", 8000)
      return []
    return None

  def save_marks(self) -> bool:
    if not self.doc:
      return True
    try:
      path = save_marks(self.doc.path, self.doc.sha256, self.ctl.marks())
    except OSError as ex:
      QMessageBox.critical(self, APP_NAME, f"標記儲存失敗：\n{ex}")
      return False
    self.ctl.set_dirty(False)
    self.msg(f"標記已儲存：{path.name}")
    return True

  def _autosave(self):
    if self.doc and self.ctl.dirty:
      try:
        save_marks(self.doc.path, self.doc.sha256, self.ctl.marks())
        self.ctl.set_dirty(False)
        self.msg("已自動儲存標記", 3000)
      except OSError as ex:
        self.msg(f"自動儲存失敗：{ex}", 8000)

  def export_dialog(self):
    if not self.doc:
      return
    default = str(self.doc.path.with_name(f"{self.doc.path.stem}_核對清單.xlsx"))
    path, flt = QFileDialog.getSaveFileName(self, "匯出核對清單", default,
                                            "Excel (*.xlsx);;CSV (*.csv)")
    if not path:
      return
    as_csv = path.lower().endswith(".csv") or ("CSV" in flt and not path.lower().endswith(".xlsx"))
    try:
      if as_csv:
        path = path if path.lower().endswith(".csv") else path + ".csv"
        export_csv(path, self.ctl.marks())
      else:
        export_xlsx(path, self.ctl.marks(), self.doc.path.name)
    except OSError as ex:
      QMessageBox.critical(self, APP_NAME, f"匯出失敗（檔案是否正在 Excel 中開啟？）：\n{ex}")
      return
    self.msg(f"已匯出：{path}", 5000)

  # ---- 最近檔案 ----
  def _recent(self) -> list[str]:
    v = self.qs.value("recent", [])
    return [v] if isinstance(v, str) else list(v or [])

  def _add_recent(self, path: str):
    items = [p for p in self._recent() if os.path.normcase(p) != os.path.normcase(path)]
    self.qs.setValue("recent", [path, *items][:MAX_RECENT])

  def _remove_recent(self, path: str):
    self.qs.setValue("recent", [p for p in self._recent()
                                if os.path.normcase(p) != os.path.normcase(path)])

  def _fill_recent(self):
    m = self.recent_menu
    m.clear()
    items = self._recent()
    if not items:
      m.addAction("（沒有最近檔案）").setEnabled(False)
      return
    for p in items:
      a = m.addAction(icons.icon("file"), Path(p).name)
      a.setToolTip(p)
      a.setEnabled(os.path.exists(p))
      a.triggered.connect(lambda _=False, p=p: self.open_pdf(p))
    m.addSeparator()
    m.addAction("清除清單").triggered.connect(lambda: self.qs.setValue("recent", []))

  # ---- 標記操作 ----
  def set_selected_status(self, status: str):
    ids = self.view.selected_ids()
    if ids:
      sign = self.view.checker and status != STATUS_NONE
      self.ctl.update_marks(ids, "變更狀態", status=status,
                            **({"checker": self.view.checker} if sign else {}))

  def delete_selected(self):
    self.ctl.delete_marks(self.view.selected_ids())

  def edit_selected(self):
    ids = self.view.selected_ids()
    if len(ids) == 1:
      self.edit_mark(ids[0])

  def edit_mark(self, mid: str):
    m = self.ctl.get(mid)
    if not m:
      return
    if self.is_text_mark(mid):
      self.edit_text_mark(mid)
      return
    dlg = MarkEditDialog(m, self)
    theme.dark_title_bar(dlg)
    if dlg.exec():
      self.ctl.update_marks([mid], "編輯標記", **dlg.values())

  def _add_mark_actions(self, m: QMenu, ids: list):
    for a, ic in ((self.a_none, "status_none"), (self.a_ok, "stamp_ok"), (self.a_ng, "stamp_ng"),
                  (self.a_pending, "stamp_pending")):
      a.setIcon(icons.icon(ic))
      m.addAction(a)
    m.addSeparator()
    self.a_edit.setEnabled(len(ids) == 1)
    m.addAction(self.a_edit)
    one = self.ctl.get(ids[0]) if len(ids) == 1 else None
    if one and one.link:
      m.addAction(self.a_open_link)
    m.addAction(self.a_delete)

  def _mark_menu(self, ids: list, pos):
    m = QMenu(self)
    self._add_mark_actions(m, ids)
    m.exec(pos)
    self.a_edit.setEnabled(True)

  def _tool_menu(self, ids: list, pos):
    """審查工具中按右鍵：快速切換工具；游標下有標記時附上標記操作。"""
    m = QMenu(self)
    m.addAction(self.tool_actions[pv.TOOL_SELECT])
    m.addSeparator()
    for t in pv.REVIEW_TOOLS:
      m.addAction(self.tool_actions[t])
    if ids:
      m.addSeparator()
      self._add_mark_actions(m, ids)
    m.exec(pos)
    self.a_edit.setEnabled(True)

  def select_tool(self, tool: str):
    self.tool_actions[tool].setChecked(True)
    self.view.set_tool(tool)

  def _open_selected_link(self):
    ids = self.view.selected_ids()
    m = self.ctl.get(ids[0]) if len(ids) == 1 else None
    if m and m.link:
      self.open_mark_link(m.link)

  # ---- 設定 / 說明 / 搜尋 ----
  def open_settings(self):
    dlg = SettingsDialog(str(self.qs.value("checker", "")), self.doc.path if self.doc else None,
                         self)
    theme.dark_title_bar(dlg)
    if dlg.exec():
      name = dlg.checker_name()
      self.qs.setValue("checker", name)  # 留空＝使用電腦使用者
      self.view.checker = name or default_marker()

  def open_help(self):
    dlg = HelpDialog(APP_FULL_NAME, VERSION, self)
    theme.dark_title_bar(dlg)
    dlg.exec()

  def focus_search(self):
    self.right_tabs.setCurrentWidget(self.search_panel)
    self.search_panel.edit.setFocus()
    self.search_panel.edit.selectAll()

  def toggle_fullscreen(self):
    if self.isFullScreen():
      self.showNormal()
    else:
      self.showFullScreen()
    self.a_full.setChecked(self.isFullScreen())

  # ---- 顯示 ----
  def _apply_settings(self, s: ViewSettings):
    self.qs.setValue("view_settings", json.dumps(asdict(s)))
    self.view.set_dark(s.dark)
    if self.doc:
      self.doc.set_settings(s)
      self.view.refresh_render()
      if s.mode == "vector" and self.doc.is_vector_failed(self.view.pno):
        self.msg("此頁向量解析失敗，已改用點陣加粗", 6000)

  def _on_page_changed(self, pno: int):
    self.bottom.set_pages(pno, self.doc.page_count if self.doc else 0)
    self.thumbs.blockSignals(True)
    self.thumbs.setCurrentRow(pno)
    self.thumbs.blockSignals(False)
    if self.thumbs.item(pno):
      self.thumbs.scrollToItem(self.thumbs.item(pno))
    self.marks_panel.set_page(pno)

  def _start_thumbs(self):
    self.thumbs.clear()
    self._thumb_next = 0
    for i in range(self.doc.page_count):
      it = QListWidgetItem(f"{i + 1}")
      it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
      self.thumbs.addItem(it)
    r = self.doc.page_rect(0)
    self.thumbs.set_aspect(r.height / max(r.width, 1))
    self.thumbs.blockSignals(True)
    self.thumbs.setCurrentRow(0)
    self.thumbs.blockSignals(False)
    self._thumb_timer.start(0)

  def _render_next_thumb(self):
    if not self.doc or self._thumb_next >= self.doc.page_count:
      self._thumb_timer.stop()
      return
    i = self._thumb_next
    self._thumb_next += 1
    page = self.doc.base[i]
    z = THUMB_RENDER_PX / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=(z, 0, 0, z, 0, 0), alpha=False)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
    pm = to_pixmap(img.reshape(pix.height, pix.width, 3).copy())
    ic = QIcon(pm)
    ic.addPixmap(pm, QIcon.Mode.Selected)
    self.thumbs.item(i).setIcon(ic)

  def _update_title(self):
    name = self.doc.path.name if self.doc else ""
    star = "*" if self.ctl.dirty else ""
    base = f"{APP_FULL_NAME}  v{VERSION}"
    self.setWindowTitle(f"{name}{star} - {base}" if name else base)

  # ---- 事件 ----
  def _update_doc_actions(self):
    on = self.doc is not None
    for a in (self.a_save, self.a_export, self.a_export_pdf, self.a_save_page, self.a_print):
      a.setEnabled(on)

  def keyPressEvent(self, e):
    if e.key() == Qt.Key.Key_Escape:
      # 先回到選取工具；已經是選取工具時，才離開全螢幕
      if self.view.tool != pv.TOOL_SELECT:
        self.select_tool(pv.TOOL_SELECT)
        return
      if self.isFullScreen():
        self.toggle_fullscreen()
        return
    super().keyPressEvent(e)

  def dragEnterEvent(self, e):
    if any(u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()):
      e.acceptProposedAction()

  def dropEvent(self, e):
    for u in e.mimeData().urls():
      if u.toLocalFile().lower().endswith(".pdf"):
        self.open_pdf(u.toLocalFile())
        break

  def closeEvent(self, e):
    if self.doc and self.ctl.dirty and not self.save_marks():
      ans = QMessageBox.question(self, APP_NAME, "標記尚未儲存，仍要關閉嗎？")
      if ans != QMessageBox.StandardButton.Yes:
        e.ignore()
        return
    if not self.isFullScreen():
      self.qs.setValue("geometry", self.saveGeometry())
    self.qs.setValue("splitter", self.splitter.saveState())
    super().closeEvent(e)
