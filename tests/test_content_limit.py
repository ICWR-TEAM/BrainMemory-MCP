from __future__ import annotations

import pytest

from brainmemory_mcp.server import _apply_content_limit


def _memory(content: str = "abcdefghij") -> dict:
    return {"id": "m1", "content": content, "category": "general"}


def test_none_limit_returns_content_unchanged():
    mem = _memory()
    out = _apply_content_limit(mem, None)
    assert out == mem
    assert "content_truncated" not in out


@pytest.mark.parametrize("limit", [0, -5])
def test_non_positive_limit_returns_content_unchanged(limit: int):
    mem = _memory()
    out = _apply_content_limit(mem, limit)
    assert out["content"] == "abcdefghij"
    assert "content_truncated" not in out


def test_limit_shorter_than_content_truncates_and_flags():
    out = _apply_content_limit(_memory("abcdefghij"), 5)
    assert out["content"] == "abcde"
    assert out["content_truncated"] is True
    assert out["content_length"] == 10


def test_limit_longer_than_content_leaves_it_whole():
    out = _apply_content_limit(_memory("abc"), 100)
    assert out["content"] == "abc"
    assert "content_truncated" not in out
    assert "content_length" not in out


def test_original_dict_not_mutated_when_truncating():
    mem = _memory("abcdefghij")
    _apply_content_limit(mem, 3)
    assert mem["content"] == "abcdefghij"
    assert "content_truncated" not in mem


def test_non_string_content_is_ignored():
    mem = {"id": "m1", "content": None}
    out = _apply_content_limit(mem, 5)
    assert out == mem
