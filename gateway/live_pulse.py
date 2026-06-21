"""Non-secret Hermes gateway live pulse for Mission Control / Agent Floor.

This module exports metadata only: counts, redacted session identity, state,
elapsed time, model/provider labels, and process counts. It never writes chat
content, user prompts, tool output, command text, logs, credentials, raw
session keys, or approval payloads.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from hermes_cli.config import get_hermes_home
except Exception:  # pragma: no cover - defensive fallback for isolated imports
    def get_hermes_home() -> Path:  # type: ignore[no-redef]
        return Path.home() / ".hermes"


PULSE_PATH = get_hermes_home() / "tools" / "agent_floor" / "hermes_live_pulse.json"
HEARTBEAT_INTERVAL_SECONDS = 30
INTERRUPTION_SIGNALS = {
    "safe_to_message",
    "caution_active_workflow",
    "do_not_interrupt",
    "unknown",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_session_key(session_key: str) -> str:
    if not session_key:
        return ""
    return hashlib.sha256(session_key.encode("utf-8", errors="replace")).hexdigest()[:16]


def _safe_str(value: Any, max_len: int = 96) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def _agent_activity(agent: Any) -> dict[str, Any]:
    if not agent or not hasattr(agent, "get_activity_summary"):
        return {}
    try:
        activity = agent.get_activity_summary() or {}
    except Exception:
        return {}
    current_tool = activity.get("current_tool")
    current_phase = activity.get("last_activity_desc") or current_tool or "running"
    return {
        "current_phase": _safe_str(current_phase),
        "current_tool": _safe_str(current_tool, 64) if current_tool else None,
        "api_call_count": activity.get("api_call_count"),
        "max_iterations": activity.get("max_iterations"),
        "seconds_since_activity": activity.get("seconds_since_activity"),
    }


def _pending_approval_counts(pending_approvals: Mapping[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not pending_approvals:
        return counts
    for session_key, approval in pending_approvals.items():
        if not session_key:
            continue
        if isinstance(approval, (list, tuple, set)):
            counts[str(session_key)] = len(approval)
        elif isinstance(approval, Mapping) and approval.get("items") and isinstance(approval.get("items"), list):
            counts[str(session_key)] = len(approval.get("items") or [])
        else:
            counts[str(session_key)] = 1
    return counts


def classify_background_process(proc: Mapping[str, Any]) -> tuple[str, bool, str]:
    """Classify process-registry rows without exposing command text.

    Only session-linked or non-default task-linked running processes are treated
    as interrupt-sensitive. Unscoped long-lived helpers stay visible but do not
    pin Agent Floor to caution forever.
    """
    has_session_key = bool(proc.get("has_session_key"))
    task_id = _safe_str(proc.get("task_id"), 64) if proc.get("task_id") else ""
    has_meaningful_task_id = bool(task_id and task_id != "default")
    detached = bool(proc.get("detached"))
    uptime = int(proc.get("uptime_seconds") or 0)

    if detached:
        return "detached_or_recovered_process", False, "detached recovered process; visible warning only"
    if not has_meaningful_task_id and uptime >= 300:
        return "default_long_lived_helper", False, "default/unscoped helper older than five minutes; not interrupt-sensitive"
    if has_session_key or has_meaningful_task_id:
        return "active_background_work", True, "linked to an active Hermes session or non-default task"
    return "unscoped_recent_background_process", False, "unscoped recent process; visible warning only"


def _process_rows() -> list[dict[str, Any]]:
    try:
        from tools.process_registry import process_registry

        rows: list[dict[str, Any]] = []
        for proc in process_registry.list_sessions():
            if proc.get("status") != "running":
                continue
            classification, interrupt_sensitive, reason = classify_background_process(proc)
            task_id = _safe_str(proc.get("task_id"), 64) if proc.get("task_id") else None
            rows.append(
                {
                    "process_id": _safe_str(proc.get("session_id"), 48),
                    "state": "background_running",
                    "classification": classification,
                    "interrupt_sensitive": interrupt_sensitive,
                    "classification_reason": reason,
                    "elapsed_seconds": int(proc.get("uptime_seconds") or 0),
                    "session_linked": bool(proc.get("has_session_key")),
                    "task_id": task_id,
                    "pid_scope": _safe_str(proc.get("pid_scope"), 24) if proc.get("pid_scope") else None,
                    "detached": bool(proc.get("detached")),
                }
            )
        return rows
    except Exception:
        return []


def build_live_pulse(
    *,
    running_agents: Mapping[str, Any] | None = None,
    running_started: Mapping[str, float] | None = None,
    pending_sentinel: Any = None,
    background_tasks: set[Any] | None = None,
    pending_approvals: Mapping[str, Any] | None = None,
    session_platform_resolver: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    now = time.time()
    running_agents = running_agents or {}
    running_started = running_started or {}
    approval_counts = _pending_approval_counts(pending_approvals)
    pending_approval_total = sum(int(v or 0) for v in approval_counts.values())

    sessions: list[dict[str, Any]] = []
    active_agent_turns = 0
    starting_turns = 0

    for session_key, agent in running_agents.items():
        session_key = str(session_key)
        started = float(running_started.get(session_key, now) or now)
        is_starting = agent is pending_sentinel
        pending_count = int(approval_counts.get(session_key, 0) or 0)
        if is_starting:
            starting_turns += 1
            state = "starting"
            risk = "caution_active_workflow"
        elif pending_count:
            active_agent_turns += 1
            state = "waiting_human_approval"
            risk = "safe_to_message"
        else:
            active_agent_turns += 1
            state = "running"
            risk = "caution_active_workflow"

        platform = "unknown"
        if session_platform_resolver:
            try:
                platform = _safe_str(session_platform_resolver(session_key), 32) or "unknown"
            except Exception:
                platform = "unknown"

        row = {
            "session_key_hash": _hash_session_key(session_key),
            "session_id": "" if is_starting else _safe_str(getattr(agent, "session_id", ""), 64),
            "platform": platform,
            "state": state,
            "elapsed_seconds": max(0, int(now - started)),
            "model": "" if is_starting else _safe_str(getattr(agent, "model", ""), 96),
            "provider": "" if is_starting else _safe_str(getattr(agent, "provider", ""), 64),
            "current_phase": "starting" if is_starting else "running",
            "current_tool": None,
            "pending_approval_count": pending_count,
            "interruption_risk": risk,
        }
        if not is_starting:
            row.update(_agent_activity(agent))
        sessions.append(row)

    running_processes = _process_rows()
    interrupt_sensitive_process_count = len([p for p in running_processes if p.get("interrupt_sensitive")])
    helper_process_count = len(running_processes) - interrupt_sensitive_process_count
    async_job_count = len([t for t in (background_tasks or set()) if hasattr(t, "done") and not t.done()])

    if any(row.get("interruption_risk") == "do_not_interrupt" for row in sessions):
        signal = "do_not_interrupt"
        reason = "A live Hermes session reports do-not-interrupt risk."
    elif active_agent_turns or starting_turns or interrupt_sensitive_process_count or async_job_count:
        signal = "caution_active_workflow"
        reason = "Hermes gateway reports active turn/startup/background activity."
    elif pending_approval_total:
        signal = "safe_to_message"
        reason = "Hermes is waiting on human approval; messaging is unlikely to interrupt active execution."
    elif helper_process_count:
        signal = "safe_to_message"
        reason = "Fresh gateway pulse shows no active turns or interrupt-sensitive background work; non-interrupting background helper present."
    else:
        signal = "safe_to_message"
        reason = "Fresh gateway pulse shows no active turns, approvals, async jobs, or background processes."

    return {
        "schema_version": "hermes-live-pulse-v1",
        "generated_at": _now_iso(),
        "profile": os.getenv("HERMES_PROFILE") or "jimmy",
        "gateway": {"running": True, "pid": os.getpid()},
        "summary": {
            "active_agent_turns": active_agent_turns,
            "starting_turns": starting_turns,
            "pending_approval_count": pending_approval_total,
            "running_background_process_count": interrupt_sensitive_process_count,
            "background_process_total_count": len(running_processes),
            "background_helper_process_count": helper_process_count,
            "async_job_count": async_job_count,
            "interruption_signal": signal,
            "interruption_reason": reason,
        },
        "sessions": sessions,
        "running_background_processes": running_processes,
        "source_limits": [
            "No chat content included",
            "No raw user prompt included",
            "No raw tool output included",
            "No sensitive command text included",
            "No approval payload included",
            "No logs, databases, caches, browser profiles, tokens, or credentials inspected",
        ],
    }


def write_live_pulse(**kwargs: Any) -> dict[str, Any]:
    pulse = build_live_pulse(**kwargs)
    PULSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PULSE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pulse, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(PULSE_PATH)
    return pulse
