"""核對清單匯出（CSV / XLSX）。"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from app.marks.model import KIND_LABELS, STATUS_LABELS, STATUSES, Mark

HEADERS = ["編號", "頁碼", "類型", "狀態", "實測值", "備註", "標記人", "建立時間", "更新時間",
           "文字內容", "連結"]


def _rows(marks: list[Mark]):
  for m in sorted(marks, key=lambda m: (m.page, m.no)):
    yield [m.no, m.page + 1, KIND_LABELS.get(m.kind, m.kind), STATUS_LABELS[m.status],
           m.measured, m.note, m.checker, m.created, m.updated, m.text, m.link]


def summary(marks: list[Mark]) -> dict[str, int]:
  c = Counter(m.status for m in marks)
  return {STATUS_LABELS[s]: c.get(s, 0) for s in STATUSES} | {"合計": len(marks)}


def export_csv(path: str | Path, marks: list[Mark]):
  # utf-8-sig 讓 Excel 直接開啟中文不亂碼
  with open(path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(HEADERS)
    w.writerows(_rows(marks))
    w.writerow([])
    for k, v in summary(marks).items():
      w.writerow([k, v])


def export_xlsx(path: str | Path, marks: list[Mark], title: str = ""):
  from openpyxl import Workbook
  from openpyxl.styles import Font, PatternFill

  fills = {
    STATUS_LABELS[s]: PatternFill("solid", fgColor=c)
    for s, c in (("none", "E8EAF6"), ("ok", "C6EFCE"), ("ng", "FFC7CE"), ("pending", "FFEB9C"))
  }
  wb = Workbook()
  ws = wb.active
  ws.title = "核對清單"
  ws.append(HEADERS)
  for cell in ws[1]:
    cell.font = Font(bold=True)
  for row in _rows(marks):
    ws.append(row)
    ws.cell(ws.max_row, 4).fill = fills[row[3]]
  for col, width in zip("ABCDEFGHIJK", (7, 6, 7, 9, 14, 40, 10, 20, 20, 30, 30)):
    ws.column_dimensions[col].width = width
  ws.freeze_panes = "A2"

  s = wb.create_sheet("統計")
  if title:
    s.append(["圖面", title])
  for k, v in summary(marks).items():
    s.append([k, v])
  wb.save(path)
