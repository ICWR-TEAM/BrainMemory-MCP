from __future__ import annotations

from pathlib import Path

import pytest

from brainmemory_mcp.server import create_server

LONG = "x" * 500


@pytest.fixture()
def server(tmp_path: Path):
    return create_server(data_dir=str(tmp_path))


def _fn(server, name):
    return server._tool_manager.get_tool(name).fn


def _store_two(server):
    fn = _fn(server, "store_memories")
    res = fn(
        items=[
            {"content": LONG, "category": "general", "tags": ["a"], "importance": 4},
            {"content": LONG, "category": "general", "tags": ["a"], "importance": 3},
        ]
    )
    return [r["memory"]["id"] for r in res["results"]]


def test_recall_memories_truncates(server):
    ids = _store_two(server)
    out = _fn(server, "recall_memories")(memory_ids=ids, content_chars=50)
    mem = out["memories"][0]["memory"]
    assert len(mem["content"]) == 50
    assert mem["content_truncated"] is True
    assert mem["content_length"] == 500


def test_recall_memories_full_by_default(server):
    ids = _store_two(server)
    out = _fn(server, "recall_memories")(memory_ids=ids)
    mem = out["memories"][0]["memory"]
    assert len(mem["content"]) == 500
    assert "content_truncated" not in mem


def test_recall_memories_truncates_details(server):
    ids = _store_two(server)
    _fn(server, "edit_details")(items=[{"op": "add", "memory_id": ids[0], "content": LONG}])
    out = _fn(server, "recall_memories")(
        memory_ids=[ids[0]], include_details=True, content_chars=10
    )
    detail = out["memories"][0]["details"][0]
    assert len(detail["content"]) == 10
    assert detail["content_truncated"] is True
    assert detail["content_length"] == 500


def test_search_memory_truncates(server):
    _store_two(server)
    out = _fn(server, "search_memory")(query="", content_chars=20)
    assert out["memories"]
    for m in out["memories"]:
        assert len(m["content"]) == 20
        assert m["content_truncated"] is True


def test_list_memories_truncates(server):
    _store_two(server)
    out = _fn(server, "list_memories")(content_chars=20)
    assert out["memories"]
    for m in out["memories"]:
        assert len(m["content"]) == 20
        assert m["content_length"] == 500


def test_recall_related_truncates_root_and_related(server):
    ids = _store_two(server)
    _fn(server, "edit_links")(
        items=[{"op": "link", "from_id": ids[0], "to_id": ids[1], "relation": "related_to"}]
    )
    out = _fn(server, "recall_related")(memory_id=ids[0], content_chars=30)
    assert len(out["root"]["content"]) == 30
    assert out["related"]
    assert all(len(m["content"]) == 30 for m in out["related"])


def test_connect_memories_truncates_path(server):
    ids = _store_two(server)
    _fn(server, "edit_links")(
        items=[{"op": "link", "from_id": ids[0], "to_id": ids[1], "relation": "related_to"}]
    )
    out = _fn(server, "connect_memories")(from_id=ids[0], to_id=ids[1], content_chars=15)
    assert out["path"]
    assert all(len(m["content"]) == 15 for m in out["path"])


def test_memory_map_truncates_nodes(server):
    _store_two(server)
    out = _fn(server, "memory_map")(content_chars=25)
    assert out["nodes"]
    assert all(len(n["content"]) == 25 for n in out["nodes"])


def test_recall_memories_content_offset_window(server):
    ids = _store_two(server)
    out = _fn(server, "recall_memories")(memory_ids=[ids[0]], content_chars=10, content_offset=5)
    mem = out["memories"][0]["memory"]
    assert mem["content"] == LONG[5:15]
    assert len(mem["content"]) == 10
    assert mem["content_truncated"] is True
    assert mem["content_length"] == 500
    assert mem["content_offset"] == 5


def test_search_memory_content_offset_paging(server):
    _store_two(server)
    page1 = _fn(server, "search_memory")(query="", content_chars=100, content_offset=0)
    page2 = _fn(server, "search_memory")(query="", content_chars=100, content_offset=100)
    m1, m2 = page1["memories"][0], page2["memories"][0]
    assert m1["content"] == LONG[0:100]
    assert m2["content"] == LONG[100:200]
    assert "content_offset" not in m1  # offset 0
    assert m2["content_offset"] == 100


def test_memory_map_content_offset(server):
    _store_two(server)
    out = _fn(server, "memory_map")(content_chars=20, content_offset=30)
    node = out["nodes"][0]
    assert node["content"] == LONG[30:50]
    assert node["content_offset"] == 30


def test_restore_list_trash_and_history_truncate(server):
    ids = _store_two(server)
    # create a history version, then forget to populate trash
    _fn(server, "update_memories")(updates=[{"memory_id": ids[0], "content": LONG + "y"}])
    hist = _fn(server, "restore_memories")(
        items=[{"op": "history", "memory_id": ids[0], "content_chars": 12}]
    )
    versions = hist["results"][0]["history"]
    assert versions
    assert all(len(v["memory"]["content"]) <= 12 for v in versions)

    _fn(server, "forget_memories")(memory_ids=[ids[1]])
    trash = _fn(server, "restore_memories")(
        items=[{"op": "list_trash", "content_chars": 12}]
    )
    rows = trash["results"][0]["trash"]
    assert rows
    assert all(len(r["memory"]["content"]) == 12 for r in rows)
