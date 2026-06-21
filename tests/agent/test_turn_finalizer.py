"""Tests for agent/turn_finalizer.py — graceful degradation on persist failure."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from agent.turn_finalizer import finalize_turn


def _base_agent():
    agent = MagicMock()
    agent.max_iterations = 1
    agent.iteration_budget.remaining = 1
    agent.quiet_mode = True
    agent.session_id = "session-1"
    agent.model = "test-model"
    agent.provider = "test-provider"
    agent.base_url = "https://test"
    agent.session_input_tokens = 0
    agent.session_output_tokens = 0
    agent.session_cache_read_tokens = 0
    agent.session_cache_write_tokens = 0
    agent.session_reasoning_tokens = 0
    agent.session_prompt_tokens = 0
    agent.session_completion_tokens = 0
    agent.session_total_tokens = 0
    agent.session_estimated_cost_usd = None
    agent.session_cost_status = None
    agent.session_cost_source = None
    agent.context_compressor = MagicMock()
    agent.context_compressor.last_prompt_tokens = 0
    agent._response_was_previewed = False
    agent._interrupt_message = None
    agent._tool_guardrail_halt_decision = None
    agent._file_mutation_verifier_enabled.return_value = False
    agent._turn_completion_explainer_enabled.return_value = False
    agent._skill_nudge_interval = 0
    agent._iters_since_skill = 0
    agent.valid_tool_names = []
    agent._drain_pending_steer.return_value = None
    agent.clear_interrupt.return_value = None
    agent._stream_callback = None
    agent._turn_failed_file_mutations = None
    agent._active_children = []
    agent._sync_external_memory_for_turn.return_value = None
    agent._spawn_background_review.return_value = None
    return agent


def test_finalize_turn_survives_persist_session_failure(caplog: pytest.LogCaptureFixture) -> None:
    """finalize_turn must return a result dict even when _persist_session raises."""
    agent = _base_agent()
    agent._drop_trailing_empty_response_scaffolding.return_value = None
    agent._persist_session.side_effect = OSError("disk full")

    with caplog.at_level(logging.WARNING, logger="agent.conversation_loop"):
        result = finalize_turn(
            agent,
            final_response="done",
            api_call_count=0,
            interrupted=False,
            failed=False,
            messages=[],
            conversation_history=[],
            effective_task_id="task-1",
            turn_id="turn-1",
            user_message="hi",
            original_user_message="hi",
            _should_review_memory=False,
            _turn_exit_reason="completed",
        )

    assert isinstance(result, dict)
    assert result["final_response"] == "done"
    agent._persist_session.assert_called_once()
    assert "turn finalization persist failed" in caplog.text
    assert "disk full" in caplog.text
