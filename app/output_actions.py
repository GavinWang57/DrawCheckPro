"""主視窗的輸出相關動作：標記 PDF / PNG、列印、截圖、文字標記。以 mixin 掛到 MainWindow。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.marks import pdf_export
from app.marks.model import KIND_TEXT
from app.marks.text_dialog import TextMarkDialog, open_link
from app.printing import print_marked
from app.ui import theme
from app.viewer import page_view as pv
from app.viewer.snapshot_overlay import ACTION_COPY
from app.ui.output_dialog import (ALL_PDF, ALL_PNG, PAGE_PDF, PAGE_PNG, SCOPE_ALL, SCOPE_PAGE,
                                  OutputDialog, PrintOptionsDialog, SelectedExportDialog)

MAX_PNG_PIXELS = pdf_export.MAX_STITCH_PIXELS


class _Busy:
  def __enter__(self):
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

  def __exit__(self, *exc):
    QApplication.restoreOverrideCursor()


class OutputActionsMixin:
  # 以下屬性由 MainWindow 提供：doc, ctl, view, qs, msg(), _act()

  def _out_dir(self) -> Path:
    return Path(str(self.qs.value("export_dir", ""))) if self.qs.value("export_dir") \
      else self.doc.path.parent

  def _ask_save(self, title: str, name: str, flt: str) -> str:
    path, _ = QFileDialog.getSaveFileName(self, title, str(self._out_dir() / name), flt)
    if path:
      self.qs.setValue("export_dir", str(Path(path).parent))
    return path

  # ---- 標記 PDF / PNG ----
  def export_marked(self, preset: str = ALL_PDF):
    if not self.doc:
      return
    dlg = OutputDialog(preset, self.view.pno, self.doc.page_count,
                       self.qs.value("export_enhanced", "false") == "true", self)
    theme.dark_title_bar(dlg)
    if not dlg.exec():
      return
    choice, enhanced, dpi = dlg.choice(), dlg.enhanced.isChecked(), dlg.dpi.currentData()
    self.qs.setValue("export_enhanced", "true" if enhanced else "false")
    pno, stem = self.view.pno, self.doc.path.stem
    pages = [pno] if choice in (PAGE_PDF, PAGE_PNG) else list(range(self.doc.page_count))
    if choice in (PAGE_PDF, ALL_PDF):
      name = f"{stem}_標記_p{pno + 1}.pdf" if choice == PAGE_PDF else f"{stem}_標記.pdf"
      path = self._ask_save("輸出含標記的 PDF", name, "PDF (*.pdf)")
      if path:
        self._run_export(lambda: pdf_export.save_pdf(self.doc, self.ctl.marks(), pages, enhanced,
                                                     path), path)
      return
    if pdf_export.estimate_pixels(self.doc, pages, dpi) > MAX_PNG_PIXELS:
      QMessageBox.warning(self, "圖片太大", "以這個解析度合併後的圖片太大，請降低 PNG 解析度。")
      return
    name = f"{stem}_標記_p{pno + 1}.png" if choice == PAGE_PNG else f"{stem}_標記_全部頁.png"
    path = self._ask_save("輸出含標記的 PNG", name, "PNG (*.png)")
    if path:
      def work():
        imgs = pdf_export.render_images(self.doc, self.ctl.marks(), pages, enhanced, dpi)
        img = imgs[0] if len(imgs) == 1 else pdf_export.stitch_vertical(imgs)
        pdf_export.save_png(img, path)
      self._run_export(work, path)

  def export_selected_marks(self, ids: list[str]):
    marks = [m for m in (self.ctl.get(i) for i in ids) if m]
    if not self.doc or not marks:
      return
    marked_pages = sorted({m.page for m in marks})
    dlg = SelectedExportDialog(len(marks), len(marked_pages), self.doc.page_count,
                               self.qs.value("export_enhanced", "false") == "true",
                               self.focused_parent())
    theme.dark_title_bar(dlg)
    if not dlg.exec():
      return
    enhanced = dlg.enhanced.isChecked()
    self.qs.setValue("export_enhanced", "true" if enhanced else "false")
    pages = list(range(self.doc.page_count)) if dlg.scope() == SCOPE_ALL else marked_pages
    path = self._ask_save("輸出選取標記的 PDF", f"{self.doc.path.stem}_標記_選取.pdf",
                          "PDF (*.pdf)")
    if path:
      self._run_export(lambda: pdf_export.save_pdf(self.doc, marks, pages, enhanced, path), path)

  def focused_parent(self):
    """標記管理視窗開著時，對話框以它為 parent，才不會被它擋住。"""
    mgr = getattr(self, "mark_manager", None)
    return mgr if mgr is not None and mgr.isVisible() else self

  def _run_export(self, work, path: str):
    try:
      with _Busy():
        work()
    except (OSError, ValueError, RuntimeError) as ex:
      QMessageBox.critical(self, "輸出失敗", f"{ex}")
      return
    self.msg(f"已輸出：{path}", 6000)

  # ---- 列印 ----
  def print_marked(self):
    if not self.doc:
      return
    dlg = PrintOptionsDialog(self.view.pno, self.doc.page_count,
                             self.qs.value("export_enhanced", "false") == "true", self)
    theme.dark_title_bar(dlg)
    if not dlg.exec():
      return
    pages = [self.view.pno] if dlg.scope() == SCOPE_PAGE else list(range(self.doc.page_count))
    try:
      with _Busy():
        done = print_marked(self, self.doc, self.ctl.marks(), pages, dlg.enhanced.isChecked(),
                            self.doc.path.name)
    except RuntimeError as ex:
      QMessageBox.critical(self, "列印失敗", str(ex))
      return
    if done:
      self.msg(f"已送出列印：{len(pages)} 頁", 5000)

  # ---- 截圖 ----
  def on_snapshot(self, rect: QRectF, action: str):
    with _Busy():
      img = self.view.render_snapshot(rect)
    self.end_snapshot_tool()
    if img.isNull():
      return
    if action == ACTION_COPY:
      QGuiApplication.clipboard().setImage(img)
      self.msg(f"截圖已複製到剪貼簿（{img.width()}×{img.height()}）", 4000)
    else:
      self.save_snapshot(img)

  def end_snapshot_tool(self):
    """截圖完成或取消後回到選取工具。"""
    self.select_tool(pv.TOOL_SELECT)

  def save_snapshot(self, img: QImage):
    name = f"{self.doc.path.stem}_截圖_p{self.view.pno + 1}.png"
    path = self._ask_save("另存截圖", name, "PNG (*.png)")
    if not path:
      return
    if not path.lower().endswith(".png"):
      path += ".png"
    if img.save(path, "PNG"):
      self.msg(f"截圖已儲存：{path}", 5000)
    else:
      QMessageBox.critical(self, "儲存失敗", f"無法寫入：{path}")

  # ---- 文字標記 ----
  def on_text_place(self, pos: QPointF):
    style = {"font_size": self.view.default_text_font_pt(), **self._last_text_style()}
    dlg = TextMarkDialog(style=style, checker=self.view.checker, title="新增文字標記", parent=self,
                         font_unit=self._text_font_unit())
    theme.dark_title_bar(dlg)
    if dlg.exec():
      values = dlg.values()
      self._remember_text_style(values["style"], dlg.unit())
      self.view.create_text_mark(pos, values)

  def edit_text_mark(self, mid: str):
    m = self.ctl.get(mid)
    dlg = TextMarkDialog(m.text, m.style, m.link, m.status, m.checker,
                         f"文字標記 #{m.no}（第 {m.page + 1} 頁）", self,
                         font_unit=self._text_font_unit())
    theme.dark_title_bar(dlg)
    if not dlg.exec():
      return
    v = dlg.values()
    self._remember_text_style(v["style"], dlg.unit())
    if m.page == self.view.pno:
      v["rect"] = self.view.resized_text_rect(m, v["text"], v["style"])
    self.ctl.update_marks([mid], "編輯文字標記", **v)

  _BOOL_STYLE = ("bold", "italic", "strike")
  _STR_STYLE = ("text_color", "fill_color", "border_color", "underline")

  def _last_text_style(self) -> dict:
    """沿用上次的格式（字級除外，字級依目前縮放決定）。"""
    out = {}
    for k in (*self._BOOL_STYLE, *self._STR_STYLE, "border_width"):
      v = self.qs.value(f"text_style/{k}")
      if v is None:
        continue
      if k in self._BOOL_STYLE:
        out[k] = v == "true"
      elif k == "border_width":
        out[k] = float(v)
      else:
        out[k] = str(v)
    return out

  def _text_font_unit(self) -> str:
    return str(self.qs.value("text_font_unit", "pt"))

  def _remember_text_style(self, style: dict, unit: str = "pt"):
    self.qs.setValue("text_font_unit", unit)
    for k, v in style.items():
      if k == "font_size":
        continue
      self.qs.setValue(f"text_style/{k}", ("true" if v else "false") if k in self._BOOL_STYLE else v)

  def open_mark_link(self, link: str):
    if not open_link(link):
      self.msg(f"無法開啟連結：{link}", 6000)

  def is_text_mark(self, mid: str) -> bool:
    m = self.ctl.get(mid)
    return bool(m) and m.kind == KIND_TEXT
