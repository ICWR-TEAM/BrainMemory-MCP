from __future__ import annotations

import json
from pathlib import Path

import pytest

from brainmemory_mcp.server import require_absolute_file_path


def test_absolute_file_path_is_accepted(tmp_path: Path):
    target = tmp_path / "migration.json"
    assert require_absolute_file_path(str(target), parameter="output_path") == target


@pytest.mark.parametrize(
    "value",
    [".", "..", "./migration.json", "../migration.json", "migration.json"],
)
def test_relative_and_dot_paths_are_rejected(value: str):
    with pytest.raises(ValueError, match="absolute path"):
        require_absolute_file_path(value, parameter="output_path")


@pytest.mark.parametrize("value", ["/tmp/./migration.json", "/tmp/../migration.json"])
def test_dot_segments_in_absolute_paths_are_rejected(value: str):
    with pytest.raises(ValueError, match="must not contain"):
        require_absolute_file_path(value, parameter="output_path")


def test_json_round_trip_fixture(tmp_path: Path):
    """The migration file format remains ordinary portable UTF-8 JSON."""
    target = require_absolute_file_path(str(tmp_path / "migration.json"), parameter="output_path")
    payload = {"format": "brainmemory-export", "format_version": 1, "memories": [], "links": []}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == payload
