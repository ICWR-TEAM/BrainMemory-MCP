from __future__ import annotations

import asyncio

from brainmemory_mcp.__main__ import build_parser
from brainmemory_mcp.server import BearerKeyMiddleware


async def request(headers: list[tuple[bytes, bytes]]) -> list[dict]:
    inner_called = False

    async def inner(scope, receive, send):
        nonlocal inner_called
        inner_called = True
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    app = BearerKeyMiddleware(inner, "correct-secret")
    await app({"type": "http", "headers": headers}, receive, send)
    sent.append({"inner_called": inner_called})
    return sent


def test_cli_key_is_optional(monkeypatch):
    monkeypatch.delenv("BRAINMEMORY_KEY", raising=False)
    assert build_parser().parse_args([]).key is None


def test_cli_key_reads_environment(monkeypatch):
    monkeypatch.setenv("BRAINMEMORY_KEY", "from-env")
    assert build_parser().parse_args([]).key == "from-env"


def test_missing_authorization_is_rejected():
    sent = asyncio.run(request([]))
    assert sent[0]["status"] == 401
    assert (b"www-authenticate", b"Bearer") in sent[0]["headers"]
    assert sent[-1]["inner_called"] is False


def test_incorrect_authorization_is_rejected():
    sent = asyncio.run(request([(b"authorization", b"Bearer wrong-secret")]))
    assert sent[0]["status"] == 401
    assert sent[-1]["inner_called"] is False


def test_correct_bearer_key_is_accepted_case_insensitively():
    sent = asyncio.run(request([(b"authorization", b"bearer correct-secret")]))
    assert sent[0]["status"] == 204
    assert sent[-1]["inner_called"] is True
