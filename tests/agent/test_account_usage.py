"""Tests for agent.account_usage provider fetchers."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.account_usage import (
    AccountUsageSnapshot,
    AccountUsageWindow,
    _fetch_cloudflare_account_usage,
    _fetch_google_account_usage,
    _fetch_nvidia_account_usage,
    _fetch_zai_account_usage,
    fetch_account_usage,
)


# ---------------------------------------------------------------------------
# NVIDIA
# ---------------------------------------------------------------------------

def _nvidia_orgs_response() -> dict:
    return {
        "organizations": [
            {
                "id": 1748966,
                "name": "test-org",
                "displayName": "my-org",
                "type": "INDIVIDUAL",
                "productEnablements": [
                    {
                        "type": "NGC_ADMIN_EVAL",
                        "productName": "AI_FOUNDATIONS",
                        "expirationDate": "2027-05-07",
                    },
                ],
            },
        ],
    }


def _nvidia_subs_response() -> dict:
    return {
        "subscriptions": [
            {
                "orgName": "test-org",
                "products": ["nim-dev", "nvidia-dev"],
                "pendingProducts": [],
                "expiredProducts": [],
            },
        ],
    }


class TestNvidiaFetch:
    def test_no_token_returns_none(self) -> None:
        assert _fetch_nvidia_account_usage(None) is None
        assert _fetch_nvidia_account_usage("") is None

    def test_http_error_returns_none(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("network error")
            mock_client_cls.return_value = mock_client
            assert _fetch_nvidia_account_usage("nvkey") is None

    def test_valid_response_extracts_details(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            org_resp = MagicMock()
            org_resp.status_code = 200
            org_resp.raise_for_status = MagicMock()
            org_resp.json.return_value = _nvidia_orgs_response()

            sub_resp = MagicMock()
            sub_resp.status_code = 200
            sub_resp.json.return_value = _nvidia_subs_response()

            mock_client.get.side_effect = [org_resp, sub_resp]
            mock_client_cls.return_value = mock_client

            snap = _fetch_nvidia_account_usage("nvkey")

        assert snap is not None
        assert snap.provider == "nvidia"
        assert snap.source == "ngc_account_api"
        assert any("my-org" in d for d in snap.details)
        assert any("AI_FOUNDATIONS" in d for d in snap.details)
        assert any("nim-dev" in d for d in snap.details)
        assert snap.unavailable_reason is not None
        assert "does not expose" in snap.unavailable_reason

    def test_empty_orgs_returns_none(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            org_resp = MagicMock()
            org_resp.status_code = 200
            org_resp.raise_for_status = MagicMock()
            org_resp.json.return_value = {"organizations": []}

            sub_resp = MagicMock()
            sub_resp.status_code = 200
            sub_resp.json.return_value = {"subscriptions": []}

            mock_client.get.side_effect = [org_resp, sub_resp]
            mock_client_cls.return_value = mock_client

            assert _fetch_nvidia_account_usage("nvkey") is None


# ---------------------------------------------------------------------------
# Cloudflare
# ---------------------------------------------------------------------------

CF_BASE_URL = "https://api.cloudflare.com/client/v4/accounts/abc123def456/ai/v1"


def _cf_graphql_response(neurons: int = 0, in_tok: int = 0, out_tok: int = 0) -> dict:
    return {
        "data": {
            "viewer": {
                "accounts": [
                    {
                        "aiInferenceAdaptiveGroups": [
                            {
                                "sum": {
                                    "totalNeurons": neurons,
                                    "totalInputTokens": in_tok,
                                    "totalOutputTokens": out_tok,
                                },
                                "dimensions": {"modelId": "@cf/test-model"},
                            },
                        ],
                    },
                ],
            },
        },
    }


class TestCloudflareFetch:
    def test_no_token_returns_none(self) -> None:
        assert _fetch_cloudflare_account_usage(CF_BASE_URL, None) is None
        assert _fetch_cloudflare_account_usage(CF_BASE_URL, "") is None

    def test_no_base_url_returns_none(self) -> None:
        assert _fetch_cloudflare_account_usage(None, "token") is None

    def test_no_account_id_in_url_returns_none(self) -> None:
        assert _fetch_cloudflare_account_usage(
            "https://example.com/v1", "token"
        ) is None

    def test_graphql_error_returns_unavailable(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"errors": [{"message": "not authorized"}]}

            mock_client.post.return_value = resp
            mock_client_cls.return_value = mock_client

            snap = _fetch_cloudflare_account_usage(CF_BASE_URL, "cfut_token")

        assert snap is not None
        assert snap.provider == "cloudflare"
        assert snap.unavailable_reason is not None
        assert "Analytics scope" in snap.unavailable_reason

    def test_valid_response_calculates_neuron_usage(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = _cf_graphql_response(
                neurons=2500, in_tok=1000, out_tok=500
            )

            mock_client.post.return_value = resp
            mock_client_cls.return_value = mock_client

            snap = _fetch_cloudflare_account_usage(CF_BASE_URL, "valid-token")

        assert snap is not None
        assert snap.provider == "cloudflare"
        assert len(snap.windows) == 1
        assert snap.windows[0].label == "Neurons (daily)"
        # 2500/10000 = 25%
        assert snap.windows[0].used_percent == 25.0
        assert "2500" in (snap.windows[0].detail or "")

    def test_zero_usage_shows_empty_state(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = _cf_graphql_response(neurons=0)

            mock_client.post.return_value = resp
            mock_client_cls.return_value = mock_client

            snap = _fetch_cloudflare_account_usage(CF_BASE_URL, "valid-token")

        assert snap is not None
        assert len(snap.windows) == 1
        assert snap.windows[0].used_percent == 0.0

    def test_network_error_returns_none(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("timeout")
            mock_client_cls.return_value = mock_client

            assert _fetch_cloudflare_account_usage(CF_BASE_URL, "token") is None


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

class TestGoogleFetch:
    def test_no_token_returns_none(self) -> None:
        assert _fetch_google_account_usage(None) is None
        assert _fetch_google_account_usage("") is None

    def test_api_key_returns_unavailable(self) -> None:
        snap = _fetch_google_account_usage("AIzaSyTestApiKey123")
        assert snap is not None
        assert snap.provider == "google"
        assert snap.unavailable_reason is not None
        assert "OAuth" in snap.unavailable_reason

    def test_oauth_token_fetches_quota(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            resp1 = MagicMock()
            resp1.raise_for_status = MagicMock()
            resp1.json.return_value = {
                "cloudaicompanionProject": "test-project-123",
                "currentTier": "STANDARD",
            }

            resp2 = MagicMock()
            resp2.raise_for_status = MagicMock()
            resp2.json.return_value = {
                "buckets": [
                    {
                        "modelId": "gemini-2.0-flash",
                        "tokenType": "request",
                        "remainingFraction": 0.575,
                        "resetTime": "2026-07-06T00:00:00Z",
                    },
                    {
                        "modelId": "internal-infra-bucket",
                        "tokenType": "tokens",
                        "remainingFraction": 0.9,
                    },
                ],
            }

            mock_client.post.side_effect = [resp1, resp2]
            mock_client_cls.return_value = mock_client

            snap = _fetch_google_account_usage("ya29.test-oauth-token")

        assert snap is not None
        assert snap.provider == "google"
        assert snap.source == "cloud_code_assist"
        # Only user-facing models (gemini-, claude-, gpt-) are included
        assert len(snap.windows) == 1
        assert "gemini-2.0-flash" in snap.windows[0].label
        # remainingFraction=0.575 -> used=42.5%
        assert snap.windows[0].used_percent == 42.5
        assert any("STANDARD" in d for d in snap.details)

    def test_no_project_returns_unavailable(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            resp1 = MagicMock()
            resp1.raise_for_status = MagicMock()
            resp1.json.return_value = {}  # No project

            mock_client.post.return_value = resp1
            mock_client_cls.return_value = mock_client

            snap = _fetch_google_account_usage("ya29.token")

        assert snap is not None
        assert snap.unavailable_reason is not None
        assert "project" in snap.unavailable_reason.lower()

    def test_network_error_returns_none(self) -> None:
        with patch("agent.account_usage.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("timeout")
            mock_client_cls.return_value = mock_client

            assert _fetch_google_account_usage("ya29.token") is None


# ---------------------------------------------------------------------------
# Dispatch (fetch_account_usage)
# ---------------------------------------------------------------------------

class TestFetchAccountUsageDispatch:
    def test_cloudflare_dispatches(self) -> None:
        with patch(
            "agent.account_usage._fetch_cloudflare_account_usage"
        ) as mock_cf:
            mock_cf.return_value = AccountUsageSnapshot(
                provider="cloudflare",
                source="test",
                fetched_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            )
            result = fetch_account_usage("cloudflare", base_url=CF_BASE_URL, api_key="tok")
            mock_cf.assert_called_once_with(CF_BASE_URL, "tok")
            assert result is not None
            assert result.provider == "cloudflare"

    def test_google_dispatches(self) -> None:
        with patch(
            "agent.account_usage._fetch_google_account_usage"
        ) as mock_g:
            mock_g.return_value = None
            fetch_account_usage("google", api_key="AIzaTest")
            mock_g.assert_called_once_with("AIzaTest")

    def test_nvidia_dispatches(self) -> None:
        with patch(
            "agent.account_usage._fetch_nvidia_account_usage"
        ) as mock_nv:
            mock_nv.return_value = None
            fetch_account_usage("nvidia", api_key="nvkey")
            mock_nv.assert_called_once_with("nvkey")

    def test_unknown_provider_returns_none(self) -> None:
        assert fetch_account_usage("unknown-provider") is None

    def test_empty_provider_returns_none(self) -> None:
        assert fetch_account_usage("") is None
        assert fetch_account_usage(None) is None

    def test_auto_provider_returns_none(self) -> None:
        assert fetch_account_usage("auto") is None


# ---------------------------------------------------------------------------
# Z.AI (smoke test -- already tested via integration)
# ---------------------------------------------------------------------------

class TestZaiFetchSmoke:
    def test_no_token_returns_none(self) -> None:
        assert _fetch_zai_account_usage(None) is None
        assert _fetch_zai_account_usage("") is None
