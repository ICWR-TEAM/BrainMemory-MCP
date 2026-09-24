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


# --- offset (windowing) --------------------------------------------------- #


def test_offset_only_returns_tail_from_start():
    out = _apply_content_limit(_memory("abcdefghij"), None, 3)
    assert out["content"] == "defghij"
    assert out["content_truncated"] is True
    assert out["content_length"] == 10
    assert out["content_offset"] == 3


def test_offset_with_length_returns_window():
    out = _apply_content_limit(_memory("abcdefghij"), 4, 2)
    assert out["content"] == "cdef"
    assert out["content_truncated"] is True
    assert out["content_length"] == 10
    assert out["content_offset"] == 2


def test_offset_zero_behaves_like_plain_limit():
    out = _apply_content_limit(_memory("abcdefghij"), 5, 0)
    assert out["content"] == "abcde"
    assert out["content_truncated"] is True
    assert "content_offset" not in out  # only added when offset > 0


def test_offset_covering_whole_tail_still_flags_because_windowed():
    # offset > 0 but length reaches the end: not the whole content -> truncated
    out = _apply_content_limit(_memory("abcdefghij"), 100, 4)
    assert out["content"] == "efghij"
    assert out["content_truncated"] is True
    assert out["content_offset"] == 4


def test_offset_beyond_content_returns_empty():
    out = _apply_content_limit(_memory("abcde"), 10, 99)
    assert out["content"] == ""
    assert out["content_truncated"] is True
    assert out["content_length"] == 5
    assert out["content_offset"] == 99


def test_offset_zero_no_limit_returns_unchanged():
    mem = _memory("abcde")
    out = _apply_content_limit(mem, None, 0)
    assert out == mem
    assert "content_truncated" not in out


def test_negative_offset_treated_as_zero():
    out = _apply_content_limit(_memory("abcdefghij"), 4, -5)
    assert out["content"] == "abcd"
    assert "content_offset" not in out
