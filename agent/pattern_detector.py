"""Lightweight per-turn tool-call pattern detection.

Catches redundant successful tool loops that the failure-only
ToolCallGuardrailController does not cover (e.g. the model calling the
same tool with the same args 5 times in a row, each one succeeding).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional


class ToolPatternDetector:
    """Per-turn accumulator for tool-call signatures.

    Tracks consecutive identical (tool_name, canonical-args) pairs and
    total tool-call volume.  When a threshold is exceeded the detector
    returns a human-readable warning the agent loop can surface.
    """

    def __init__(self) -> None:
        self._last_sig: Optional[tuple] = None
        self._consecutive: int = 0
        self._total: int = 0
        # Constants
        self.CONSECUTIVE_WARN = 4   # warn when same call repeats this many times
        self.VOLUME_WARN = 25       # warn when any turn exceeds this many calls

    # -- public API -------------------------------------------------------

    def record(self, tool_name: str, tool_args: dict) -> Optional[str]:
        """Record a completed tool call.  Returns a warning string or None."""
        sig = self._canonical_sig(tool_name, tool_args)

        self._total += 1

        if self._last_sig == sig:
            self._consecutive += 1
        else:
            self._consecutive = 1
        self._last_sig = sig

        if self._consecutive == self.CONSECUTIVE_WARN:
            return (
                f"{tool_name} called {self._consecutive} times consecutively "
                f"with identical args — possible redundant loop"
            )
        if self._total == self.VOLUME_WARN:
            return (
                f"High tool volume: {self._total} tool calls this turn — "
                f"consider whether the task can complete more directly"
            )
        return None

    def reset_for_turn(self) -> None:
        """Clear all per-turn state (call at turn boundary)."""
        self._last_sig = None
        self._consecutive = 0
        self._total = 0

    # -- internal ---------------------------------------------------------

    @staticmethod
    def _canonical_sig(tool_name: str, tool_args: dict) -> tuple:
        """Hash tool args so small formatting differences do not mask identity."""
        raw = json.dumps(tool_args, sort_keys=True, ensure_ascii=False)
        return (tool_name, hashlib.sha256(raw.encode()).hexdigest()[:16])
