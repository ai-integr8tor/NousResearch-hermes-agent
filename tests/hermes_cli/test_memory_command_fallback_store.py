"""Test that _handle_memory_command falls back to a fresh MemoryStore when
the agent does not have one (e.g., TUI slash-worker context).  Fixes #47363.
"""

import io
import os
import tempfile
import shutil
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def hermes_home(monkeypatch):
    d = tempfile.mkdtemp(prefix="hermes_mem_cmd_")
    home = os.path.join(d, ".hermes")
    os.makedirs(home)
    monkeypatch.setenv("HERMES_HOME", home)
    # Create minimal MEMORY.md so MemoryStore.load_from_disk() succeeds
    with open(os.path.join(home, "MEMORY.md"), "w") as f:
        f.write("- test entry\n")
    yield home
    shutil.rmtree(d, ignore_errors=True)


def test_memory_command_falls_back_to_disk_store(hermes_home, monkeypatch):
    """When self.agent is None (TUI slash-worker), _handle_memory_command
    should construct a MemoryStore from disk rather than passing None."""
    from hermes_cli.cli_commands_mixin import CLICommandsMixin

    # Build a minimal mixin instance with no agent
    obj = object.__new__(CLICommandsMixin)
    obj.agent = None

    # Patch handle_pending_subcommand to capture what store is passed
    captured = {}

    def fake_handle(subsystem, args, memory_store=None, set_mode_fn=None):
        captured["store"] = memory_store
        captured["subsystem"] = subsystem
        return "ok"

    with patch(
        "hermes_cli.write_approval_commands.handle_pending_subcommand",
        side_effect=fake_handle,
    ):
        # Redirect stdout since the method prints
        with patch("builtins.print"):
            obj._handle_memory_command("/memory pending")

    # The store should NOT be None — it should be a MemoryStore loaded from disk
    assert captured["store"] is not None
    assert hasattr(captured["store"], "memory_entries")


def test_memory_command_uses_agent_store_when_available(hermes_home, monkeypatch):
    """When self.agent._memory_store exists, use it directly."""
    from hermes_cli.cli_commands_mixin import CLICommandsMixin

    obj = object.__new__(CLICommandsMixin)
    mock_store = MagicMock()
    mock_agent = MagicMock()
    mock_agent._memory_store = mock_store
    obj.agent = mock_agent

    captured = {}

    def fake_handle(subsystem, args, memory_store=None, set_mode_fn=None):
        captured["store"] = memory_store
        return "ok"

    with patch(
        "hermes_cli.write_approval_commands.handle_pending_subcommand",
        side_effect=fake_handle,
    ):
        with patch("builtins.print"):
            obj._handle_memory_command("/memory pending")

    # Should use the agent's existing store
    assert captured["store"] is mock_store
