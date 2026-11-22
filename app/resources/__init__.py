"""內建資源（圖示）。PyInstaller 打包後資源會解壓到 sys._MEIPASS 底下。"""
import sys
from pathlib import Path


def resource_path(name: str) -> Path:
  base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
  return base / "app" / "resources" / name
