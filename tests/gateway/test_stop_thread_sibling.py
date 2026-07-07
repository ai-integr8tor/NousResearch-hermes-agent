"""Regression tests: /stop can interrupt a sibling participant's run in a
per-user thread.

When ``thread_sessions_per_user=True``, each participant in a thread gets an
isolated session key (``...:{thread_id}:{user_id}``).  A run another user
started lives under a different key, so the caller's own ``/stop`` used to find
nothing and reply "no active task to stop".  Authorized users should be able to
stop any run in the same thread.
"""

import pytest

from gateway.run import GatewayRunner, _AGENT_PENDING_SENTINEL, _INTERRUPT_REASON_STOP
from gateway.session import SessionSource, build_session_key
from gateway.platforms.base import Platform, MessageEvent, MessageType


class _FakeAgent:
    pass


def _thread_source(uid, thread_id="thr1", chat_id="chan1"):
    return SessionSource(
        platform=Platform.DISCORD,
        chat_type="forum",
        chat_id=chat_id,
        thread_id=thread_id,
        user_id=uid,
    )


def _per_user_key(uid, thread_id="thr1", chat_id="chan1"):
    return build_session_key(
        _thread_source(uid, thread_id, chat_id),
        thread_sessions_per_user=True,
    )


def _dm_source(uid="@alice:ex", thread_id=None, chat_id="!dm:ex"):
    return SessionSource(
        platform=Platform.MATRIX,
        chat_type="dm",
        chat_id=chat_id,
        thread_id=thread_id,
        user_id=uid,
    )


def _dm_thread_key(thread_id="$root", chat_id="!dm:ex"):
    return build_session_key(_dm_source(thread_id=thread_id, chat_id=chat_id))


# ---------------------------------------------------------------------------
# _sibling_thread_run_keys
# ---------------------------------------------------------------------------


def test_sibling_finds_other_users_run_in_same_thread():
    runner = object.__new__(GatewayRunner)
    key_a = _per_user_key("userA")
    key_b = _per_user_key("userB")
    runner._running_agents = {key_b: _FakeAgent()}
    assert runner._sibling_thread_run_keys(_thread_source("userA"), key_a) == [key_b]


def test_sibling_excludes_callers_own_key():
    runner = object.__new__(GatewayRunner)
    key_a = _per_user_key("userA")
    key_b = _per_user_key("userB")
    runner._running_agents = {key_a: _FakeAgent(), key_b: _FakeAgent()}
    assert runner._sibling_thread_run_keys(_thread_source("userA"), key_a) == [key_b]


def test_sibling_skips_pending_sentinel():
    runner = object.__new__(GatewayRunner)
    key_a = _per_user_key("userA")
    key_b = _per_user_key("userB")
    runner._running_agents = {key_b: _AGENT_PENDING_SENTINEL}
    assert runner._sibling_thread_run_keys(_thread_source("userA"), key_a) == []


def test_sibling_does_not_match_different_thread_same_chat():
    # thr1 caller must not match a run in thr11 (prefix-collision guard).
    runner = object.__new__(GatewayRunner)
    key_a = _per_user_key("userA", thread_id="thr1")
    key_b_other = _per_user_key("userB", thread_id="thr11")
    runner._running_agents = {key_b_other: _FakeAgent()}
    assert runner._sibling_thread_run_keys(_thread_source("userA"), key_a) == []


def test_sibling_returns_empty_for_non_thread_source():
    # Non-thread group/channel must NOT trigger the cross-user fallback.
    runner = object.__new__(GatewayRunner)
    nonthread = SessionSource(
        platform=Platform.DISCORD, chat_type="group", chat_id="chan1", user_id="userA"
    )
    grp_b = build_session_key(
        SessionSource(
            platform=Platform.DISCORD, chat_type="group", chat_id="chan1", user_id="userB"
        )
    )
    runner._running_agents = {grp_b: _FakeAgent()}
    assert runner._sibling_thread_run_keys(nonthread, "agent:main:discord:group:chan1:userA") == []


def test_dm_sibling_finds_threaded_runs_in_same_dm():
    runner = object.__new__(GatewayRunner)
    stop_key = build_session_key(_dm_source(thread_id=None))
    run_key = _dm_thread_key("$root-event")
    runner._running_agents = {run_key: _FakeAgent()}

    assert runner._sibling_dm_thread_run_keys(_dm_source(thread_id=None), stop_key) == [run_key]


def test_dm_sibling_ignores_other_dm_rooms_and_pending_sentinel():
    runner = object.__new__(GatewayRunner)
    stop_key = build_session_key(_dm_source(thread_id=None))
    same_room_pending = _dm_thread_key("$pending")
    other_room = _dm_thread_key("$root-event", chat_id="!other:ex")
    runner._running_agents = {
        same_room_pending: _AGENT_PENDING_SENTINEL,
        other_room: _FakeAgent(),
    }

    assert runner._sibling_dm_thread_run_keys(_dm_source(thread_id=None), stop_key) == []


def test_dm_sibling_ignores_threaded_stop_source():
    runner = object.__new__(GatewayRunner)
    stop_source = _dm_source(thread_id="$idle-thread")
    stop_key = build_session_key(stop_source)
    run_key = _dm_thread_key("$root-event")
    runner._running_agents = {run_key: _FakeAgent()}

    assert runner._sibling_dm_thread_run_keys(stop_source, stop_key) == []


def test_dm_sibling_is_matrix_only():
    runner = object.__new__(GatewayRunner)
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_type="dm",
        chat_id="dm1",
        thread_id=None,
        user_id="userA",
    )
    run_key = build_session_key(
        SessionSource(
            platform=Platform.DISCORD,
            chat_type="dm",
            chat_id="dm1",
            thread_id="thread1",
            user_id="userA",
        )
    )
    stop_key = build_session_key(source)
    runner._running_agents = {run_key: _FakeAgent()}

    assert runner._sibling_dm_thread_run_keys(source, stop_key) == []


# ---------------------------------------------------------------------------
# _handle_stop_command fallback path
# ---------------------------------------------------------------------------


class _StoreEntry:
    def __init__(self, session_key):
        self.session_key = session_key


class _FakeStore:
    def __init__(self, session_key):
        self._key = session_key

    def get_or_create_session(self, source):
        return _StoreEntry(self._key)


@pytest.mark.asyncio
async def test_stop_interrupts_sibling_thread_run_when_authorized(monkeypatch):
    runner = object.__new__(GatewayRunner)
    key_a = _per_user_key("userA")
    key_b = _per_user_key("userB")
    runner._running_agents = {key_b: _FakeAgent()}
    runner.session_store = _FakeStore(key_a)

    interrupted = []

    async def _fake_interrupt(session_key, source, *, interrupt_reason, invalidation_reason):
        interrupted.append((session_key, interrupt_reason, invalidation_reason))

    runner._interrupt_and_clear_session = _fake_interrupt
    runner._is_user_authorized = lambda source: True

    event = MessageEvent(
        text="/stop", message_type=MessageType.TEXT, source=_thread_source("userA")
    )
    result = await runner._handle_stop_command(event)

    assert interrupted == [(key_b, _INTERRUPT_REASON_STOP, "stop_command_thread_sibling")]
    # EphemeralReply or str — both carry the "stopped" message, not "no_active".
    assert "no active" not in str(getattr(result, "text", result)).lower()


@pytest.mark.asyncio
async def test_stop_from_threaded_dm_does_not_interrupt_other_dm_thread(monkeypatch):
    runner = object.__new__(GatewayRunner)
    stop_source = _dm_source(thread_id="$idle-thread")
    stop_key = build_session_key(stop_source)
    run_key = _dm_thread_key("$root-event")
    runner._running_agents = {run_key: _FakeAgent()}
    runner.session_store = _FakeStore(stop_key)

    interrupted = []

    async def _fake_interrupt(session_key, source, *, interrupt_reason, invalidation_reason):
        interrupted.append((session_key, interrupt_reason, invalidation_reason))

    runner._interrupt_and_clear_session = _fake_interrupt
    runner._is_user_authorized = lambda source: False

    event = MessageEvent(
        text="/stop", message_type=MessageType.TEXT, source=stop_source
    )
    result = await runner._handle_stop_command(event)

    assert interrupted == []
    assert "no active" in str(getattr(result, "text", result)).lower()


@pytest.mark.asyncio
async def test_stop_does_not_interrupt_sibling_when_unauthorized(monkeypatch):
    runner = object.__new__(GatewayRunner)
    key_a = _per_user_key("userA")
    key_b = _per_user_key("userB")
    runner._running_agents = {key_b: _FakeAgent()}
    runner.session_store = _FakeStore(key_a)

    interrupted = []

    async def _fake_interrupt(session_key, source, *, interrupt_reason, invalidation_reason):
        interrupted.append(session_key)

    runner._interrupt_and_clear_session = _fake_interrupt
    runner._is_user_authorized = lambda source: False

    event = MessageEvent(
        text="/stop", message_type=MessageType.TEXT, source=_thread_source("userA")
    )
    result = await runner._handle_stop_command(event)

    assert interrupted == []
    assert "no active" in str(getattr(result, "text", result)).lower()


@pytest.mark.asyncio
async def test_stop_interrupts_threaded_dm_run_from_root_dm(monkeypatch):
    runner = object.__new__(GatewayRunner)
    stop_key = build_session_key(_dm_source(thread_id=None))
    run_key = _dm_thread_key("$root-event")
    runner._running_agents = {run_key: _FakeAgent()}
    runner.session_store = _FakeStore(stop_key)

    interrupted = []

    async def _fake_interrupt(session_key, source, *, interrupt_reason, invalidation_reason):
        interrupted.append((session_key, interrupt_reason, invalidation_reason))

    runner._interrupt_and_clear_session = _fake_interrupt
    runner._is_user_authorized = lambda source: False

    event = MessageEvent(
        text="/stop", message_type=MessageType.TEXT, source=_dm_source(thread_id=None)
    )
    result = await runner._handle_stop_command(event)

    assert interrupted == [
        (run_key, _INTERRUPT_REASON_STOP, "stop_command_dm_thread_sibling")
    ]
    assert "no active" not in str(getattr(result, "text", result)).lower()
