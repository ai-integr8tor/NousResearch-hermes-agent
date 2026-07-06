import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig


def _ensure_slack_mock():
    if "slack_bolt" in sys.modules and hasattr(sys.modules["slack_bolt"], "__file__"):
        return

    slack_bolt = MagicMock()
    slack_bolt.async_app.AsyncApp = MagicMock
    slack_bolt.adapter.socket_mode.async_handler.AsyncSocketModeHandler = MagicMock

    slack_sdk = MagicMock()
    slack_sdk.web.async_client.AsyncWebClient = MagicMock

    for name, mod in [
        ("slack_bolt", slack_bolt),
        ("slack_bolt.async_app", slack_bolt.async_app),
        ("slack_bolt.adapter", slack_bolt.adapter),
        ("slack_bolt.adapter.socket_mode", slack_bolt.adapter.socket_mode),
        ("slack_bolt.adapter.socket_mode.async_handler", slack_bolt.adapter.socket_mode.async_handler),
        ("slack_sdk", slack_sdk),
        ("slack_sdk.web", slack_sdk.web),
        ("slack_sdk.web.async_client", slack_sdk.web.async_client),
    ]:
        sys.modules.setdefault(name, mod)


_ensure_slack_mock()

import plugins.platforms.slack.adapter as _slack_mod  # noqa: E402

_slack_mod.SLACK_AVAILABLE = True

from plugins.platforms.slack.adapter import SlackAdapter  # noqa: E402


async def _never_finishes():
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_restart_socket_mode_bounds_hung_handler_close(monkeypatch):
    adapter = SlackAdapter(PlatformConfig(enabled=True, token="xoxb-test"))
    adapter._running = True
    adapter._app = MagicMock()
    adapter._app_token = "xapp-test"
    adapter._handler = MagicMock()
    adapter._handler.close_async = AsyncMock(side_effect=_never_finishes)
    adapter._socket_mode_task = asyncio.create_task(asyncio.Event().wait())
    start_socket_mode_handler = MagicMock()
    monkeypatch.setattr(adapter, "_start_socket_mode_handler", start_socket_mode_handler)

    monkeypatch.setattr(_slack_mod, "_SOCKET_MODE_CLOSE_TIMEOUT", 0.01, raising=False)

    await asyncio.wait_for(adapter._restart_socket_mode("transport disconnected"), timeout=0.2)

    start_socket_mode_handler.assert_called_once()
    assert adapter._socket_mode_task is None
