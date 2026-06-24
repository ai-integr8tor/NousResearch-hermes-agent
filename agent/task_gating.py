"""Task-level capability gating for degraded/local model operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent.model_capabilities import ModelCapability, resolve_model_capability


_DEFAULT_TASK_POLICY = {
    "score_key": "general",
    "min_score": 0.40,
    "local_allowed": True,
    "on_insufficient": "defer",
}


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    action: str
    reason: str
    task_type: str
    score_key: str
    score: float
    minimum: float
    capability: ModelCapability


def _policy_enabled(config: Mapping[str, Any]) -> bool:
    policy = config.get("capability_policy") if isinstance(config, Mapping) else None
    if not isinstance(policy, Mapping):
        return False
    return bool(policy.get("enabled", False))


def _task_policy(config: Mapping[str, Any], task_type: str) -> dict[str, Any]:
    policy = config.get("capability_policy") if isinstance(config, Mapping) else None
    if not isinstance(policy, Mapping):
        return dict(_DEFAULT_TASK_POLICY)
    merged = dict(_DEFAULT_TASK_POLICY)
    if policy.get("default_min_score") is not None:
        merged["min_score"] = policy.get("default_min_score")
    tasks = policy.get("tasks")
    if isinstance(tasks, Mapping):
        task_cfg = tasks.get(task_type) or tasks.get("default")
        if isinstance(task_cfg, Mapping):
            merged.update(dict(task_cfg))
    return merged


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _looks_local(provider: str, capability: ModelCapability) -> bool:
    text = " ".join([
        provider or "",
        capability.provider or "",
        capability.degraded_label or "",
    ]).lower()
    return any(marker in text for marker in ("local", "llama", "qwen"))


def evaluate_task_capability(
    *,
    task_type: str,
    provider: str,
    model: str,
    config: Mapping[str, Any] | None = None,
    degraded: bool = False,
) -> CapabilityDecision:
    """Return whether the active model may attempt ``task_type``.

    The gate is inactive unless ``capability_policy.enabled`` is true.  When
    active, it compares the model's configured score against the task's minimum
    and also honors ``local_allowed: false`` during degraded/local operation.
    """

    config = config or {}
    capability = resolve_model_capability(provider=provider, model=model, config=config)
    task_type = task_type or "default"

    if not _policy_enabled(config):
        return CapabilityDecision(
            allowed=True,
            action="allow",
            reason="capability policy disabled",
            task_type=task_type,
            score_key="general",
            score=capability.score("general"),
            minimum=0.0,
            capability=capability,
        )

    policy = _task_policy(config, task_type)
    score_key = str(policy.get("score_key") or "general")
    minimum = _to_float(policy.get("min_score"), 0.40)
    score = capability.score(score_key)
    action = str(policy.get("on_insufficient") or "defer")
    local_allowed = bool(policy.get("local_allowed", True))
    is_local_degraded = bool(degraded and _looks_local(provider, capability))

    if is_local_degraded and not local_allowed:
        return CapabilityDecision(
            allowed=False,
            action=action,
            reason=(
                f"Task {task_type} is not allowed on degraded/local model "
                f"{capability.degraded_label}; requires {score_key} score "
                f"{minimum:.2f}, active score is {score:.2f}."
            ),
            task_type=task_type,
            score_key=score_key,
            score=score,
            minimum=minimum,
            capability=capability,
        )

    if score < minimum:
        return CapabilityDecision(
            allowed=False,
            action=action,
            reason=(
                f"Task {task_type} requires {score_key} score {minimum:.2f}; "
                f"active model {capability.degraded_label} scores {score:.2f}."
            ),
            task_type=task_type,
            score_key=score_key,
            score=score,
            minimum=minimum,
            capability=capability,
        )

    return CapabilityDecision(
        allowed=True,
        action="allow",
        reason=(
            f"Task {task_type} allowed: {score_key} score {score:.2f} "
            f">= {minimum:.2f}."
        ),
        task_type=task_type,
        score_key=score_key,
        score=score,
        minimum=minimum,
        capability=capability,
    )


def infer_cron_task_type(job: Mapping[str, Any], prompt: str = "") -> str:
    """Conservative heuristic for existing cron jobs without explicit policy."""

    cap_cfg = job.get("capability") if isinstance(job, Mapping) else None
    if isinstance(cap_cfg, Mapping) and cap_cfg.get("task_type"):
        return str(cap_cfg.get("task_type"))

    toolsets = " ".join(str(t).lower() for t in (job.get("enabled_toolsets") or [])) if isinstance(job, Mapping) else ""
    text = f"{job.get('name', '') if isinstance(job, Mapping) else ''} {prompt} {toolsets}".lower()
    if any(word in text for word in ("email", "gmail", "imap", "inbox")):
        return "cron.email_monitor"
    if any(word in text for word in ("commit", "pull request", " pr ", "code", "patch", "deploy", "build")):
        return "cron.code_modification"
    return "cron.default"
