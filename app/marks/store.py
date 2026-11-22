"""標記側檔 (<pdf>.marks.json) 的讀寫。"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.marks.model import Mark, now_iso

SCHEMA_VERSION = 1


def sidecar_path(pdf_path: str | Path) -> Path:
  p = Path(pdf_path)
  return p.with_name(p.name + ".marks.json")


@dataclass
class LoadResult:
  marks: list[Mark]
  exists: bool
  hash_mismatch: bool
  stored_sha256: str = ""


class SidecarError(Exception):
  pass


def load_marks(pdf_path: str | Path, pdf_sha256: str) -> LoadResult:
  path = sidecar_path(pdf_path)
  if not path.exists():
    return LoadResult([], exists=False, hash_mismatch=False)
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    marks = [Mark.from_dict(d) for d in data.get("marks", [])]
  except (OSError, ValueError, TypeError, KeyError) as e:
    raise SidecarError(f"標記檔無法讀取：{path}\n{e}") from e
  stored = data.get("pdf_sha256", "")
  return LoadResult(marks, exists=True, hash_mismatch=bool(stored) and stored != pdf_sha256,
                    stored_sha256=stored)


def save_marks(pdf_path: str | Path, pdf_sha256: str, marks: list[Mark]) -> Path:
  path = sidecar_path(pdf_path)
  payload = {
    "schema_version": SCHEMA_VERSION,
    "pdf_file": Path(pdf_path).name,
    "pdf_sha256": pdf_sha256,
    "saved": now_iso(),
    "marks": [m.to_dict() for m in marks],
  }
  text = json.dumps(payload, ensure_ascii=False, indent=2)
  fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
      f.write(text)
    os.replace(tmp, path)
  except BaseException:
    if os.path.exists(tmp):
      os.unlink(tmp)
    raise
  return path
