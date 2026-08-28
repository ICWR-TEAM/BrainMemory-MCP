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


def test_export_pagination_pages_through_a_large_graph(tmp_path: Path):
    source = create_server(data_dir=str(tmp_path / "source"))
    store_tool = source._tool_manager._tools["store_memories"].fn
    link_tool = source._tool_manager._tools["edit_links"].fn
    stored = store_tool([{"content": f"memory {i}"} for i in range(5)])
    ids = [r["memory"]["id"] for r in stored["results"]]
    link_tool([{"op": "link", "from_id": ids[0], "to_id": ids[1]}])
    link_tool([{"op": "link", "from_id": ids[1], "to_id": ids[2]}])

    export = source._tool_manager._tools["transfer_memories"].fn
    dest = create_server(data_dir=str(tmp_path / "destination"))
    import_fn = dest._tool_manager._tools["transfer_memories"].fn

    # Page through memories two at a time.
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = export(op="export", scope="memories", limit=2, cursor=cursor)
        assert page["status"] == "ok"
        assert page["scope"] == "memories"
        assert page["data"]["links"] == []
        imported = import_fn(op="import", data=page["data"])
        assert imported["status"] == "ok"
        seen.extend(m["id"] for m in page["data"]["memories"])
        pages += 1
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
        assert cursor is not None
    assert pages == 3  # 2 + 2 + 1
    assert sorted(seen) == sorted(ids)

    # Now page through links (endpoints already imported above).
    link_page = export(op="export", scope="links", limit=100)
    assert link_page["status"] == "ok"
    assert link_page["has_more"] is False
    assert link_page["data"]["memories"] == []
    assert len(link_page["data"]["links"]) == 2
    imported_links = import_fn(op="import", data=link_page["data"])
    assert imported_links["links_imported"] == 2


def test_export_pagination_requires_scope_memories_or_links(tmp_path: Path):
    tool = transfer_tool(tmp_path / "data")
    result = tool(op="export", scope="all", limit=10)
    assert result["status"] == "error"
    assert "scope" in result["error"]
