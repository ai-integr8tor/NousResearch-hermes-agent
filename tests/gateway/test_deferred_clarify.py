import json


def test_deferred_marker_round_trips_as_provider_valid_tool_result():
    from gateway.extensions.deferred_clarify import (
        DEFERRED_CLARIFY_KIND,
        is_deferred_clarify_result,
        make_deferred_marker,
        parse_deferred_marker,
    )

    marker = make_deferred_marker("cld_123")
    payload = json.loads(marker)

    assert payload["status"] == "deferred"
    assert payload["kind"] == DEFERRED_CLARIFY_KIND
    assert payload["interaction_id"] == "cld_123"
    assert is_deferred_clarify_result(marker) is True
    assert parse_deferred_marker(marker) == "cld_123"


def test_recovery_prompt_includes_question_answer_and_instruction():
    from gateway.extensions.deferred_clarify import build_recovery_prompt

    prompt = build_recovery_prompt(
        question="Deploy where?",
        answer="staging",
    )

    assert "previous Hermes turn" in prompt
    assert "Deploy where?" in prompt
    assert "staging" in prompt
    assert "Do not ask the same clarification again" in prompt


def test_marker_parser_ignores_malformed_or_other_tool_results():
    from gateway.extensions.deferred_clarify import (
        is_deferred_clarify_result,
        parse_deferred_marker,
    )

    assert parse_deferred_marker("not json") is None
    assert parse_deferred_marker('{"status":"ok"}') is None
    assert is_deferred_clarify_result('{"status":"ok"}') is False
