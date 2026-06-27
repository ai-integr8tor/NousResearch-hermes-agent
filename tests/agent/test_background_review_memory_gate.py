"""The background review must not use the built-in ``memory`` tool when its store
is disabled (e.g. a memory provider has replaced it).

Regression for: the post-turn review fork is prompted to "save it using the memory
tool" and whitelists ``enabled_toolsets=["memory", "skills"]`` unconditionally, so
when the built-in store is off (``agent._memory_store is None``) every memory-arm
call fails with "Memory is not available". The review should run skill-only in that
case. See ``agent.background_review._builtin_memory_available``.
"""
from types import SimpleNamespace

from agent.background_review import (
    _builtin_memory_available,
    spawn_background_review_thread,
    _MEMORY_REVIEW_PROMPT,
    _SKILL_REVIEW_PROMPT,
)


def _agent(memory_enabled, store):
    return SimpleNamespace(_memory_enabled=memory_enabled, _memory_store=store)


def test_available_requires_both_enabled_and_a_store():
    assert _builtin_memory_available(_agent(True, object())) is True
    assert _builtin_memory_available(_agent(False, object())) is False
    assert _builtin_memory_available(_agent(True, None)) is False
    assert _builtin_memory_available(_agent(False, None)) is False


def test_available_defaults_false_when_attrs_missing():
    # An agent that never set the memory attrs must not be treated as available.
    assert _builtin_memory_available(SimpleNamespace()) is False


def test_memory_only_trigger_is_skipped_when_store_disabled():
    target, prompt = spawn_background_review_thread(
        _agent(False, None), [], review_memory=True, review_skills=False
    )
    assert prompt == ""          # nothing for the memory arm to do
    assert target() is None      # no-op fork target


def test_combined_trigger_degrades_to_skill_only_when_store_disabled():
    _, prompt = spawn_background_review_thread(
        _agent(False, None), [], review_memory=True, review_skills=True
    )
    assert prompt == _SKILL_REVIEW_PROMPT


def test_memory_review_unchanged_when_store_available():
    _, prompt = spawn_background_review_thread(
        _agent(True, object()), [], review_memory=True, review_skills=False
    )
    assert prompt == _MEMORY_REVIEW_PROMPT


def test_skill_review_unaffected_by_memory_state():
    for ag in (_agent(False, None), _agent(True, object())):
        _, prompt = spawn_background_review_thread(
            ag, [], review_memory=False, review_skills=True
        )
        assert prompt == _SKILL_REVIEW_PROMPT
