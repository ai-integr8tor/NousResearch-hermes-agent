import json

from agent import degraded_mode_notify as notify
from agent.degraded_mode_notify import format_fallback_message, notify_degraded_mode


def test_format_fallback_message_mentions_models_and_policy():
    msg = format_fallback_message(
        old_model="gpt-primary",
        new_model="qwen3.6-27b-q4km",
        provider="local-llm",
        reason="auth",
    )

    assert "gpt-primary" in msg
    assert "qwen3.6-27b-q4km" in msg
    assert "local-llm" in msg
    assert "capability policy" in msg


def test_notify_degraded_mode_is_rate_limited(monkeypatch):
    sent = []

    def fake_send(args):
        sent.append(args)
        return json.dumps({"ok": True})

    monkeypatch.setattr(notify, "_notify_enabled", lambda: True)
    monkeypatch.setattr("tools.send_message_tool.send_message_tool", fake_send)
    notify._LAST_SENT.clear()

    assert notify_degraded_mode(kind="fallback", key="same", message="hello", cooldown_seconds=60)
    assert not notify_degraded_mode(kind="fallback", key="same", message="hello", cooldown_seconds=60)

    assert len(sent) == 1
    assert sent[0]["target"] == "telegram"
