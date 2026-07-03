"""Gateway coverage for the read-only /journey slash command."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(text=text, source=_make_source(), message_id="m1")


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner.hooks = SimpleNamespace(
        emit=AsyncMock(),
        emit_collect=AsyncMock(return_value=[]),
        loaded_hooks=False,
    )
    return runner


def test_journey_is_available_on_gateway():
    from hermes_cli.commands import GATEWAY_KNOWN_COMMANDS, resolve_command

    cmd = resolve_command("journey")
    assert cmd is not None
    assert not cmd.cli_only
    assert "journey" in GATEWAY_KNOWN_COMMANDS


def test_handle_journey_list_renders_plain_text(monkeypatch):
    import hermes_cli.journey as journey

    monkeypatch.setattr(
        journey,
        "_build_payload",
        lambda: {
            "nodes": [
                {
                    "id": "skill-alpha",
                    "kind": "skill",
                    "label": "Alpha Skill",
                    "timestamp": 1_700_000_000,
                }
            ]
        },
    )

    runner = _make_runner()
    result = asyncio.run(runner._handle_journey_command(_make_event("/journey list")))

    assert "skill-alpha" in result
    assert "Alpha Skill" in result
    assert "\x1b[" not in result


def test_handle_journey_edit_delete_are_cli_only():
    runner = _make_runner()

    result = asyncio.run(runner._handle_journey_command(_make_event("/journey delete skill-alpha")))

    assert "read-only" in result
    assert "CLI" in result
