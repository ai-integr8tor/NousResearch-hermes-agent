"""Tests for CCC Telegram inline-button callbacks (ccc:decision / ccc:followup / ai:).

Regression for the silent-shimmer bug: ccc:* callbacks fell through
_handle_callback_query without ever calling query.answer(), so Telegram
buttons spun forever. The _handle_ccc_script_callback handler shells out to
ccc-decision-callback.sh, acks the query, and strips the keyboard on terminal
actions (keeping it on 'view').
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)


def _ensure_telegram_mock():
    if "telegram" in sys.modules and hasattr(sys.modules["telegram"], "__file__"):
        return
    mod = MagicMock()
    mod.ext.ContextTypes.DEFAULT_TYPE = type(None)
    mod.constants.ParseMode.MARKDOWN = "Markdown"
    mod.constants.ParseMode.MARKDOWN_V2 = "MarkdownV2"
    mod.constants.ParseMode.HTML = "HTML"
    mod.constants.ChatType.PRIVATE = "private"
    mod.constants.ChatType.GROUP = "group"
    mod.constants.ChatType.SUPERGROUP = "supergroup"
    mod.constants.ChatType.CHANNEL = "channel"
    mod.error.NetworkError = type("NetworkError", (OSError,), {})
    mod.error.TimedOut = type("TimedOut", (OSError,), {})
    mod.error.BadRequest = type("BadRequest", (Exception,), {})
    for name in ("telegram", "telegram.ext", "telegram.constants", "telegram.request"):
        sys.modules.setdefault(name, mod)
    sys.modules.setdefault("telegram.error", mod.error)


_ensure_telegram_mock()

from gateway.platforms.telegram import TelegramAdapter  # noqa: E402
from gateway.config import PlatformConfig  # noqa: E402


def _make_adapter():
    config = PlatformConfig(enabled=True, token="test-token", extra={})
    adapter = TelegramAdapter(config)
    adapter._bot = AsyncMock()
    adapter._app = MagicMock()
    return adapter


def _make_query(data: str, user_id: str = "12345"):
    query = AsyncMock()
    query.data = data
    query.message = MagicMock()
    query.message.chat_id = 12345
    query.message.text_html = "⚠️ <b>Decision Needs Attention</b>\n#1846 — test"
    query.from_user = MagicMock()
    query.from_user.id = user_id
    query.from_user.first_name = "Michael"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def _fake_proc(returncode: int = 0, stderr: bytes = b""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(b"{}", stderr))
    return proc


class TestCCCCallback:
    """ccc:decision / ccc:followup / ai: inline-button callbacks."""

    @pytest.mark.asyncio
    async def test_approve_acks_and_strips_keyboard(self):
        adapter = _make_adapter()
        query = _make_query("ccc:decision:approve:1846")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=_fake_proc(0)):
            await adapter._handle_callback_query(update, context)

        # The whole point: the query MUST be answered (no eternal shimmer).
        query.answer.assert_called_once()
        assert "Approved" in query.answer.call_args[1]["text"]
        # Terminal action → keyboard stripped.
        query.edit_message_text.assert_called_once()
        assert query.edit_message_text.call_args[1]["reply_markup"] is None

    @pytest.mark.asyncio
    async def test_view_keeps_keyboard(self):
        adapter = _make_adapter()
        query = _make_query("ccc:decision:view:1846")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=_fake_proc(0)):
            await adapter._handle_callback_query(update, context)

        query.answer.assert_called_once()
        # 'view' is non-terminal — keyboard stays so the user can still act.
        query.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_action(self):
        adapter = _make_adapter()
        query = _make_query("ccc:decision:reject:1846")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=_fake_proc(0)) as mock_exec:
            await adapter._handle_callback_query(update, context)

        # The full callback_data is passed to the shell handler as argv[1].
        passed_args = mock_exec.call_args[0]
        assert "ccc:decision:reject:1846" in passed_args
        assert "Rejected" in query.answer.call_args[1]["text"]

    @pytest.mark.asyncio
    async def test_unauthorized_denies_without_subprocess(self):
        adapter = _make_adapter()
        adapter._message_handler = None  # force fallback auth
        query = _make_query("ccc:decision:approve:1846", user_id="999")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "67890"}, clear=False), \
             patch("asyncio.create_subprocess_exec") as mock_exec:
            await adapter._handle_callback_query(update, context)

        mock_exec.assert_not_called()
        query.answer.assert_called_once()
        assert "not authorized" in query.answer.call_args[1]["text"].lower()
        query.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_resolved_strips_keyboard(self):
        adapter = _make_adapter()
        query = _make_query("ccc:decision:approve:1846")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        # API returns non-zero with "already approved" → treat as resolved.
        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec",
                   return_value=_fake_proc(1, b'{"error":"Decision #1846 already approved"}')):
            await adapter._handle_callback_query(update, context)

        query.answer.assert_called_once()
        assert "Already resolved" in query.answer.call_args[1]["text"]
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_keeps_keyboard_for_retry(self):
        adapter = _make_adapter()
        query = _make_query("ccc:decision:approve:1846")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec",
                   return_value=_fake_proc(1, b'{"error":"connection refused"}')):
            await adapter._handle_callback_query(update, context)

        query.answer.assert_called_once()
        assert "failed" in query.answer.call_args[1]["text"].lower()
        # Failure → keyboard preserved so the user can retry.
        query.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_just_acks(self):
        adapter = _make_adapter()
        query = _make_query("ccc:noop")
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            await adapter._handle_callback_query(update, context)

        mock_exec.assert_not_called()
        query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_followup_and_ai_prefixes_route(self):
        """ccc:followup: and ai: prefixes hit the same handler."""
        adapter = _make_adapter()
        for data in ("ccc:followup:done:14", "ai:done:1496:2"):
            query = _make_query(data)
            update = MagicMock()
            update.callback_query = query
            context = MagicMock()

            with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False), \
                 patch("pathlib.Path.exists", return_value=True), \
                 patch("asyncio.create_subprocess_exec", return_value=_fake_proc(0)) as mock_exec:
                await adapter._handle_callback_query(update, context)

            mock_exec.assert_called_once()
            assert data in mock_exec.call_args[0]
            query.answer.assert_called_once()
