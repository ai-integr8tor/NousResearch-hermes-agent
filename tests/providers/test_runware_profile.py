"""Tests for the Runware provider profile."""

import json
from unittest.mock import patch

from providers import get_provider_profile


class TestRunwareProfile:
    def test_discovered(self):
        p = get_provider_profile("runware")
        assert p is not None
        assert p.name == "runware"

    def test_aliases(self):
        assert get_provider_profile("runware-ai").name == "runware"
        assert get_provider_profile("runwareai").name == "runware"

    def test_base_url(self):
        p = get_provider_profile("runware")
        assert p.base_url == "https://api.runware.ai/v1"

    def test_api_key_provider(self):
        p = get_provider_profile("runware")
        assert p.auth_type == "api_key"
        assert p.env_vars == ("RUNWARE_API_KEY", "RUNWARE_BASE_URL")

    def test_no_special_temperature(self):
        p = get_provider_profile("runware")
        assert p.fixed_temperature is None

    def test_fallback_models_nonempty(self):
        p = get_provider_profile("runware")
        assert p.fallback_models
        assert "openai-gpt-5-4" in p.fallback_models

    def test_default_aux_model(self):
        p = get_provider_profile("runware")
        assert p.default_aux_model == "deepseek-v4-flash"


class TestRunwareMaxTokens:
    """Runware 400s when max_tokens is omitted, using an internal default
    that exceeds some models' real completion-token cap. get_max_tokens()
    must return each model's verified cap, and None for unlisted models
    (safe fallback — no crash risk for models we have no data on)."""

    def test_known_model_cap(self):
        p = get_provider_profile("runware")
        assert p.get_max_tokens("deepseek-v4-flash") == 384000

    def test_different_models_get_different_caps(self):
        p = get_provider_profile("runware")
        assert p.get_max_tokens("moonshotai-kimi-k2-6") == 49152
        assert p.get_max_tokens("minimax-m3") == 512000

    def test_unknown_model_returns_none(self):
        p = get_provider_profile("runware")
        assert p.get_max_tokens("openai-gpt-5-1") is None
        assert p.get_max_tokens("some-brand-new-model") is None

    def test_none_model_returns_none(self):
        p = get_provider_profile("runware")
        assert p.get_max_tokens(None) is None


class TestRunwareFetchModelsBareList:
    """Runware's /v1/models returns a bare JSON array, not {"data": [...]}."""

    def test_fetch_models_parses_bare_list(self):
        p = get_provider_profile("runware")
        fake_response = [
            {"id": "openai-gpt-5-4", "object": "model", "owned_by": "openai"},
            {"id": "minimax-m3", "object": "model", "owned_by": "minimax"},
        ]

        class _Resp:
            def read(self):
                return json.dumps(fake_response).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch("urllib.request.urlopen", return_value=_Resp()):
            models = p.fetch_models(api_key="test-key")

        assert models == ["openai-gpt-5-4", "minimax-m3"]
