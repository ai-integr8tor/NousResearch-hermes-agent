"""Rate limit tracking for inference API responses.

Captures x-ratelimit-* headers from provider responses and provides
formatted display for the /usage slash command.  Currently supports
the Nous Portal header format (also used by OpenRouter and OpenAI-compatible
APIs that follow the same convention).

Header schema (12 headers total):
    x-ratelimit-limit-requests          RPM cap
    x-ratelimit-limit-requests-1h       RPH cap
    x-ratelimit-limit-tokens            TPM cap
    x-ratelimit-limit-tokens-1h         TPH cap
    x-ratelimit-remaining-requests      requests left in minute window
    x-ratelimit-remaining-requests-1h   requests left in hour window
    x-ratelimit-remaining-tokens        tokens left in minute window
    x-ratelimit-remaining-tokens-1h     tokens left in hour window
    x-ratelimit-reset-requests          seconds until minute request window resets
    x-ratelimit-reset-requests-1h       seconds until hour request window resets
    x-ratelimit-reset-tokens            seconds until minute token window resets
    x-ratelimit-reset-tokens-1h         seconds until hour token window resets
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class RateLimitBucket:
    """One rate-limit window (e.g. requests per minute)."""

    limit: int = 0
    remaining: int = 0
    reset_seconds: float = 0.0
    captured_at: float = 0.0  # time.time() when this was captured

    @property
    def used(self) -> int:
        return max(0, self.limit - self.remaining)

    @property
    def usage_pct(self) -> float:
        if self.limit <= 0:
            return 0.0
        return (self.used / self.limit) * 100.0

    @property
    def remaining_seconds_now(self) -> float:
        """Estimated seconds remaining until reset, adjusted for elapsed time."""
        elapsed = time.time() - self.captured_at
        return max(0.0, self.reset_seconds - elapsed)


@dataclass
class RateLimitState:
    """Full rate-limit state parsed from response headers."""

    requests_min: RateLimitBucket = field(default_factory=RateLimitBucket)
    requests_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_min: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    captured_at: float = 0.0  # when the headers were captured
    provider: str = ""

    @property
    def has_data(self) -> bool:
        return self.captured_at > 0

    @property
    def age_seconds(self) -> float:
        if not self.has_data:
            return float("inf")
        return time.time() - self.captured_at


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_rate_limit_headers(
    headers: Mapping[str, str],
    provider: str = "",
    status_code: int = 0,
    error_body: str = "",
) -> Optional[RateLimitState]:
    """Parse x-ratelimit-* headers into a RateLimitState.

    Returns None if no rate limit headers are present.
    Supports multiple provider header formats:
      - OpenAI/Groq:      x-ratelimit-limit-requests, -remaining-requests, -reset-requests
      - OpenAI hourly:    x-ratelimit-limit-requests-1h, -remaining-requests-1h
      - Cerebras:         x-ratelimit-limit-requests-minute, -remaining-requests-minute, etc.
      - Mistral:          x-ratelimit-limit-req-minute, -remaining-req-minute, -limit-tokens-minute
      - SambaNova:        x-ratelimit-limit-requests-day, -remaining-requests-day
      - Anthropic:        retry-after, x-ratelimit-* (via anthropic-ratelimit-* variant)
    """
    # Normalize to lowercase so lookups work regardless of how the server
    # capitalises headers (HTTP header names are case-insensitive per RFC 7230).
    lowered = {k.lower(): v for k, v in headers.items()}

    # Quick check: at least one rate limit header must exist
    has_any = any(k.startswith("x-ratelimit-") for k in lowered) or \
              any(k.startswith("anthropic-ratelimit-") for k in lowered) or \
              "retry-after" in lowered
    if not has_any:
        return None

    now = time.time()

    # Build a flat lookup that normalizes different provider suffixes.
    # We want to find limit/remaining/reset for these window tags:
    #   requests (per-minute),  requests-1h (per-hour)
    #   tokens   (per-minute),  tokens-1h   (per-hour)
    # Each provider spells the suffix differently:
    #   Groq/OpenAI: no suffix for minute, -1h for hour
    #   Cerebras:    -minute / -hour / -day
    #   Mistral:     -minute (and uses "req" instead of "requests")
    #   SambaNova:   -day
    #
    # Strategy: for each (resource, window) pair, try a list of known
    # header name variants and take the first match.

    def _find_raw(prefix: str, resource: str, window_suffixes: list[str]) -> str:
        """Search for a header value trying multiple naming conventions.

        prefix: "limit", "remaining", or "reset"
        resource: "requests" or "tokens"
        window_suffixes: list of suffix variants, e.g. ["", "-minute", "-day"]
        Returns the raw header value as string, or "" if not found.

        Supports both orderings:
          OpenAI/Groq:  x-ratelimit-{prefix}-{resource}{suffix}
                        e.g. x-ratelimit-limit-requests
          Anthropic:    anthropic-ratelimit-{resource}{suffix}-{prefix}
                        e.g. anthropic-ratelimit-requests-limit
        """
        # Different providers use "req" vs "requests"
        resource_variants = [resource]
        if resource == "requests":
            resource_variants.append("req")

        for wsuf in window_suffixes:
            for res in resource_variants:
                # OpenAI/Groq/Cerebras/Mistral/SambaNova: prefix-resource
                key = f"x-ratelimit-{prefix}-{res}{wsuf}"
                if key in lowered:
                    return lowered[key]
                # Anthropic: resource-prefix (inverted)
                key2 = f"anthropic-ratelimit-{res}{wsuf}-{prefix}"
                if key2 in lowered:
                    return lowered[key2]
        return ""

    def _find_int(prefix: str, resource: str, suffixes: list[str]) -> int:
        return _safe_int(_find_raw(prefix, resource, suffixes))

    def _find_float(prefix: str, resource: str, suffixes: list[str]) -> float:
        return _safe_float(_find_raw(prefix, resource, suffixes))

    # Window suffixes in priority order (minute first, then day, then bare)
    MINUTE_SUFFIXES = ["", "-minute", "-1m"]
    HOUR_SUFFIXES = ["-1h", "-hour"]
    DAY_SUFFIXES = ["-day", "-1d"]

    def _bucket(resource: str, suffixes: list[str]) -> RateLimitBucket:
        return RateLimitBucket(
            limit=_find_int("limit", resource, suffixes),
            remaining=_find_int("remaining", resource, suffixes),
            reset_seconds=_find_float("reset", resource, suffixes),
            captured_at=now,
        )

    # Some providers (Anthropic) use reset with duration strings like "15s"
    def _parse_duration(val: str) -> float:
        if not val:
            return 0.0
        val = val.strip()
        if val.isdigit():
            return float(val)
        # "15s", "2m", "1h"
        try:
            import re
            m = re.match(r'^(\d+(?:\.\d+)?)([smh])?$', val)
            if m:
                num = float(m.group(1))
                unit = m.group(2) or 's'
                mult = {'s': 1, 'm': 60, 'h': 3600}[unit]
                return num * mult
        except Exception:
            pass
        return 0.0

    state = RateLimitState(
        requests_min=_bucket("requests", MINUTE_SUFFIXES),
        requests_hour=_bucket("requests", HOUR_SUFFIXES),
        tokens_min=_bucket("tokens", MINUTE_SUFFIXES),
        tokens_hour=_bucket("tokens", HOUR_SUFFIXES),
        captured_at=now,
        provider=provider,
    )

    # If minute data is empty but day data exists (SambaNova),
    # put day data into the minute slot so it's still displayed
    if state.requests_min.limit == 0 and state.requests_hour.limit == 0:
        day_bucket = _bucket("requests", DAY_SUFFIXES)
        if day_bucket.limit > 0:
            state.requests_min = day_bucket

    if state.tokens_min.limit == 0 and state.tokens_hour.limit == 0:
        day_bucket = _bucket("tokens", DAY_SUFFIXES)
        if day_bucket.limit > 0:
            state.tokens_min = day_bucket

    # Anthropic retry-after as fallback
    if not state.has_data and "retry-after" in lowered:
        ra = _parse_duration(lowered.get("retry-after", ""))
        if ra > 0:
            state.captured_at = now
            state.provider = provider

    return state


# ── Formatting ──────────────────────────────────────────────────────────


def _fmt_count(n: int) -> str:
    """Human-friendly number: 7999856 -> '8.0M', 33599 -> '33.6K', 799 -> '799'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_seconds(seconds: float) -> str:
    """Seconds -> human-friendly duration: '58s', '2m 14s', '58m 57s', '1h 2m'."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        m, sec = divmod(s, 60)
        return f"{m}m {sec}s" if sec else f"{m}m"
    h, remainder = divmod(s, 3600)
    m = remainder // 60
    return f"{h}h {m}m" if m else f"{h}h"


def _bar(pct: float, width: int = 20) -> str:
    """ASCII progress bar: [████████░░░░░░░░░░░░] 40%."""
    filled = int(pct / 100.0 * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


def _bucket_line(label: str, bucket: RateLimitBucket, label_width: int = 14) -> str:
    """Format one bucket as a single line."""
    if bucket.limit <= 0:
        return f"  {label:<{label_width}}  (no data)"

    pct = bucket.usage_pct
    used = _fmt_count(bucket.used)
    limit = _fmt_count(bucket.limit)
    remaining = _fmt_count(bucket.remaining)
    reset = _fmt_seconds(bucket.remaining_seconds_now)

    bar = _bar(pct)
    return f"  {label:<{label_width}} {bar} {pct:5.1f}%  {used}/{limit} used  ({remaining} left, resets in {reset})"


def format_rate_limit_display(state: RateLimitState) -> str:
    """Format rate limit state for terminal/chat display."""
    if not state.has_data:
        return "No rate limit data yet — make an API request first."

    age = state.age_seconds
    if age < 5:
        freshness = "just now"
    elif age < 60:
        freshness = f"{int(age)}s ago"
    else:
        freshness = f"{_fmt_seconds(age)} ago"

    provider_label = state.provider.title() if state.provider else "Provider"

    lines = [
        f"{provider_label} Rate Limits (captured {freshness}):",
        "",
        _bucket_line("Requests/min", state.requests_min),
        _bucket_line("Requests/hr", state.requests_hour),
        "",
        _bucket_line("Tokens/min", state.tokens_min),
        _bucket_line("Tokens/hr", state.tokens_hour),
    ]

    # Add warnings if any bucket is getting hot
    warnings = []
    for label, bucket in [
        ("requests/min", state.requests_min),
        ("requests/hr", state.requests_hour),
        ("tokens/min", state.tokens_min),
        ("tokens/hr", state.tokens_hour),
    ]:
        if bucket.limit > 0 and bucket.usage_pct >= 80:
            reset = _fmt_seconds(bucket.remaining_seconds_now)
            warnings.append(f"  ⚠ {label} at {bucket.usage_pct:.0f}% — resets in {reset}")

    if warnings:
        lines.append("")
        lines.extend(warnings)

    return "\n".join(lines)


def format_rate_limit_compact(state: RateLimitState) -> str:
    """One-line compact summary for status bars / gateway messages."""
    if not state.has_data:
        return "No rate limit data."

    rm = state.requests_min
    tm = state.tokens_min
    rh = state.requests_hour
    th = state.tokens_hour

    parts = []
    if rm.limit > 0:
        parts.append(f"RPM: {rm.remaining}/{rm.limit}")
    if rh.limit > 0:
        parts.append(f"RPH: {_fmt_count(rh.remaining)}/{_fmt_count(rh.limit)} (resets {_fmt_seconds(rh.remaining_seconds_now)})")
    if tm.limit > 0:
        parts.append(f"TPM: {_fmt_count(tm.remaining)}/{_fmt_count(tm.limit)}")
    if th.limit > 0:
        parts.append(f"TPH: {_fmt_count(th.remaining)}/{_fmt_count(th.limit)} (resets {_fmt_seconds(th.remaining_seconds_now)})")

    return " | ".join(parts)
