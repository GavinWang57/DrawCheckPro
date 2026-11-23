"""深藍色主題（依 UI/UX 設計圖）。"""
from __future__ import annotations

import ctypes
import hashlib
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from app.ui import icons

BG = "#0a1628"
BG_BAR = "#0c1c33"
PANEL = "#0e1f37"
CARD = "#112745"
BORDER = "#1e3a5f"
BORDER_HI = "#2d5a8c"
TEXT = "#e3ecf7"
MUTED = "#8fa6c4"
ACCENT = "#1e88e5"
ACCENT_HI = "#42a5f5"
CANVAS = "#16263c"
CANVAS_DARK = "#0b1422"


def _asset_dir() -> Path:
  """QSS 的 image: url() 只吃檔案路徑，所以把勾選框等小圖示寫到暫存資料夾。"""
  assets = {
    "check.svg": icons.svg("check", "#ffffff", 3),
    "down.svg": icons.svg("chevron_down", MUTED, 2.2),
    "up.svg": icons.svg("chevron_up", MUTED, 2.2),
  }
  key = hashlib.sha1("".join(assets.values()).encode()).hexdigest()[:10]
  d = Path(tempfile.gettempdir()) / f"drawing_checker_ui_{key}"
  d.mkdir(exist_ok=True)
  for name, content in assets.items():
    f = d / name
    if not f.exists():
      f.write_text(content, encoding="utf-8")
  return d


def stylesheet() -> str:
  a = _asset_dir().as_posix()
  return f"""
* {{ color: {TEXT}; font-family: "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI", "Segoe UI Symbol"; font-size: 13px; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER_HI}; padding: 4px; }}

#Ribbon {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f2440, stop:1 {BG_BAR});
          border-bottom: 1px solid {BORDER}; }}
#RibbonGroup {{ background: rgba(20, 45, 80, 0.55); border: 1px solid {BORDER}; border-radius: 6px; }}
#RibbonGroupTitle {{ color: {MUTED}; font-size: 12px; font-weight: bold; }}
#RibbonGroup QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 5px;
                           padding: 3px 4px; min-width: 50px; font-size: 13px; }}
#RibbonGroup QToolButton:hover {{ background: rgba(66, 165, 245, 0.16); border-color: {BORDER_HI}; }}
#RibbonGroup QToolButton:pressed {{ background: rgba(66, 165, 245, 0.30); }}
#RibbonGroup QToolButton:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                   stop:0 #2b8ef0, stop:1 #1565c0); border-color: {ACCENT_HI}; }}
#RibbonGroup QToolButton:disabled {{ color: #4d6380; }}
#RibbonGroup QToolButton::menu-indicator {{ image: none; width: 0; }}
#RibbonSep {{ background: {BORDER}; margin: 6px 6px; }}
QTabBar#RibbonTabs::tab {{ background: transparent; color: {MUTED}; padding: 4px 16px; margin-right: 4px;
  border: 1px solid transparent; border-radius: 4px; font-size: 13px; font-weight: bold; }}
QTabBar#RibbonTabs::tab:selected {{ color: white; background: rgba(30, 136, 229, 0.35);
  border-color: {BORDER_HI}; }}
QTabBar#RibbonTabs::tab:hover:!selected {{ color: {TEXT}; background: rgba(66,165,245,0.12); }}
#SideStrip {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
#StripBtn {{ border: 1px solid transparent; border-radius: 5px; padding: 6px; }}
#StripBtn:hover {{ background: rgba(66,165,245,0.18); border-color: {BORDER_HI}; }}
#HoverToolbar {{ background: {CARD}; border: 1px solid {BORDER_HI}; border-radius: 6px; }}
#HoverToolbar QToolButton {{ border: 1px solid transparent; border-radius: 4px; padding: 3px; }}
#HoverToolbar QToolButton:hover {{ background: rgba(66,165,245,0.22); border-color: {BORDER_HI}; }}
#CollapseBtn {{ border: none; padding: 4px; margin: 2px 4px; }}
#CollapseBtn:hover {{ background: rgba(66,165,245,0.18); border-radius: 4px; }}

#SidePanel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
#CardTitle {{ font-size: 14px; font-weight: bold; }}
#SectionTitle {{ color: {TEXT}; font-weight: bold; padding-top: 4px; }}
#Muted, QLabel#Muted {{ color: {MUTED}; }}
#SectionHeader {{ background: transparent; border: none; text-align: left; font-size: 14px;
                 font-weight: bold; padding: 6px 4px; }}
#SectionHeader:hover {{ color: {ACCENT_HI}; }}
#SectionHeader:checked, #SectionHeader:pressed {{ background: transparent; border: none; }}
#SubBox {{ background: rgba(8, 20, 38, 0.6); border: 1px solid {BORDER}; border-radius: 5px; }}

QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 8px; margin-right: 1px;
               border: 1px solid transparent; border-top-left-radius: 6px; border-top-right-radius: 6px;
               font-size: 14px; font-weight: bold; }}
QTabBar::tab:selected {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b8ef0, stop:1 #1565c0);
                        color: white; border-color: {ACCENT_HI}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: rgba(66,165,245,0.12); }}
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; }}

QListWidget, QTableWidget, QPlainTextEdit, QTextBrowser {{ background: rgba(8, 20, 38, 0.6);
  border: 1px solid {BORDER}; border-radius: 5px; outline: 0; }}
QListWidget#Thumbs {{ background: transparent; border: none; }}
QListWidget#Thumbs::item {{ border: 2px solid transparent; border-radius: 4px; padding: 4px; color: {TEXT}; }}
QListWidget#Thumbs::item:selected {{ border-color: {ACCENT_HI}; background: rgba(66,165,245,0.18); }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: rgba(30, 136, 229, 0.45); }}
QListWidget::item:hover {{ background: rgba(66,165,245,0.12); }}
QTableWidget {{ gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: none; border-right: 1px solid {BORDER};
                       border-bottom: 1px solid {BORDER}; padding: 4px; font-weight: bold; }}
QTableCornerButton::section {{ background: {CARD}; border: none; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: rgba(8, 20, 38, 0.8); border: 1px solid {BORDER};
  border-radius: 4px; padding: 4px 6px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT_HI}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ image: url({a}/down.svg); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER_HI}; selection-background-color: {ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
  border: none; width: 14px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({a}/up.svg); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({a}/down.svg); width: 9px; height: 9px; }}

QPushButton {{ background: {CARD}; border: 1px solid {BORDER_HI}; border-radius: 5px; padding: 6px 14px; }}
QPushButton:hover {{ background: #173560; border-color: {ACCENT_HI}; }}
QPushButton:pressed {{ background: {ACCENT}; }}
QPushButton:default {{ border-color: {ACCENT_HI}; }}

QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {BORDER_HI}; border-radius: 3px;
                       background: rgba(8, 20, 38, 0.8); }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HI}; image: url({a}/check.svg); }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1px solid {BORDER_HI};
                          background: rgba(8, 20, 38, 0.8); }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
  stop:0 white, stop:0.35 white, stop:0.45 {ACCENT}, stop:1 {ACCENT}); border-color: {ACCENT_HI}; }}
QCheckBox:disabled, QRadioButton:disabled, QLabel:disabled {{ color: #4d6380; }}

QSlider::groove:horizontal {{ height: 4px; background: #23405f; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #2f95ff; border: 2px solid #e8f3ff; width: 10px; height: 10px;
                             margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:disabled {{ background: #34506f; border-color: #4d6380; }}
QSlider::sub-page:horizontal:disabled {{ background: #34506f; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: #2a4a72; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: #3a659a; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER_HI}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QMenu::item:disabled {{ color: #4d6380; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

#BottomBar {{ background: {BG_BAR}; border-top: 1px solid {BORDER}; }}
#BottomBar QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 3px; }}
#BottomBar QToolButton:hover {{ background: rgba(66,165,245,0.16); border-color: {BORDER_HI}; }}
#BottomBar QToolButton:checked {{ background: rgba(30,136,229,0.45); border-color: {ACCENT_HI}; }}
QGraphicsView {{ border: 1px solid {BORDER}; border-radius: 4px; }}
QToolButton#StatusChip {{ background: transparent; border: 1px solid {BORDER}; border-radius: 12px;
  padding: 3px 10px 3px 6px; color: #8fa6c4; }}
QToolButton#StatusChip:hover {{ border-color: {BORDER_HI}; }}
QToolButton#StatusChip:checked {{ background: rgba(30,136,229,0.28); border-color: {ACCENT_HI};
  color: white; }}
QToolButton#SymbolButton {{ font-family: "Segoe UI Symbol", "Microsoft JhengHei"; font-size: 16px;
  min-width: 26px; min-height: 26px; padding: 0 3px; border: 1px solid {BORDER}; border-radius: 4px;
  background: transparent; }}
QToolButton#SymbolButton:hover {{ background: rgba(66,165,245,0.18); border-color: {ACCENT_HI}; }}
QToolButton#SymbolButton:pressed {{ background: rgba(66,165,245,0.35); }}
"""


def install_translations(app: QApplication):
  """載入 Qt 內建的繁體中文翻譯（確定／取消、列印與檔案對話框等）。"""
  path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
  for name in ("qtbase_zh_TW", "qt_zh_TW"):
    tr = QTranslator(app)
    if tr.load(name, path):
      app.installTranslator(tr)


def apply(app: QApplication):
  install_translations(app)
  app.setStyle("Fusion")
  pal = QPalette()
  for role, color in (
    (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
    (QPalette.ColorRole.Base, PANEL), (QPalette.ColorRole.AlternateBase, CARD),
    (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, CARD),
    (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
    (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, CARD),
    (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, MUTED),
  ):
    pal.setColor(role, QColor(color))
  app.setPalette(pal)
  app.setStyleSheet(stylesheet())


def dark_title_bar(w: QWidget):
  """Windows 10/11：要求 DWM 用深色標題列。其他平台或舊版 Windows 靜默略過。"""
  if sys.platform != "win32":
    return
  try:
    hwnd = int(w.winId())
    value = ctypes.c_int(1)
    for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE（新版 20，舊版 19）
      if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                    ctypes.sizeof(value)) == 0:
        break
  except (AttributeError, OSError):
    pass
