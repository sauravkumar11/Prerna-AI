from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.atomic_io import atomic_write_json


def test_atomic_write_json_writes_valid_json(tmp_path: Path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"ok": True, "count": 2})

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {"ok": True, "count": 2}


def test_atomic_write_json_keeps_existing_file_on_replace_failure(tmp_path: Path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text('{"old": true}', encoding="utf-8")

    def fail_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr("utils.atomic_io.os.replace", fail_replace)

    with pytest.raises(OSError):
        atomic_write_json(target, {"new": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert not list(tmp_path.glob("*.tmp"))
