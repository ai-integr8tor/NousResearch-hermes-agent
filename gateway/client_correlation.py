"""Parse optional client correlation headers for gateway observability.

Clients may send standard ``X-Request-Id`` and/or ``X-Stream-Token`` headers.
Hermes treats these as opaque strings — no client-specific naming or semantics.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def parse_correlation_headers(headers: Mapping[str, Any]) -> Dict[str, str]:
    """Extract correlation ids from inbound HTTP headers."""
    corr: Dict[str, str] = {}
    request_id = (
        headers.get("X-Request-Id")
        or headers.get("X-Request-ID")
        or ""
    )
    if isinstance(request_id, str):
        request_id = request_id.strip()
    else:
        request_id = str(request_id or "").strip()
    if request_id:
        corr["request_id"] = request_id

    stream_token = headers.get("X-Stream-Token", "")
    if isinstance(stream_token, str):
        stream_token = stream_token.strip()
    else:
        stream_token = str(stream_token or "").strip()
    if stream_token:
        corr["stream_token"] = stream_token
    return corr


def parse_bound_skills_header(headers: Mapping[str, Any]) -> frozenset[str]:
    """Extract bound skill ids from ``X-Hermes-Bound-Skills``."""
    raw = headers.get("X-Hermes-Bound-Skills", "")
    if isinstance(raw, str):
        raw = raw.strip()
    else:
        raw = str(raw or "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def format_correlation_log_suffix(
    corr: Optional[Mapping[str, str]] = None,
    *,
    session_id: Optional[str] = None,
) -> str:
    """Build a space-separated suffix for structured log lines."""
    parts = []
    if corr:
        rid = corr.get("request_id")
        if rid:
            parts.append(f"request_id={rid}")
        st = corr.get("stream_token")
        if st:
            parts.append(f"stream_token={st}")
    if session_id:
        parts.append(f"session={session_id}")
    return f" {' '.join(parts)}" if parts else ""
