"""Tests for strict gateway auto-continue resume-marker behavior.

A trailing tool result alone is not sufficient to auto-continue gateway work.
Only sessions explicitly marked ``resume_pending`` by gateway restart/shutdown
recovery should receive the restart-resume system note.
"""

from datetime import datetime

from gateway.run import _is_fresh_gateway_interruption
from gateway.session import SessionEntry


def _simulate_strict_auto_continue(
    *,
    resume_entry: SessionEntry | None,
    user_message: str,
    window_secs: float = 3600,
) -> str:
    """Reproduce the strict resume-marker predicate from gateway/run.py."""
    has_resume_pending = bool(
        resume_entry is not None
        and getattr(resume_entry, "resume_pending", False)
    )
    marker_is_fresh = (
        _is_fresh_gateway_interruption(
            getattr(resume_entry, "last_resume_marked_at", None),
            window_secs=window_secs,
        )
        if has_resume_pending
        else False
    )
    if has_resume_pending and marker_is_fresh:
        return (
            "[System note: A new message has arrived. The previous turn "
            "was interrupted by a gateway restart. "
            "Address the user's NEW message below FIRST. "
            "Do NOT re-execute old tool calls — skip any unfinished "
            "work from the conversation history and focus on what the "
            "user is asking now.]\n\n"
            + user_message
        )
    return user_message


def _pending_entry(*, marked_at=None) -> SessionEntry:
    now = datetime.now()
    return SessionEntry(
        session_key="agent:main:telegram:dm:1",
        session_id="sid",
        created_at=now,
        updated_at=now,
        resume_pending=True,
        resume_reason="restart_timeout",
        last_resume_marked_at=marked_at if marked_at is not None else now,
    )


class TestStrictResumeMarker:
    def test_trailing_tool_result_without_marker_does_not_trigger_note(self):
        result = _simulate_strict_auto_continue(
            resume_entry=None,
            user_message="what happened?",
        )
        assert result == "what happened?"

    def test_explicit_resume_marker_triggers_note(self):
        result = _simulate_strict_auto_continue(
            resume_entry=_pending_entry(),
            user_message="what happened?",
        )
        assert "[System note:" in result
        assert "gateway restart" in result
        assert "NEW message" in result
        assert "Do NOT re-execute" in result
        assert result.endswith("what happened?")

    def test_pending_entry_without_marker_timestamp_fails_closed(self):
        entry = _pending_entry()
        entry.last_resume_marked_at = None
        result = _simulate_strict_auto_continue(
            resume_entry=entry,
            user_message="start new work",
        )
        assert result == "start new work"

    def test_empty_history_no_note_without_marker(self):
        result = _simulate_strict_auto_continue(
            resume_entry=None,
            user_message="hello",
        )
        assert result == "hello"


class TestInterruptedReplayFiltering:
    def test_interrupted_tool_tail_is_removed_from_agent_history(self):
        from gateway.run import _build_gateway_agent_history

        history = [
            {"role": "user", "content": "transcribe this video"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "terminal", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '{"exit_code": 130, "output": "[Command interrupted]"}',
            },
        ]

        agent_history, observed_context = _build_gateway_agent_history(history)

        assert observed_context is None
        assert agent_history == [{"role": "user", "content": "transcribe this video"}]

    def test_mixed_tail_with_one_interrupted_result_is_removed(self):
        from gateway.run import _build_gateway_agent_history

        history = [
            {"role": "user", "content": "search and transcribe"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "web_search", "arguments": "{}"}},
                    {"id": "call_2", "function": {"name": "terminal", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "found URL"},
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": '{"exit_code": 130, "output": "[Command interrupted]"}',
            },
        ]

        agent_history, _observed_context = _build_gateway_agent_history(history)

        assert agent_history == [{"role": "user", "content": "search and transcribe"}]

    def test_successful_tool_tail_is_preserved(self):
        from gateway.run import _build_gateway_agent_history

        history = [
            {"role": "user", "content": "deploy"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "terminal", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "deployed successfully"},
        ]

        agent_history, _observed_context = _build_gateway_agent_history(history)

        assert agent_history[-1]["role"] == "tool"
        assert agent_history[-1]["content"] == "deployed successfully"

    def test_dangling_unanswered_tool_call_tail_is_removed(self):
        """A trailing assistant(tool_calls) with NO tool answers is stripped.

        This is the SIGKILL signature from #49201: the tool itself ran a
        restart/shutdown command and killed the gateway before its result was
        persisted. The transcript tail is an assistant message with tool_calls
        and zero matching tool rows. Without stripping it, the model re-issues
        the unanswered call on resume and loops the restart forever.
        """
        from gateway.run import _build_gateway_agent_history

        history = [
            {"role": "user", "content": "restart the container"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "terminal",
                            "arguments": '{"command": "docker restart hermes-agent"}',
                        },
                    },
                ],
            },
        ]

        agent_history, _observed_context = _build_gateway_agent_history(history)

        assert agent_history == [{"role": "user", "content": "restart the container"}]

    def test_dangling_tail_after_completed_pair_is_removed_only_at_tail(self):
        """Only the trailing unanswered tool-call block is stripped.

        An earlier completed assistant→tool pair must survive — we only drop
        the final assistant(tool_calls) that has no answers.
        """
        from gateway.run import _build_gateway_agent_history

        history = [
            {"role": "user", "content": "do two things"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "web_search", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "found it"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_2",
                        "function": {
                            "name": "terminal",
                            "arguments": '{"command": "systemctl restart hermes"}',
                        },
                    },
                ],
            },
        ]

        agent_history, _observed_context = _build_gateway_agent_history(history)

        # The completed call_1 pair survives; the dangling call_2 tail is gone.
        assert agent_history[-1]["role"] == "tool"
        assert agent_history[-1]["content"] == "found it"
        # The surviving assistant(tool_calls) is the completed call_1 (which
        # has a matching tool answer), not the stripped dangling call_2.
        _surviving_calls = [
            tc.get("id")
            for m in agent_history
            if m.get("role") == "assistant" and m.get("tool_calls")
            for tc in m["tool_calls"]
        ]
        assert _surviving_calls == ["call_1"]

    def test_persisted_auto_continue_note_is_not_replayed(self):
        from gateway.run import _build_gateway_agent_history

        history = [
            {"role": "user", "content": "first real question"},
            {
                "role": "user",
                "content": (
                    "[System note: Your previous turn was interrupted before you could "
                    "process the last tool result(s).]\n\nsecond real question"
                ),
            },
            {"role": "assistant", "content": "answer"},
            {
                "role": "user",
                "content": (
                    "[System note: A new message has arrived. The conversation "
                    "history contains pending tool outputs from an interrupted turn.]\n\nthird"
                ),
            },
        ]

        agent_history, _observed_context = _build_gateway_agent_history(history)

        assert agent_history == [
            {"role": "user", "content": "first real question"},
            {"role": "user", "content": "second real question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "third"},
        ]
