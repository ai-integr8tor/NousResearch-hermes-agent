from types import SimpleNamespace

from agent.auxiliary_client import call_llm
from run_agent import AIAgent


def test_platform_request_overrides_layer_below_explicit_overrides(
    monkeypatch, tmp_path
):
    cfg = {
        "platform_request_overrides": {
            "api_server": {
                "reasoning_effort": "minimal",
                "service_tier": "priority",
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False},
                    "shared": "platform",
                },
            },
        },
    }
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr("run_agent._hermes_home", hermes_home)
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: cfg)

    agent = AIAgent(
        base_url="http://localhost:1234/v1",
        api_key="test-key",
        provider="custom",
        model="test-model",
        platform="api_server",
        reasoning_config={"enabled": True, "effort": "high"},
        request_overrides={
            "reasoning_effort": "low",
            "extra_body": {"shared": "caller", "caller_only": True},
        },
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
    )

    assert agent.reasoning_config == {"enabled": True, "effort": "low"}
    assert agent.service_tier == "priority"
    assert agent.request_overrides == {
        "service_tier": "priority",
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
            "shared": "caller",
            "caller_only": True,
        },
    }


def test_auxiliary_task_request_options_reach_llm_kwargs(monkeypatch):
    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="ok")),
                ],
            )

    fake_client = SimpleNamespace(
        base_url="https://llm.example/v1",
        chat=SimpleNamespace(completions=_Completions()),
    )

    monkeypatch.setattr(
        "agent.auxiliary_client._resolve_task_provider_model",
        lambda *args, **kwargs: ("custom", "aux-model", None, None, None),
    )
    monkeypatch.setattr(
        "agent.auxiliary_client._get_cached_client",
        lambda *args, **kwargs: (fake_client, "aux-model"),
    )
    monkeypatch.setattr(
        "agent.auxiliary_client._get_auxiliary_task_config",
        lambda task: {
            "reasoning_effort": "none",
            "service_tier": "priority",
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False},
                "shared": "task",
            },
        },
    )

    result = call_llm(
        task="compression",
        messages=[{"role": "user", "content": "summarize"}],
        extra_body={"shared": "call", "call_only": True},
    )

    assert result.choices[0].message.content == "ok"
    assert captured["service_tier"] == "priority"
    assert captured["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False},
        "shared": "call",
        "call_only": True,
        "reasoning": {"enabled": False},
    }
