"""Best-effort degraded-mode notifications.

This module deliberately has no dependency on gateway internals.  It uses the
same send_message tool path humans use, so a bare ``telegram`` target resolves
to the configured home channel when Telegram is available.  Failures are logged
and never block fallback activation.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_LAST_SENT: dict[str, float] = {}
_DEFAULT_COOLDOWN_SECONDS = 15 * 60


def _notify_enabled() -> bool:
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        policy = cfg.get("capability_policy") if isinstance(cfg, dict) else None
        if isinstance(policy, dict) and policy.get("notify_on_degraded_mode") is False:
            return False
    except Exception:
        pass
    return True


def notify_degraded_mode(
    *,
    kind: str,
    message: str,
    target: str = "telegram",
    cooldown_seconds: int = _DEFAULT_COOLDOWN_SECONDS,
    key: str | None = None,
) -> bool:
    """Send a rate-limited degraded-mode notice.

    Returns True only when a send was attempted successfully according to the
    tool response.  False means disabled, rate-limited, or unavailable.
    """

    if not message.strip() or not _notify_enabled():
        return False

    now = time.monotonic()
    dedupe_key = key or f"{kind}:{target}:{message[:160]}"
    last_sent = _LAST_SENT.get(dedupe_key, 0.0)
    if cooldown_seconds > 0 and now - last_sent < cooldown_seconds:
        return False

    try:
        from tools.send_message_tool import send_message_tool
        raw = send_message_tool({"action": "send", "target": target, "message": message})
        parsed: dict[str, Any] = {}
        if isinstance(raw, str) and raw.strip():
            try:
                maybe = json.loads(raw)
                if isinstance(maybe, dict):
                    parsed = maybe
            except json.JSONDecodeError:
                parsed = {}
        if parsed.get("error"):
            logger.warning("Degraded-mode notification failed: %s", parsed.get("error"))
            return False
        _LAST_SENT[dedupe_key] = now
        return True
    except Exception as exc:
        logger.warning("Degraded-mode notification failed: %s", exc)
        return False


def format_fallback_message(
    *,
    old_model: str,
    new_model: str,
    provider: str,
    reason: Any = None,
) -> str:
    reason_text = getattr(reason, "value", None) or str(reason or "provider failure")
    return (
        "Bruno fallback: primary provider failed "
        f"({reason_text}); switched from {old_model or 'primary model'} "
        f"to {new_model} via {provider}. I can keep debugging locally, "
        "but will defer tasks that exceed the active model capability policy."
    )
