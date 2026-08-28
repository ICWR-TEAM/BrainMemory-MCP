from __future__ import annotations

from pathlib import Path

from brainmemory_mcp.server import create_server


def transfer_tool(data_dir: Path):
    server = create_server(data_dir=str(data_dir))
    return server._tool_manager._tools["transfer_memories"].fn


def test_inline_export_can_be_uploaded_to_another_server(tmp_path: Path):
    source = create_server(data_dir=str(tmp_path / "source"))
    source._tool_manager._tools["store_memories"].fn(
        [{"content": "portable memory", "category": "test", "importance": 4}]
    )

    exported = source._tool_manager._tools["transfer_memories"].fn(op="export")
    assert exported["status"] == "ok"
    assert exported["counts"]["memories"] == 1
    assert exported["data"]["format"] == "brainmemory-export"

    imported = transfer_tool(tmp_path / "destination")(
        op="import", data=exported["data"], on_conflict="overwrite"
    )
    assert imported["status"] == "ok"
    assert imported["source"] == "upload"
    assert imported["imported"] == 1


def test_file_export_and_import_remain_supported(tmp_path: Path):
    source = create_server(data_dir=str(tmp_path / "source"))
    source._tool_manager._tools["store_memories"].fn([{"content": "file memory"}])
    migration = tmp_path / "migration.json"

    exported = source._tool_manager._tools["transfer_memories"].fn(
        op="export", output_path=str(migration)
    )
    assert exported["output_path"] == str(migration)
    assert migration.is_file()

    imported = transfer_tool(tmp_path / "destination")(op="import", input_path=str(migration))
    assert imported["status"] == "ok"
    assert imported["source"] == "file"


def test_import_rejects_ambiguous_or_non_object_upload(tmp_path: Path):
    tool = transfer_tool(tmp_path / "data")
    assert tool(op="import", data={}, input_path="/tmp/data.json")["status"] == "error"
    result = tool(op="import", data=["not", "an", "object"])
    assert result == {"status": "error", "error": "data must be a migration JSON object"}
