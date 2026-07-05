from types import SimpleNamespace

from agent.conversation_compression import (
    compress_context,
    conversation_history_after_compression,
)


class _AbortCompressor:
    _last_compress_aborted = False
    _last_summary_error = "summary provider timeout"
    compression_count = 1

    def compress(self, messages, **_kwargs):
        self._last_compress_aborted = True
        return messages


class _SuccessCompressor:
    _last_compress_aborted = False
    _last_summary_error = None
    compression_count = 1
    last_compression_rough_tokens = 0
    last_prompt_tokens = 0
    last_completion_tokens = 0
    awaiting_real_usage_after_compression = False

    def compress(self, _messages, **_kwargs):
        return [{"role": "user", "content": "[summary]"}]


class _FakeSessionDB:
    def try_acquire_compression_lock(self, *_args, **_kwargs):
        return True

    def release_compression_lock(self, *_args, **_kwargs):
        pass

    def archive_and_compact(self, _session_id, _messages):
        pass

    def update_system_prompt(self, _session_id, _system_prompt):
        pass


def _make_agent(compressor):
    warnings = []
    return SimpleNamespace(
        _last_compaction_in_place=False,
        _last_compression_attempt_in_place=False,
        _compression_feasibility_checked=True,
        compression_in_place=True,
        context_compressor=compressor,
        session_id="sess-1",
        model="test-model",
        tools=None,
        platform=None,
        _gateway_session_key=None,
        log_prefix="",
        _session_db=_FakeSessionDB(),
        _memory_manager=None,
        _todo_store=SimpleNamespace(format_for_injection=lambda: ""),
        _cached_system_prompt="cached-system",
        _last_compression_summary_warning=None,
        _build_system_prompt=lambda system_message: f"system:{system_message}",
        _invalidate_system_prompt=lambda: None,
        commit_memory_session=lambda _messages: None,
        _emit_status=lambda _message: None,
        _emit_warning=warnings.append,
    )


def test_aborted_compression_uses_per_attempt_flag_without_clearing_run_signal():
    messages = [{"role": "user", "content": "keep this"}]

    agent = _make_agent(_SuccessCompressor())

    compressed, _system_prompt = compress_context(agent, messages, "system")
    assert agent._last_compression_attempt_recorded is True
    assert agent._last_compaction_in_place is True
    assert agent._last_compression_attempt_in_place is True
    assert conversation_history_after_compression(agent, compressed) == compressed

    agent.context_compressor = _AbortCompressor()
    returned, system_prompt = compress_context(agent, messages, "system")

    assert returned is messages
    assert system_prompt == "system:system"
    assert agent._last_compression_attempt_recorded is True
    assert agent._last_compaction_in_place is True
    assert agent._last_compression_attempt_in_place is False
    assert conversation_history_after_compression(agent, returned) is None


def test_run_conversation_resets_run_level_in_place_signal(monkeypatch):
    import agent.conversation_loop as loop

    observed = {}

    def fake_build_turn_context(agent, *_args, **_kwargs):
        observed["run_flag"] = agent._last_compaction_in_place
        observed["attempt_recorded"] = agent._last_compression_attempt_recorded
        return SimpleNamespace(
            user_message="hello",
            original_user_message="hello",
            messages=[],
            conversation_history=[],
            active_system_prompt="system",
            effective_task_id="default",
            turn_id="turn-1",
            current_turn_user_idx=0,
            should_review_memory=False,
            plugin_user_context={},
            ext_prefetch_cache=None,
        )

    agent = SimpleNamespace(
        api_mode="codex_app_server",
        _last_compaction_in_place=True,
        _last_compression_attempt_recorded=True,
    )
    agent._run_codex_app_server_turn = lambda **_kwargs: {
        "compacted_in_place": agent._last_compaction_in_place,
        "attempt_recorded": agent._last_compression_attempt_recorded,
    }

    monkeypatch.setattr(loop, "build_turn_context", fake_build_turn_context)

    result = loop.run_conversation(agent, "hello")

    assert observed == {"run_flag": False, "attempt_recorded": False}
    assert result == {"compacted_in_place": False, "attempt_recorded": False}
