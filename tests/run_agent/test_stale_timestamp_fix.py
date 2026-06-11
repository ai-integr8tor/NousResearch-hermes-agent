"""
Tests for PR #15872: prevent stale timestamp perception by injecting
current time per-turn into user messages (not system prompt).

Core invariant: "Current time:" must NEVER appear in the system prompt
(which would break prompt cache prefix). It must appear in user messages.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


class TestFormatCurrentTimeContext:
    """Unit tests for hermes_time.format_current_time_context()"""

    def test_basic_output_contains_current_time(self):
        from hermes_time import format_current_time_context
        # June 11, 2026 is a Thursday
        dt = datetime(2026, 6, 11, 15, 30, tzinfo=timezone.utc)
        result = format_current_time_context(dt)
        assert "Current time:" in result
        assert "Thursday" in result
        assert "June 11, 2026" in result

    def test_timezone_line_when_configured(self):
        from hermes_time import format_current_time_context
        hkt = timezone(timedelta(hours=8))
        dt = datetime(2026, 6, 11, 15, 30, tzinfo=hkt)
        with patch("hermes_time.get_timezone", return_value=hkt):
            result = format_current_time_context(dt)
            assert "UTC+08:00" in result

    def test_no_timezone_line_when_not_configured(self):
        from hermes_time import format_current_time_context
        with patch("hermes_time.get_timezone", return_value=None):
            result = format_current_time_context(
                datetime(2026, 6, 11, 15, 30)
            )
            lines = result.split("\n")
            assert len(lines) == 1
            assert "Current time:" in lines[0]

    def test_explicit_datetime_passthrough(self):
        from hermes_time import format_current_time_context
        dt = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        result = format_current_time_context(dt)
        assert "January 01, 2025" in result

    def test_dst_aware_offset(self):
        from hermes_time import format_current_time_context
        est = timezone(timedelta(hours=-5))
        edt = timezone(timedelta(hours=-4))
        with patch("hermes_time.get_timezone", return_value=est):
            assert "UTC-05:00" in format_current_time_context(
                datetime(2026, 1, 15, 12, 0, tzinfo=est)
            )
        with patch("hermes_time.get_timezone", return_value=edt):
            assert "UTC-04:00" in format_current_time_context(
                datetime(2026, 7, 15, 12, 0, tzinfo=edt)
            )


class TestCacheSafety:
    """Verify that volatile 'Current time:' never leaks into the system prompt."""

    def test_system_prompt_source_excludes_current_time(self):
        """Source code of system_prompt.py must not inject 'Current time:'."""
        import agent.system_prompt as sp
        import inspect
        source = inspect.getsource(sp)
        # The only "Current time" reference should be in comments (PR rationale)
        # NOT in any f-string or format that produces system prompt output
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # comments are fine
            # Any non-comment line that puts "Current time:" into the prompt is a bug
            assert 'Current time:' not in stripped or 'not' in stripped.lower() or 'never' in stripped.lower(), (
                f"Volatile 'Current time:' found in system_prompt.py source: {stripped}"
            )

    def test_system_prompt_uses_session_started_label(self):
        """Source code should use 'Session started:' not 'Conversation started:'."""
        import agent.system_prompt as sp
        import inspect
        source = inspect.getsource(sp)
        assert "Session started:" in source, (
            "system_prompt.py should contain 'Session started:' label"
        )
        # "Conversation started:" should NOT appear in format strings
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "f\"" in stripped or "f'" in stripped:
                assert "Conversation started:" not in stripped, (
                    f"Still using 'Conversation started:' in format string: {stripped}"
                )


class TestTurnContextTimeInjection:
    """Verify that turn_context.py injects current time into plugin_user_context."""

    def test_turn_context_source_has_time_injection(self):
        """turn_context.py source should call format_current_time_context."""
        import agent.turn_context as tc
        import inspect
        source = inspect.getsource(tc)
        assert "format_current_time_context" in source, (
            "turn_context.py should import and call format_current_time_context()"
        )
        assert "plugin_user_context" in source, (
            "Time injection should target plugin_user_context"
        )

    def test_time_prepended_to_plugin_user_context(self):
        """Time block should be prepended (not appended) to plugin_user_context."""
        import agent.turn_context as tc
        import inspect
        source = inspect.getsource(tc)
        # The injection pattern should prepend time before existing context
        assert "_time_block" in source, (
            "Should use _time_block variable for time context"
        )


class TestMaxIterationsTimeInjection:
    """Verify that handle_max_iterations injects current time."""

    def test_max_iterations_source_has_time_injection(self):
        """chat_completion_helpers.py should inject time into summary request."""
        import agent.chat_completion_helpers as chc
        import inspect
        source = inspect.getsource(chc.handle_max_iterations)
        assert "format_current_time_context" in source, (
            "handle_max_iterations should call format_current_time_context()"
        )

    def test_time_injected_before_summary_request(self):
        """Time should be prepended to the summary request, not after it."""
        import agent.chat_completion_helpers as chc
        import inspect
        source = inspect.getsource(chc.handle_max_iterations)
        # The time block should appear before "messages.append" in the source
        time_pos = source.find("format_current_time_context")
        append_pos = source.find('messages.append({"role": "user"')
        assert time_pos < append_pos, (
            "Time injection should happen BEFORE appending to messages"
        )
