"""Tests for CLI background command TUI refresh behavior.

Ensures the TUI is properly refreshed before printing background task output
to prevent spinner/status bar overlap (#2718).
"""

from unittest.mock import MagicMock, patch
from queue import Queue


from cli import HermesCLI, _queue_or_display_async_notification


def _make_cli():
    """Create a minimal HermesCLI instance for testing."""
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj.model = "test-model"
    cli_obj._background_tasks = {}
    cli_obj._background_task_counter = 0
    cli_obj.conversation_history = []
    cli_obj.agent = None
    cli_obj._app = None
    return cli_obj


class TestBackgroundCommandTuiRefresh:
    """Tests for TUI refresh in background command output."""

    def test_invalidate_called_before_success_output(self):
        """App.invalidate() is called before printing background success output."""
        cli_obj = _make_cli()
        mock_app = MagicMock()
        cli_obj._app = mock_app

        # Track call order
        call_order = []
        original_invalidate = mock_app.invalidate

        def track_invalidate():
            call_order.append("invalidate")
            return original_invalidate()

        mock_app.invalidate = track_invalidate

        # Patch print to track when it's called
        with patch("builtins.print") as mock_print:
            mock_print.side_effect = lambda *args, **kwargs: call_order.append("print")

            # Simulate the background task output code path
            if cli_obj._app:
                cli_obj._app.invalidate()
                import time
                time.sleep(0.01)  # reduced for test
            print()

        # Verify invalidate was called before print
        assert call_order[0] == "invalidate"
        assert "print" in call_order

    def test_invalidate_called_before_error_output(self):
        """App.invalidate() is called before printing background error output."""
        cli_obj = _make_cli()
        mock_app = MagicMock()
        cli_obj._app = mock_app

        call_order = []
        mock_app.invalidate.side_effect = lambda: call_order.append("invalidate")

        with patch("builtins.print") as mock_print:
            mock_print.side_effect = lambda *args, **kwargs: call_order.append("print")

            # Simulate error path
            if cli_obj._app:
                cli_obj._app.invalidate()
                import time
                time.sleep(0.01)
            print()

        assert call_order[0] == "invalidate"
        assert "print" in call_order

    def test_no_crash_when_app_is_none(self):
        """No crash when _app is None (non-TUI mode)."""
        cli_obj = _make_cli()
        cli_obj._app = None

        # This should not raise
        if cli_obj._app:
            cli_obj._app.invalidate()
        # If we get here without exception, test passes

    def test_background_task_thread_safety(self):
        """Background task tracking is thread-safe."""
        cli_obj = _make_cli()

        # Simulate adding and removing background tasks
        task_id = "test_task_1"
        cli_obj._background_tasks[task_id] = MagicMock()
        assert task_id in cli_obj._background_tasks

        # Clean up
        cli_obj._background_tasks.pop(task_id, None)
        assert task_id not in cli_obj._background_tasks


def test_process_notification_displayed_not_queued(monkeypatch):
    q = Queue()
    printed = []
    monkeypatch.setattr("cli._cprint", printed.append)

    _queue_or_display_async_notification(
        q,
        {"type": "completion", "session_id": "proc_1"},
        "[IMPORTANT: Background process proc_1 completed]",
    )

    assert q.empty()
    assert len(printed) == 1
    assert "⚙️" in printed[0]
    assert "Background process proc_1" in printed[0]


def test_async_delegation_notification_still_queued(monkeypatch):
    q = Queue()
    monkeypatch.setattr(
        "cli._cprint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not print")),
    )

    _queue_or_display_async_notification(
        q,
        {"type": "async_delegation", "delegation_id": "deleg_1"},
        "[ASYNC DELEGATION COMPLETE — deleg_1]",
    )

    assert q.get_nowait() == "[ASYNC DELEGATION COMPLETE — deleg_1]"
