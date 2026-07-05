"""Regression tests for Matrix command batching.

Matrix clients commonly reserve typed "/" for local commands, so Hermes
accepts "!command" aliases that normalize to "/command".  Long normalized
commands still need the text-batch split path so client-side continuation
chunks do not arrive as separate user messages.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


ROOM_ID = "!room:example"
USER_ID = "@user:example"


def _source(message_id: str) -> SessionSource:
    return SessionSource(
        platform=Platform.MATRIX,
        chat_id=ROOM_ID,
        chat_name="Element X DM",
        chat_type="dm",
        user_id=USER_ID,
        user_name="User",
        message_id=message_id,
        scope_id="matrix.example",
    )


def _make_adapter(*, batch_delay: float = 0.02):
    from plugins.platforms.matrix.adapter import MatrixAdapter

    adapter = object.__new__(MatrixAdapter)
    adapter.config = SimpleNamespace(
        extra={"group_sessions_per_user": True, "thread_sessions_per_user": False}
    )
    adapter._text_batch_delay_seconds = batch_delay
    adapter._text_batch_split_delay_seconds = batch_delay
    adapter._pending_text_batches = {}
    adapter._pending_text_batch_tasks = {}

    async def resolve_context(room_id, sender, event_id, body, source_content, relates_to):
        return body, True, "dm", None, "User", _source(event_id)

    adapter._resolve_message_context = resolve_context
    return adapter


def test_long_matrix_bang_command_is_batched():
    async def scenario():
        adapter = _make_adapter()
        captured: list[MessageEvent] = []

        async def capture(message: MessageEvent):
            captured.append(message)

        adapter.handle_message = capture

        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$long-1",
            0,
            {"body": "!queue " + ("x" * 3900)},
            {},
        )
        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$long-2",
            0,
            {"body": "tail from client split"},
            {},
        )
        await asyncio.sleep(0.08)

        assert len(captured) == 1
        assert captured[0].message_type == MessageType.COMMAND
        assert captured[0].get_command() == "queue"
        assert "tail from client split" in captured[0].text

    asyncio.run(scenario())


def test_short_matrix_bang_command_dispatches_immediately():
    async def scenario():
        adapter = _make_adapter()
        captured: list[MessageEvent] = []

        async def capture(message: MessageEvent):
            captured.append(message)

        adapter.handle_message = capture

        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$short-1",
            0,
            {"body": "!stop"},
            {},
        )

        assert len(captured) == 1
        assert captured[0].text == "/stop"
        assert captured[0].message_type == MessageType.COMMAND

    asyncio.run(scenario())


def test_command_like_split_continuation_joins_pending_long_command():
    async def scenario():
        adapter = _make_adapter()
        captured: list[MessageEvent] = []

        async def capture(message: MessageEvent):
            captured.append(message)

        adapter.handle_message = capture

        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$long-1",
            0,
            {"body": "!queue " + ("x" * 3900)},
            {},
        )
        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$long-2",
            0,
            {"body": "/looks-like-a-command but is a split continuation"},
            {},
        )
        await asyncio.sleep(0.08)

        assert len(captured) == 1
        assert captured[0].get_command() == "queue"
        assert "/looks-like-a-command but is a split continuation" in captured[0].text

    asyncio.run(scenario())


def test_long_command_after_pending_text_starts_separate_command_batch():
    async def scenario():
        adapter = _make_adapter()
        captured: list[MessageEvent] = []

        async def capture(message: MessageEvent):
            captured.append(message)

        adapter.handle_message = capture

        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$text-1",
            0,
            {"body": "hello before"},
            {},
        )
        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$long-1",
            0,
            {"body": "!queue " + ("x" * 3900)},
            {},
        )
        await adapter._handle_text_message(
            ROOM_ID,
            USER_ID,
            "$long-2",
            0,
            {"body": "tail from client split"},
            {},
        )
        await asyncio.sleep(0.08)

        assert len(captured) == 2
        assert captured[0].message_type == MessageType.TEXT
        assert captured[0].text == "hello before"
        assert captured[1].message_type == MessageType.COMMAND
        assert captured[1].get_command() == "queue"
        assert "tail from client split" in captured[1].text

    asyncio.run(scenario())
