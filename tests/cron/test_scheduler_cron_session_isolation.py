"""Regression test for cron-session approval isolation.

When ``approvals.cron_mode=deny``, cron jobs should still block their own
``execute_code`` calls, but that cron context must not leak into the next normal
interactive gateway turn handled by the same process.
"""

from __future__ import annotations

import os

import pytest

import cron.scheduler as cron_scheduler
from gateway.session_context import clear_session_vars, set_session_vars
from tools import approval as approval_module


class _FakeCronAgent:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def run_conversation(self, prompt: str, conversation_history=None, task_id=None):
        result = approval_module.check_execute_code_guard("import os; print(1)", "local")
        assert result["approved"] is False
        assert result["outcome"] == "blocked"
        return {"final_response": "cron execute_code blocked", "messages": []}


@pytest.fixture(autouse=True)
def _clear_approval_state(monkeypatch):
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
    approval_module._permanent_approved.clear()
    approval_module.clear_session("default")
    approval_module.clear_session("cron-isolation-session")
    yield
    approval_module._permanent_approved.clear()
    approval_module.clear_session("default")
    approval_module.clear_session("cron-isolation-session")


def _register_gateway_auto_approve(session_key: str, result: str = "once") -> None:
    def _notify(_approval_data):
        with approval_module._lock:
            entries = approval_module._gateway_queues.get(session_key, [])
            if entries:
                entry = entries[-1]
                entry.result = result
                entry.event.set()

    with approval_module._lock:
        approval_module._gateway_notify_cbs[session_key] = _notify



def test_run_job_cron_execute_code_deny_does_not_pollute_later_gateway_execute_code(
    monkeypatch, tmp_path
):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "cron").mkdir()
    (hermes_home / "cron" / "output").mkdir()
    (hermes_home / "config.yaml").write_text("approvals:\n  cron_mode: deny\n", encoding="utf-8")
    (hermes_home / ".env").write_text("", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    monkeypatch.setattr(approval_module, "_get_approval_mode", lambda: "manual")
    monkeypatch.setattr(approval_module, "_get_cron_approval_mode", lambda: "deny")
    monkeypatch.setattr("run_agent.AIAgent", _FakeCronAgent)
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda requested=None, **kwargs: {
            "provider": "openai",
            "api_mode": "chat_completions",
            "base_url": "https://example.invalid/v1",
            "api_key": "test-key",
        },
    )
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.format_runtime_provider_error", lambda exc: str(exc)
    )
    monkeypatch.setattr("tools.mcp_tool.discover_mcp_tools", lambda: [])

    success, output, final_response, error = cron_scheduler.run_job(
        {"id": "job-1", "name": "Cron Isolation Test", "prompt": "Run safely"}
    )

    assert success is True
    assert error is None
    assert final_response == "cron execute_code blocked"
    assert "cron execute_code blocked" in output
    assert os.getenv("HERMES_CRON_SESSION") is None

    session_key = "cron-isolation-session"
    token = approval_module.set_current_session_key(session_key)
    session_tokens = set_session_vars(
        platform="discord",
        chat_id="123",
        session_key=session_key,
        cron_session="",
    )
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    try:
        _register_gateway_auto_approve(session_key)
        result = approval_module.check_execute_code_guard("import os; print(2)", "local")
        assert result["approved"] is True
        assert result.get("user_approved") is True
    finally:
        clear_session_vars(session_tokens)
        approval_module.reset_current_session_key(token)
        with approval_module._lock:
            approval_module._gateway_queues.pop(session_key, None)
            approval_module._gateway_notify_cbs.pop(session_key, None)
