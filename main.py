import ctypes
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import APP_NAME, MainWindow
from app.resources import resource_path
from app.ui import theme


def main():
  if sys.platform == "win32":
    # 讓工作列顯示本程式的圖示，而不是 python.exe 的圖示
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DrawCheckPro.App")
  app = QApplication(sys.argv)
  app.setApplicationName(APP_NAME)
  app.setWindowIcon(QIcon(str(resource_path("app_icon.png"))))
  theme.apply(app)
  win = MainWindow()
  win.show()
  if len(sys.argv) > 1 and sys.argv[1].strip():
    win.open_pdf(sys.argv[1])
  sys.exit(app.exec())


if __name__ == "__main__":
  main()
