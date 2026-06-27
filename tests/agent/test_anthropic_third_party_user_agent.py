"""Tests for optional User-Agent override on third-party Anthropic endpoints.

Background: third-party Anthropic-compatible endpoints behind Cloudflare/WAF
often block the SDK default UA (Anthropic-Python) with HTTP 403.
``build_anthropic_client`` supports an opt-in ``user_agent`` override (and
``HERMES_THIRD_PARTY_UA`` env var) that ONLY applies when explicitly configured.
Default behavior (SDK default UA = main behavior) is preserved, so other
third-party endpoints (Bedrock, Foundry, etc.) are unaffected.
"""
from __future__ import annotations

from agent.anthropic_adapter import build_anthropic_client


# A non-anthropic.com URL → classified as a third-party Anthropic endpoint.
_TP_URL = "https://third-party-example.invalid"


def _user_agent(client) -> str | None:
    headers = getattr(client, "default_headers", None) or {}
    return headers.get("User-Agent") or headers.get("user-agent")


class TestThirdPartyUserAgentOverride:
    def test_user_agent_kwarg_overrides_sdk_default(self, monkeypatch):
        monkeypatch.delenv("HERMES_THIRD_PARTY_UA", raising=False)
        client = build_anthropic_client("sk-test", base_url=_TP_URL, user_agent="my-agent/1.0")
        assert _user_agent(client) == "my-agent/1.0"

    def test_env_var_used_when_no_kwarg(self, monkeypatch):
        monkeypatch.setenv("HERMES_THIRD_PARTY_UA", "env-agent/2.0")
        client = build_anthropic_client("sk-test", base_url=_TP_URL, user_agent=None)
        assert _user_agent(client) == "env-agent/2.0"

    def test_kwarg_takes_priority_over_env(self, monkeypatch):
        monkeypatch.setenv("HERMES_THIRD_PARTY_UA", "env-agent/2.0")
        client = build_anthropic_client("sk-test", base_url=_TP_URL, user_agent="kwarg-agent/3.0")
        assert _user_agent(client) == "kwarg-agent/3.0"

    def test_no_override_keeps_sdk_default(self, monkeypatch):
        """When neither user_agent nor env is set, no User-Agent is forced —
        the SDK default (main behavior) is preserved."""
        monkeypatch.delenv("HERMES_THIRD_PARTY_UA", raising=False)
        client = build_anthropic_client("sk-test", base_url=_TP_URL, user_agent=None)
        assert _user_agent(client) != "hermes-agent"
