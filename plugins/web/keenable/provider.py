"""Keenable web search + content extraction — plugin form.

Subclasses :class:`agent.web_search_provider.WebSearchProvider`. Two
capabilities, both sync (the underlying call is ``httpx``):

- ``supports_search()``  -> True (Keenable ``GET /v1/search``)
- ``supports_extract()`` -> True (Keenable ``GET /v1/fetch``, one URL per call)

Config keys this provider responds to::

    web:
      search_backend: "keenable"      # explicit per-capability
      extract_backend: "keenable"     # explicit per-capability
      backend: "keenable"             # shared fallback for both

Env vars::

    KEENABLE_API_KEY=...             # https://keenable.ai/signup (optional)
    KEENABLE_API_URL=...             # optional override of https://api.keenable.ai

Keyless: Keenable's free tier works without a key. When ``KEENABLE_API_KEY``
is unset the provider calls the ``/public`` endpoint variants (rate-limited)
and omits the ``X-API-Key`` header — mirroring Keenable's own MCP client.

It stays **opt-in**, not a silent default: ``is_available()`` is key-gated, so
keenable is never auto-selected in the no-credential fallback (it would only
take over the no-config default otherwise — the posture #46350 reverted). It
works keyless only when explicitly chosen via ``web.backend``/``*_backend``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

# Identifies Hermes to Keenable for traffic attribution. Sent on every call.
_CLIENT_TITLE = "Hermes"


def _keenable_base_url() -> str:
    return os.getenv("KEENABLE_API_URL", "https://api.keenable.ai").rstrip("/")


def _api_key() -> str:
    return os.getenv("KEENABLE_API_KEY", "").strip()


def _keenable_headers(api_key: str) -> Dict[str, str]:
    """Request headers; ``X-API-Key`` only when a key is present (keyless otherwise)."""
    headers = {"X-Keenable-Title": _CLIENT_TITLE, "Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _endpoint(base_url: str, path: str, api_key: str) -> str:
    """Keyless calls hit the ``/public`` variant (no auth, rate-limited)."""
    return f"{base_url}{path}" if api_key else f"{base_url}{path}/public"


def _normalize_search_results(response: Dict[str, Any]) -> Dict[str, Any]:
    """Map Keenable ``/v1/search`` response to ``{success, data: {web: [...]}}``.

    Each ``SearchResultDTO`` has ``id``, ``title``, ``url``, ``description``.
    """
    web_results = []
    for i, result in enumerate(response.get("results", []) or []):
        web_results.append(
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("description", ""),
                "position": i + 1,
            }
        )
    return {"success": True, "data": {"web": web_results}}


class KeenableWebSearchProvider(WebSearchProvider):
    """Keenable search + extract provider."""

    @property
    def name(self) -> str:
        return "keenable"

    @property
    def display_name(self) -> str:
        return "Keenable"

    def is_available(self) -> bool:
        """Return True when ``KEENABLE_API_KEY`` is set to a non-empty value."""
        return bool(os.getenv("KEENABLE_API_KEY", "").strip())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute a Keenable search (``GET /v1/search?query=``).

        The API takes no result-count param (query/mode/site/date filters
        only), so ``limit`` is applied client-side to the ranked results.
        """
        try:
            from tools.interrupt import is_interrupted

            if is_interrupted():
                return {"success": False, "error": "Interrupted"}

            import httpx

            api_key = _api_key()
            logger.info("Keenable search: '%s' (limit=%d)", query, limit)
            response = httpx.get(
                _endpoint(_keenable_base_url(), "/v1/search", api_key),
                headers=_keenable_headers(api_key),
                params={"query": query},
                timeout=60,
            )
            response.raise_for_status()
            normalized = _normalize_search_results(response.json())
            normalized["data"]["web"] = normalized["data"]["web"][:limit]
            return normalized
        except Exception as exc:  # noqa: BLE001 — including httpx errors
            logger.warning("Keenable search error: %s", exc)
            return {"success": False, "error": f"Keenable search failed: {exc}"}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Extract content from URLs via Keenable (``GET /v1/fetch``, one per URL).

        Sync — the underlying call is ``httpx.get(...)``. Returns the legacy
        list-of-results shape; per-URL failures become items with ``error``.
        """
        try:
            from tools.interrupt import is_interrupted
        except Exception:  # noqa: BLE001 — interrupt support is optional
            is_interrupted = lambda: False  # noqa: E731

        import httpx

        base_url = _keenable_base_url()
        api_key = _api_key()
        headers = _keenable_headers(api_key)
        fetch_url = _endpoint(base_url, "/v1/fetch", api_key)
        documents: List[Dict[str, Any]] = []

        # /v1/fetch takes a single ``url`` query param (no batch, no max_chars).
        for url in urls:
            if is_interrupted():
                documents.append({"url": url, "title": "", "content": "", "error": "Interrupted"})
                continue
            try:
                logger.info("Keenable fetch: %s", url)
                response = httpx.get(
                    fetch_url,
                    headers=headers,
                    params={"url": url},
                    timeout=60,
                )
                response.raise_for_status()
                payload = response.json()
                title = payload.get("title", "")
                content = payload.get("content", "")
                metadata = {"sourceURL": url, "title": title}
                if isinstance(payload.get("metadata"), dict):
                    metadata.update(payload["metadata"])
                documents.append(
                    {
                        "url": payload.get("url", url),
                        "title": title,
                        "content": content,
                        "raw_content": content,
                        "metadata": metadata,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Keenable fetch error for %s: %s", url, exc)
                documents.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "raw_content": "",
                        "error": f"Keenable fetch failed: {exc}",
                        "metadata": {"sourceURL": url},
                    }
                )
        return documents

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Keenable",
            "badge": "free",
            "tag": "Search + page fetch; free tier works keyless, key raises limits.",
            "env_vars": [
                {
                    "key": "KEENABLE_API_KEY",
                    "prompt": "Keenable API key (optional — blank uses the keyless free tier)",
                    "url": "https://keenable.ai/signup",
                },
            ],
        }
