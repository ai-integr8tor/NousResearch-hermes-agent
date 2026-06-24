"""Tests for SessionDB.active_session_count() — O(1) active session counting."""

import time

import pytest

from hermes_state import SessionDB


@pytest.fixture
def db(tmp_path):
    database = SessionDB(tmp_path / "state.db")
    try:
        yield database
    finally:
        database.close()


def test_active_session_count_empty(db):
    assert db.active_session_count() == 0


def test_active_session_count_with_active_sessions(db):
    now = time.time()
    sid1 = db.create_session("s1", source="cli")
    sid2 = db.create_session("s2", source="cli")
    db.append_message(sid1, "user", "hello")
    db.append_message(sid2, "user", "world")
    assert db.active_session_count(idle_secs=300) == 2


def test_active_session_count_excludes_ended(db):
    sid1 = db.create_session("s1", source="cli")
    sid2 = db.create_session("s2", source="cli")
    db.append_message(sid1, "user", "hello")
    db.append_message(sid2, "user", "world")
    db.end_session(sid1, end_reason="completed")
    assert db.active_session_count(idle_secs=300) == 1


def test_active_session_count_excludes_idle(db):
    sid = db.create_session("s1", source="cli")
    db.append_message(sid, "user", "hello")
    # Backdate the message to 10 minutes ago
    old_time = time.time() - 600
    db._conn.execute(
        "UPDATE messages SET timestamp = ? WHERE session_id = ?",
        (old_time, sid),
    )
    db._conn.commit()
    assert db.active_session_count(idle_secs=300) == 0


def test_active_session_count_respects_idle_secs(db):
    sid = db.create_session("s1", source="cli")
    db.append_message(sid, "user", "hello")
    old_time = time.time() - 400
    db._conn.execute(
        "UPDATE messages SET timestamp = ? WHERE session_id = ?",
        (old_time, sid),
    )
    db._conn.commit()
    # idle_secs=300 should exclude it, idle_secs=500 should include it
    assert db.active_session_count(idle_secs=300) == 0
    assert db.active_session_count(idle_secs=500) == 1
