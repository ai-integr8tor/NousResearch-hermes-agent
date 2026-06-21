"""Tests for the /background indicator in the CLI status bar.

The classic prompt_toolkit status bar shows `▶ N` when N tasks launched via
`/background` are still running. Source of truth is `self._background_tasks`
(a Dict[str, threading.Thread]); entries are removed in the task thread's
finally block, so len() reflects truly-running tasks.
"""

import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from cli import HermesCLI


def _stub_thread() -> threading.Thread:
    """Return a Thread instance that's never started — pure dict-value stand-in."""
    return threading.Thread(target=lambda: None)


def _make_cli():
    """Bare-metal HermesCLI for snapshot/build tests (no __init__ side effects)."""
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj.model = "anthropic/claude-opus-4.6"
    cli_obj.agent = None
    cli_obj.provider = "anthropic"
    cli_obj.requested_provider = "anthropic"
    cli_obj._background_tasks = {}
    cli_obj._codex_usage_snapshot = None
    cli_obj._codex_usage_last_checked = 0.0
    cli_obj._codex_usage_refreshing = False
    cli_obj._codex_usage_lock = threading.Lock()
    # The snapshot reads session_start to compute duration; supply a stub.
    cli_obj.session_start = datetime.now()
    return cli_obj


def _codex_usage_snapshot(used_percent: float, reset_seconds: float | None = None):
    reset_at = None
    if reset_seconds is not None:
        reset_at = datetime.now() + timedelta(seconds=reset_seconds)
    return SimpleNamespace(
        windows=(SimpleNamespace(label="Session", used_percent=used_percent, reset_at=reset_at),)
    )


def _seed_codex_usage(cli_obj, used_percent: float, reset_seconds: float | None = None) -> None:
    cli_obj.provider = "openai-codex"
    cli_obj.requested_provider = "openai-codex"
    cli_obj._codex_usage_snapshot = _codex_usage_snapshot(used_percent, reset_seconds=reset_seconds)
    # Fresh enough that _get_status_bar_snapshot() will not start a network
    # refresh thread during tests; it simply reads the cached usage data.
    cli_obj._codex_usage_last_checked = time.monotonic()


def test_snapshot_reports_zero_when_no_background_tasks():
    cli_obj = _make_cli()
    snap = cli_obj._get_status_bar_snapshot()
    assert snap["active_background_tasks"] == 0


def test_snapshot_counts_live_background_tasks():
    cli_obj = _make_cli()
    cli_obj._background_tasks = {"bg_a": _stub_thread(), "bg_b": _stub_thread()}
    snap = cli_obj._get_status_bar_snapshot()
    assert snap["active_background_tasks"] == 2


def test_snapshot_safe_when_background_tasks_attr_missing():
    """Older HermesCLI instances (tests with __new__, etc.) may lack the attr."""
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj.model = "x"
    cli_obj.agent = None
    cli_obj.session_start = datetime.now()
    # No _background_tasks at all — must not raise.
    snap = cli_obj._get_status_bar_snapshot()
    assert snap["active_background_tasks"] == 0


def test_plain_text_status_omits_indicator_when_idle():
    cli_obj = _make_cli()
    text = cli_obj._build_status_bar_text(width=80)
    assert "▶" not in text


def test_plain_text_status_shows_indicator_when_active():
    cli_obj = _make_cli()
    cli_obj._background_tasks = {"bg_a": _stub_thread()}
    text = cli_obj._build_status_bar_text(width=80)
    assert "▶ 1" in text


def test_plain_text_status_shows_higher_count():
    cli_obj = _make_cli()
    cli_obj._background_tasks = {
        "a": _stub_thread(),
        "b": _stub_thread(),
        "c": _stub_thread(),
    }
    text = cli_obj._build_status_bar_text(width=80)
    assert "▶ 3" in text


def test_narrow_width_omits_bg_indicator():
    """The narrow tier (<52) is already cramped — bg is secondary, drop it."""
    cli_obj = _make_cli()
    cli_obj._background_tasks = {"bg_a": _stub_thread()}
    text = cli_obj._build_status_bar_text(width=40)
    assert "▶" not in text


def test_fragments_include_bg_segment_when_active():
    cli_obj = _make_cli()
    cli_obj._background_tasks = {"a": _stub_thread(), "b": _stub_thread()}
    cli_obj._status_bar_visible = True
    # _get_status_bar_fragments asks _get_tui_terminal_width(); stub it wide.
    cli_obj._get_tui_terminal_width = lambda: 120  # type: ignore[method-assign]
    frags = cli_obj._get_status_bar_fragments()
    rendered = "".join(text for _style, text in frags)
    assert "▶ 2" in rendered


def test_fragments_omit_bg_segment_when_idle():
    cli_obj = _make_cli()
    cli_obj._status_bar_visible = True
    cli_obj._get_tui_terminal_width = lambda: 120  # type: ignore[method-assign]
    frags = cli_obj._get_status_bar_fragments()
    rendered = "".join(text for _style, text in frags)
    assert "▶" not in rendered


# ── Background terminal-process indicator (⚙ N) ───────────────────────────
# Source of truth is tools.process_registry.process_registry._running (a dict
# of currently-running shell processes spawned by terminal(background=true)).
# Distinct from /background tasks above: ▶ counts agent threads, ⚙ counts
# shell processes. Both can be active simultaneously.


class _FakeRunningRegistry:
    """Minimal stand-in for process_registry; exposes count_running()."""

    def __init__(self, count: int) -> None:
        self._count = count

    def count_running(self) -> int:
        return self._count


def _patch_process_registry(monkeypatch, count: int) -> None:
    import tools.process_registry as pr_mod
    monkeypatch.setattr(pr_mod, "process_registry", _FakeRunningRegistry(count))


def test_snapshot_reports_zero_when_no_background_processes(monkeypatch):
    cli_obj = _make_cli()
    _patch_process_registry(monkeypatch, 0)
    snap = cli_obj._get_status_bar_snapshot()
    assert snap["active_background_processes"] == 0


def test_snapshot_counts_live_background_processes(monkeypatch):
    cli_obj = _make_cli()
    _patch_process_registry(monkeypatch, 3)
    snap = cli_obj._get_status_bar_snapshot()
    assert snap["active_background_processes"] == 3


def test_snapshot_safe_when_process_registry_raises(monkeypatch):
    """If count_running() raises the snapshot stays at 0; no propagate."""
    cli_obj = _make_cli()
    import tools.process_registry as pr_mod

    class _BoomRegistry:
        def count_running(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(pr_mod, "process_registry", _BoomRegistry())
    snap = cli_obj._get_status_bar_snapshot()
    assert snap["active_background_processes"] == 0


def test_plain_text_status_shows_proc_indicator_when_active(monkeypatch):
    cli_obj = _make_cli()
    _patch_process_registry(monkeypatch, 2)
    text = cli_obj._build_status_bar_text(width=80)
    assert "⚙ 2" in text


def test_plain_text_status_omits_proc_indicator_when_idle(monkeypatch):
    cli_obj = _make_cli()
    _patch_process_registry(monkeypatch, 0)
    text = cli_obj._build_status_bar_text(width=80)
    assert "⚙" not in text


def test_fragments_include_proc_segment_when_active(monkeypatch):
    cli_obj = _make_cli()
    _patch_process_registry(monkeypatch, 1)
    cli_obj._status_bar_visible = True
    cli_obj._get_tui_terminal_width = lambda: 120  # type: ignore[method-assign]
    frags = cli_obj._get_status_bar_fragments()
    rendered = "".join(text for _style, text in frags)
    assert "⚙ 1" in rendered


def test_indicators_independent_agents_and_processes(monkeypatch):
    """▶ (agent tasks) and ⚙ (shell processes) render side-by-side."""
    cli_obj = _make_cli()
    cli_obj._background_tasks = {"bg_a": _stub_thread()}
    _patch_process_registry(monkeypatch, 2)
    cli_obj._status_bar_visible = True
    cli_obj._get_tui_terminal_width = lambda: 120  # type: ignore[method-assign]
    frags = cli_obj._get_status_bar_fragments()
    rendered = "".join(text for _style, text in frags)
    assert "▶ 1" in rendered
    assert "⚙ 2" in rendered


# ── OpenAI Codex current-session usage indicator ─────────────────────────


def test_codex_session_limit_formatter_uses_remaining_percent():
    assert HermesCLI._format_codex_session_limit(_codex_usage_snapshot(23.4)) == "Codex 77%"


def test_codex_session_limit_formatter_includes_session_reset_countdown():
    assert (
        HermesCLI._format_codex_session_limit(
            _codex_usage_snapshot(23.4, reset_seconds=(2 * 3600) + (10 * 60) + 30)
        )
        == "Codex 77% reset 2h 10m"
    )


def test_snapshot_includes_cached_codex_session_limit_for_codex_provider():
    cli_obj = _make_cli()
    _seed_codex_usage(cli_obj, 12.0)

    snap = cli_obj._get_status_bar_snapshot()

    assert snap["codex_session_limit"] == "Codex 88%"


def test_snapshot_hides_cached_codex_session_limit_for_other_providers():
    cli_obj = _make_cli()
    cli_obj._codex_usage_snapshot = _codex_usage_snapshot(12.0)

    snap = cli_obj._get_status_bar_snapshot()

    assert snap["codex_session_limit"] is None


def test_plain_text_status_shows_codex_session_limit():
    cli_obj = _make_cli()
    _seed_codex_usage(cli_obj, 66.0, reset_seconds=(3 * 3600) + (20 * 60) + 30)

    text = cli_obj._build_status_bar_text(width=100)

    assert "Codex 34% reset 3h 20m" in text


def test_fragments_include_codex_session_limit():
    cli_obj = _make_cli()
    _seed_codex_usage(cli_obj, 94.0)
    cli_obj._status_bar_visible = True
    cli_obj._get_tui_terminal_width = lambda: 120  # type: ignore[method-assign]

    frags = cli_obj._get_status_bar_fragments()
    rendered = "".join(text for _style, text in frags)

    assert "Codex 6%" in rendered
    assert any(style == "class:status-bar-bad" and text == "Codex 6%" for style, text in frags)
