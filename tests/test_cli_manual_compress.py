from contextlib import contextmanager

from cli import HermesCLI


class DummyAgent:
    def __init__(self):
        self.compression_enabled = True
        self._cached_system_prompt = "FULL CACHED SYSTEM PROMPT SHOULD NOT BE NESTED"
        self.session_id = "new-session"
        self.calls = []

    def _compress_context(
        self,
        messages,
        system_message,
        *,
        approx_tokens=None,
        focus_topic=None,
        force=False,
        force_in_place=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "system_message": system_message,
                "approx_tokens": approx_tokens,
                "focus_topic": focus_topic,
                "force": force,
                "force_in_place": force_in_place,
            }
        )
        return ([{"role": "user", "content": "[CONTEXT SUMMARY]: compacted"}], "new system prompt")


@contextmanager
def _busy_context(status: str):
    _ = status
    yield


def _make_cli() -> HermesCLI:
    cli = HermesCLI.__new__(HermesCLI)
    cli.conversation_history = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
        {"role": "assistant", "content": "four"},
    ]
    cli.agent = DummyAgent()
    cli.session_id = "old-session"
    cli._pending_title = "old title"
    cli._busy_command = _busy_context
    return cli


def _patch_feedback(monkeypatch):
    monkeypatch.setattr(
        "agent.manual_compression_feedback.summarize_manual_compression",
        lambda *args, **kwargs: {
            "noop": False,
            "headline": "compressed",
            "token_line": "tokens reduced",
            "note": "",
        },
    )


def test_manual_compress_does_not_pass_cached_system_prompt(monkeypatch):
    """Manual /compress should rebuild the next prompt without nesting the old one."""
    cli = _make_cli()
    _patch_feedback(monkeypatch)

    cli._manual_compress("/compress database schema")

    agent = cli.agent
    assert isinstance(agent, DummyAgent)
    assert len(agent.calls) == 1
    call = agent.calls[0]
    assert call["system_message"] is None
    assert call["system_message"] != agent._cached_system_prompt
    assert call["focus_topic"] == "database schema"
    assert call["force_in_place"] is None
    assert cli.session_id == "new-session"
    assert cli._pending_title is None


def test_compress_child_flag_forces_legacy_rotation(monkeypatch):
    """/compress --child is a one-shot in_place=False override."""
    cli = _make_cli()
    _patch_feedback(monkeypatch)

    cli._manual_compress("/compress --child database schema")

    agent = cli.agent
    assert isinstance(agent, DummyAgent)
    assert len(agent.calls) == 1
    call = agent.calls[0]
    assert call["focus_topic"] == "database schema"
    assert call["force_in_place"] is False


def test_childcompress_command_forces_legacy_rotation(monkeypatch):
    """/childcompress mirrors /compress but forces child continuation."""
    cli = _make_cli()
    _patch_feedback(monkeypatch)

    cli._manual_compress("/childcompress database schema", force_in_place=False)

    agent = cli.agent
    assert isinstance(agent, DummyAgent)
    assert len(agent.calls) == 1
    call = agent.calls[0]
    assert call["focus_topic"] == "database schema"
    assert call["force_in_place"] is False
