from types import SimpleNamespace

from agent.agent_init import (
    _merge_custom_provider_extra_body,
    _merge_request_overrides,
    _model_request_overrides_for_agent,
)


def test_custom_provider_extra_body_merges_into_request_overrides():
    agent = SimpleNamespace(
        provider="custom",
        model="google/gemma-4-31b-it",
        base_url="https://example.test/v1",
        request_overrides={"service_tier": "priority"},
    )

    _merge_custom_provider_extra_body(
        agent,
        [
            {
                "name": "gemma",
                "base_url": "https://example.test/v1/",
                "model": "google/gemma-4-31b-it",
                "extra_body": {
                    "enable_thinking": True,
                    "reasoning_effort": "high",
                },
            }
        ],
    )

    assert agent.request_overrides == {
        "service_tier": "priority",
        "extra_body": {
            "enable_thinking": True,
            "reasoning_effort": "high",
        },
    }


def test_custom_provider_extra_body_preserves_caller_override():
    agent = SimpleNamespace(
        provider="custom",
        model="google/gemma-4-31b-it",
        base_url="https://example.test/v1",
        request_overrides={
            "extra_body": {
                "reasoning_effort": "low",
                "caller_only": True,
            }
        },
    )

    _merge_custom_provider_extra_body(
        agent,
        [
            {
                "name": "gemma",
                "base_url": "https://example.test/v1",
                "model": "google/gemma-4-31b-it",
                "extra_body": {
                    "enable_thinking": True,
                    "reasoning_effort": "high",
                },
            }
        ],
    )

    assert agent.request_overrides["extra_body"] == {
        "enable_thinking": True,
        "reasoning_effort": "low",
        "caller_only": True,
    }


def test_custom_provider_extra_body_ignores_other_custom_models():
    agent = SimpleNamespace(
        provider="custom",
        model="other-model",
        base_url="https://example.test/v1",
        request_overrides={},
    )

    _merge_custom_provider_extra_body(
        agent,
        [
            {
                "name": "gemma",
                "base_url": "https://example.test/v1",
                "model": "google/gemma-4-31b-it",
                "extra_body": {"enable_thinking": True},
            }
        ],
    )

    assert agent.request_overrides == {}


def test_model_request_overrides_reads_model_config(monkeypatch):
    def fake_load_config():
        return {
            "model": {
                "request_overrides": {
                    "extra_body": {"text": {"verbosity": "low"}}
                }
            }
        }

    monkeypatch.setattr("hermes_cli.config.load_config", fake_load_config)

    assert _model_request_overrides_for_agent() == {
        "extra_body": {"text": {"verbosity": "low"}}
    }


def test_model_request_overrides_ignores_non_mapping_config(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"model": {"request_overrides": "low"}},
    )

    assert _model_request_overrides_for_agent() == {}


def test_merge_request_overrides_preserves_explicit_turn_override():
    agent = SimpleNamespace(
        request_overrides={
            "service_tier": "priority",
            "extra_body": {
                "text": {"verbosity": "medium"},
                "caller_only": True,
            },
        }
    )

    _merge_request_overrides(
        agent,
        {
            "service_tier": "default",
            "extra_body": {
                "text": {"verbosity": "low"},
                "provider_default": True,
            },
        },
    )

    assert agent.request_overrides == {
        "service_tier": "priority",
        "extra_body": {
            "text": {"verbosity": "medium"},
            "provider_default": True,
            "caller_only": True,
        },
    }
