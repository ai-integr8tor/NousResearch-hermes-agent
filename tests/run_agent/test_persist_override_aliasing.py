"""Regression tests for the persist-override aliasing bug (#48677).

The crash-resilience early persist runs on the *same* ``messages`` list the
model request is later built from. Applying the clean persist-override in place
there stripped the API-facing user message (observed-group context, voice
prefix, …) before it reached the model — silently dropping context.

These tests pin the contract: persistence sees the clean override, but the live
``messages`` list and its dicts are never mutated, and the SQLite row is written
exactly once.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

SESSION_ID = "test-persist-override-aliasing"


def _make_agent(session_db):
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        from run_agent import AIAgent

        agent = AIAgent(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            model="test/model",
            quiet_mode=True,
            session_db=session_db,
            session_id=SESSION_ID,
            skip_context_files=True,
            skip_memory=True,
        )
    agent._ensure_db_session()
    return agent


def _user_contents(db):
    return [
        row["content"]
        for row in db.get_messages(SESSION_ID)
        if row["role"] == "user"
    ]


def test_early_persist_does_not_strip_api_facing_user_message():
    """The live message keeps its wrapped content; the DB row is clean."""
    from hermes_state import SessionDB

    wrapped = (
        "<observed_context>\n[Alice] did you see the deploy?\n</observed_context>\n"
        "what do you think of this?"
    )
    bare = "what do you think of this?"

    with tempfile.TemporaryDirectory() as tmpdir:
        db = SessionDB(db_path=Path(tmpdir) / "t.db")
        try:
            agent = _make_agent(db)

            user_msg = {"role": "user", "content": wrapped}
            messages = [user_msg]
            agent._persist_user_message_idx = 0
            agent._persist_user_message_override = bare
            agent._persist_user_message_clean_cache = None

            # Crash-resilience early persist (before the model request is built).
            agent._persist_session(messages, conversation_history=[])

            # The live list/dict the API request is built from is untouched.
            assert messages[0] is user_msg
            assert messages[0]["content"] == wrapped

            # The persisted transcript is clean.
            assert _user_contents(db) == [bare]
        finally:
            db.close()


def test_repeated_persist_points_write_user_row_once():
    """Early + terminal persist must not duplicate the user row."""
    from hermes_state import SessionDB

    wrapped = "API-only synthetic prefix\nhello"
    bare = "hello"

    with tempfile.TemporaryDirectory() as tmpdir:
        db = SessionDB(db_path=Path(tmpdir) / "t.db")
        try:
            agent = _make_agent(db)

            user_msg = {"role": "user", "content": wrapped}
            messages = [user_msg]
            agent._persist_user_message_idx = 0
            agent._persist_user_message_override = bare
            agent._persist_user_message_clean_cache = None

            agent._persist_session(messages, conversation_history=[])
            agent._persist_session(messages, conversation_history=[])

            assert _user_contents(db) == [bare]
            assert messages[0]["content"] == wrapped
        finally:
            db.close()
