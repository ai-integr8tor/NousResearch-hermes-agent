"""Regression tests for cronjob tool availability gating."""

import model_tools

from tools.cronjob_tools import check_cronjob_requirements


def test_cronjob_available_from_gateway_session_contextvars(monkeypatch):
    """Gateway turns bind session identity in ContextVars, not env vars."""
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)

    tokens = set_session_vars(
        platform="matrix",
        chat_id="!room:example.org",
        user_id="@user:example.org",
    )
    try:
        assert check_cronjob_requirements() is True
    finally:
        clear_session_vars(tokens)


def test_cached_missing_cronjob_refreshes_after_gateway_context(monkeypatch):
    """A no-session check must not hide cronjob after a gateway context appears."""
    from gateway.session_context import clear_session_vars, set_session_vars
    from tools.registry import invalidate_check_fn_cache

    for name in (
        "HERMES_INTERACTIVE",
        "HERMES_GATEWAY_SESSION",
        "HERMES_EXEC_ASK",
        "HERMES_SESSION_PLATFORM",
        "HERMES_SESSION_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    clear_session_vars([])
    model_tools._clear_tool_defs_cache()
    invalidate_check_fn_cache()

    def cronjob_names() -> set[str]:
        return {
            tool["function"]["name"]
            for tool in model_tools.get_tool_definitions(
                enabled_toolsets=["cronjob"],
                quiet_mode=True,
            )
        }

    assert "cronjob" not in cronjob_names()

    tokens = set_session_vars(
        platform="matrix",
        chat_id="!room:example.org",
        user_id="@user:example.org",
    )
    try:
        assert "cronjob" in cronjob_names()
    finally:
        clear_session_vars(tokens)
        model_tools._clear_tool_defs_cache()
        invalidate_check_fn_cache()


def test_cached_missing_cronjob_refreshes_after_gateway_env(monkeypatch):
    """A pre-gateway lookup must not hide cronjob after HERMES_EXEC_ASK appears."""
    from gateway.session_context import clear_session_vars
    from tools.registry import invalidate_check_fn_cache

    for name in (
        "HERMES_INTERACTIVE",
        "HERMES_GATEWAY_SESSION",
        "HERMES_EXEC_ASK",
        "HERMES_SESSION_PLATFORM",
        "HERMES_SESSION_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    clear_session_vars([])
    model_tools._clear_tool_defs_cache()
    invalidate_check_fn_cache()

    def cronjob_names() -> set[str]:
        return {
            tool["function"]["name"]
            for tool in model_tools.get_tool_definitions(
                enabled_toolsets=["cronjob"],
                quiet_mode=True,
            )
        }

    assert "cronjob" not in cronjob_names()

    monkeypatch.setenv("HERMES_EXEC_ASK", "1")
    try:
        assert "cronjob" in cronjob_names()
    finally:
        clear_session_vars([])
        model_tools._clear_tool_defs_cache()
        invalidate_check_fn_cache()
