"""Helpers for durable deferred gateway clarify turns."""

from __future__ import annotations

import json
from typing import Optional

DEFERRED_CLARIFY_KIND = "hermes.deferred_clarify.v1"


def make_deferred_marker(interaction_id: str) -> str:
    """Return a provider-valid tool result that asks the loop to suspend."""
    return json.dumps(
        {
            "status": "deferred",
            "kind": DEFERRED_CLARIFY_KIND,
            "interaction_id": str(interaction_id),
            "message": "Clarify prompt sent to user; current turn is suspended.",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_deferred_marker(content: object) -> Optional[str]:
    """Extract a deferred clarify interaction id from a tool result string."""
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("status") != "deferred" or payload.get("kind") != DEFERRED_CLARIFY_KIND:
        return None
    interaction_id = payload.get("interaction_id")
    if not isinstance(interaction_id, str) or not interaction_id:
        return None
    return interaction_id


def is_deferred_clarify_result(content: object) -> bool:
    return parse_deferred_marker(content) is not None


def build_recovery_prompt(*, question: str, answer: str) -> str:
    """Build the synthetic user turn that resumes a deferred clarify."""
    return (
        "The user answered a clarify prompt from the previous Hermes turn.\n\n"
        "Previous question:\n"
        f"{question}\n\n"
        "User answer:\n"
        f"{answer}\n\n"
        "Continue the previous task using this answer. Do not ask the same "
        "clarification again unless the answer is still ambiguous."
    )


__all__ = [
    "DEFERRED_CLARIFY_KIND",
    "make_deferred_marker",
    "parse_deferred_marker",
    "is_deferred_clarify_result",
    "build_recovery_prompt",
]
