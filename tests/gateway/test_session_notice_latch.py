import json
from datetime import datetime

from gateway.config import GatewayConfig, Platform
from gateway.session import SessionEntry, SessionSource, SessionStore


def _entry(session_key: str = "agent:main:telegram:dm:123") -> SessionEntry:
    now = datetime.now()
    return SessionEntry(
        session_key=session_key,
        session_id="20260608_test",
        created_at=now,
        updated_at=now,
        origin=SessionSource(platform=Platform.TELEGRAM, chat_id="123"),
        platform=Platform.TELEGRAM,
    )


def test_session_entry_loads_missing_notice_map():
    data = _entry().to_dict()
    data.pop("notices_shown")

    loaded = SessionEntry.from_dict(data)

    assert loaded.notices_shown == {}


def test_session_entry_sanitizes_malformed_notice_map():
    base = _entry().to_dict()

    for malformed in (None, "seen", ["notice"], 42):
        data = dict(base, notices_shown=malformed)
        loaded = SessionEntry.from_dict(data)
        assert loaded.notices_shown == {}

    data = dict(
        base,
        notices_shown={
            "codex_gpt55_autoraise": True,
            "false_value": False,
            123: True,
            "truthy_value": "yes",
        },
    )
    loaded = SessionEntry.from_dict(data)

    assert loaded.notices_shown == {
        "codex_gpt55_autoraise": True,
        "truthy_value": True,
    }
    assert loaded.to_dict()["notices_shown"] == {
        "codex_gpt55_autoraise": True,
        "truthy_value": True,
    }


def test_mark_notice_shown_once_persists_and_returns_first_caller(tmp_path):
    store = SessionStore(tmp_path, GatewayConfig())
    entry = _entry()
    store._entries[entry.session_key] = entry
    store._loaded = True
    store._save()

    assert store.mark_notice_shown_once(entry.session_key, "codex_gpt55_autoraise") is True
    assert store.mark_notice_shown_once(entry.session_key, "codex_gpt55_autoraise") is False
    assert store.mark_notice_shown_once(entry.session_key, "other_notice") is True

    reloaded = SessionStore(tmp_path, GatewayConfig())
    reloaded._ensure_loaded()

    assert reloaded._entries[entry.session_key].notices_shown == {
        "codex_gpt55_autoraise": True,
        "other_notice": True,
    }

    saved = json.loads((tmp_path / "sessions.json").read_text())
    assert saved[entry.session_key]["notices_shown"]["codex_gpt55_autoraise"] is True


def test_fresh_session_entry_starts_with_no_notice_keys():
    first = _entry("agent:main:telegram:dm:first")
    second = _entry("agent:main:telegram:dm:second")
    first.notices_shown["codex_gpt55_autoraise"] = True

    assert second.notices_shown == {}


def test_force_new_session_resets_notice_eligibility(tmp_path):
    store = SessionStore(tmp_path, GatewayConfig())
    source = SessionSource(platform=Platform.TELEGRAM, chat_id="123")

    first = store.get_or_create_session(source)
    assert store.mark_notice_shown_once(first.session_key, "codex_gpt55_autoraise") is True
    assert store.mark_notice_shown_once(first.session_key, "codex_gpt55_autoraise") is False

    reset = store.get_or_create_session(source, force_new=True)

    assert reset.session_key == first.session_key
    assert reset.session_id != first.session_id
    assert reset.notices_shown == {}
    assert store.mark_notice_shown_once(reset.session_key, "codex_gpt55_autoraise") is True
