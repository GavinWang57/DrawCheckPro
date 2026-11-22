import csv
import json

import pytest
from openpyxl import load_workbook

from app.document import file_sha256
from app.marks.controller import MarkController
from app.marks.export import export_csv, export_xlsx
from app.marks.model import KIND_RECT, KIND_STAMP, STATUS_NG, STATUS_OK, Mark
from app.marks.store import SidecarError, load_marks, save_marks, sidecar_path


def sample_marks():
  return [
    Mark(page=0, kind=KIND_STAMP, rect=[10, 10, 20, 20], status=STATUS_OK, no=1),
    Mark(page=1, kind=KIND_RECT, rect=[30, 40, 80, 60], status=STATUS_NG, no=2,
         note="孔徑偏大", measured="8.05"),
    Mark(page=0, kind=KIND_RECT, rect=[1, 2, 3, 4], no=3, status="pending"),
  ]


def test_roundtrip_and_pdf_untouched(drawing_pdf):
  sha = file_sha256(drawing_pdf)
  marks = sample_marks()
  path = save_marks(drawing_pdf, sha, marks)
  assert path == sidecar_path(drawing_pdf) and path.name == "A001.pdf.marks.json"
  res = load_marks(drawing_pdf, sha)
  assert not res.hash_mismatch
  assert [m.to_dict() for m in res.marks] == [m.to_dict() for m in marks]
  assert file_sha256(drawing_pdf) == sha


def test_hash_mismatch_detected(drawing_pdf):
  save_marks(drawing_pdf, "old-hash", sample_marks())
  assert load_marks(drawing_pdf, file_sha256(drawing_pdf)).hash_mismatch


def test_corrupt_sidecar_raises(drawing_pdf):
  sidecar_path(drawing_pdf).write_text("{not json", encoding="utf-8")
  with pytest.raises(SidecarError):
    load_marks(drawing_pdf, "x")


def test_missing_sidecar(drawing_pdf):
  res = load_marks(drawing_pdf, "x")
  assert not res.exists and res.marks == []


def test_export_csv_and_xlsx(tmp_path):
  marks = sample_marks()
  export_csv(tmp_path / "a.csv", marks)
  rows = list(csv.reader(open(tmp_path / "a.csv", encoding="utf-8-sig")))
  assert rows[0][0] == "編號"
  assert rows[1][:4] == ["1", "1", "戳記", "OK"]
  assert ["NG", "1"] in rows and ["合計", "3"] in rows

  export_xlsx(tmp_path / "a.xlsx", marks, "A001.pdf")
  wb = load_workbook(tmp_path / "a.xlsx")
  ws = wb["核對清單"]
  assert ws.max_row == 4
  assert ws.cell(4, 6).value == "孔徑偏大"
  stats = {r[0]: r[1] for r in wb["統計"].iter_rows(values_only=True)}
  assert stats["OK"] == 1 and stats["待確認"] == 1 and stats["無狀態"] == 0 and stats["合計"] == 3


def test_controller_undo_redo():
  ctl = MarkController()
  m = Mark(page=0, kind=KIND_RECT, rect=[0, 0, 5, 5])
  ctl.add_mark(m)
  assert m.no == 1 and ctl.dirty
  ctl.update_marks([m.id], status=STATUS_OK, note="ok")
  assert ctl.get(m.id).status == STATUS_OK
  ctl.undo_stack.undo()
  assert ctl.get(m.id).status != STATUS_OK and ctl.get(m.id).note == ""
  ctl.delete_marks([m.id])
  assert ctl.get(m.id) is None
  ctl.undo_stack.undo()
  assert ctl.get(m.id) is not None
  ctl.add_mark(Mark(page=0, kind=KIND_RECT, rect=[0, 0, 1, 1]))
  assert sorted(x.no for x in ctl.marks()) == [1, 2]


def test_from_dict_tolerates_unknown_fields():
  d = sample_marks()[0].to_dict() | {"future_field": 1, "status": "weird"}
  m = Mark.from_dict(json.loads(json.dumps(d)))
  assert m.status == "pending"
