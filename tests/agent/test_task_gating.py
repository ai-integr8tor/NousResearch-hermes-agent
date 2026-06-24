from agent.task_gating import CapabilityDecision, evaluate_task_capability


def test_evaluate_task_capability_allows_local_task_above_threshold():
    cfg = {
        "capability_policy": {
            "enabled": True,
            "tasks": {
                "cron.email_monitor": {
                    "score_key": "autonomous_ops",
                    "min_score": 0.40,
                    "local_allowed": True,
                }
            },
        },
        "providers": {
            "local-llm": {
                "models": {
                    "qwen3.6-27b-q4km": {
                        "scores": {"autonomous_ops": 0.45},
                        "degraded_label": "local-qwen",
                    }
                }
            }
        },
    }

    decision = evaluate_task_capability(
        task_type="cron.email_monitor",
        provider="local-llm",
        model="qwen3.6-27b-q4km",
        config=cfg,
        degraded=True,
    )

    assert isinstance(decision, CapabilityDecision)
    assert decision.allowed is True
    assert decision.score == 0.45
    assert decision.minimum == 0.40
    assert decision.action == "allow"


def test_evaluate_task_capability_defers_local_task_below_threshold():
    cfg = {
        "capability_policy": {
            "enabled": True,
            "tasks": {
                "cron.code_modification": {
                    "score_key": "coding",
                    "min_score": 0.70,
                    "local_allowed": False,
                    "on_insufficient": "notify",
                }
            },
        },
        "providers": {
            "local-llm": {
                "models": {
                    "qwen3.6-27b-q4km": {
                        "scores": {"coding": 0.45},
                        "degraded_label": "local-qwen",
                    }
                }
            }
        },
    }

    decision = evaluate_task_capability(
        task_type="cron.code_modification",
        provider="local-llm",
        model="qwen3.6-27b-q4km",
        config=cfg,
        degraded=True,
    )

    assert decision.allowed is False
    assert decision.score == 0.45
    assert decision.minimum == 0.70
    assert decision.action == "notify"
    assert "requires coding score 0.70" in decision.reason
    assert "local-qwen" in decision.reason


def test_evaluate_task_capability_bypasses_when_policy_disabled():
    decision = evaluate_task_capability(
        task_type="cron.code_modification",
        provider="local-llm",
        model="qwen3.6-27b-q4km",
        config={"capability_policy": {"enabled": False}},
        degraded=True,
    )

    assert decision.allowed is True
    assert decision.action == "allow"
