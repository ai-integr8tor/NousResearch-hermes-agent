"""Unit tests for the LLMTR provider profile registration and wiring.

LLMTR is a Türkiye-based, OpenAI-compatible AI gateway. The profile is a
plain ``ProviderProfile`` (no custom hooks), so these tests pin the identity
contract that the rest of the harness auto-wires from: the profile is
registered, resolvable via its aliases, points at the right OpenAI-compatible
base URL, and advertises an auxiliary model so consumers don't fall back to the
"No auxiliary LLM provider configured" warning.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def llmtr_profile():
    """Resolve the registered LLMTR profile through the public registry.

    Importing ``model_tools`` triggers plugin discovery, which is what
    registers the LLMTR profile in the global provider registry.
    """
    import model_tools  # noqa: F401
    import providers

    profile = providers.get_provider_profile("llmtr")
    assert profile is not None, "llmtr provider profile must be registered"
    return profile


class TestLlmtrIdentity:
    def test_canonical_name(self, llmtr_profile):
        assert llmtr_profile.name == "llmtr"

    @pytest.mark.parametrize("alias", ["llm-tr", "llmtr-com", "llmtr.com"])
    def test_aliases_resolve(self, alias):
        import providers

        assert providers.get_provider_profile(alias).name == "llmtr"

    def test_openai_compatible_base_url(self, llmtr_profile):
        assert llmtr_profile.base_url == "https://llmtr.com/v1"

    def test_hostname_derives_from_base_url(self, llmtr_profile):
        assert llmtr_profile.get_hostname() == "llmtr.com"

    def test_api_key_env_vars(self, llmtr_profile):
        assert "LLMTR_API_KEY" in llmtr_profile.env_vars

    def test_api_key_auth_mode(self, llmtr_profile):
        # api_key auth is what gets the provider auto-injected into the picker.
        assert llmtr_profile.auth_type == "api_key"


class TestLlmtrModels:
    def test_fallback_models_use_provider_slug_format(self, llmtr_profile):
        assert llmtr_profile.fallback_models, "expected curated fallback models"
        for model in llmtr_profile.fallback_models:
            assert "/" in model, f"LLMTR routes by provider/model slug: {model!r}"

    def test_aux_model_advertised(self, llmtr_profile):
        assert llmtr_profile.default_aux_model == "google/gemini-2.5-flash"

    def test_consumer_api_returns_aux_model(self):
        from agent.auxiliary_client import _get_aux_model_for_provider

        assert _get_aux_model_for_provider("llmtr") == "google/gemini-2.5-flash"


class TestLlmtrPickerExposure:
    def test_appears_in_canonical_providers(self):
        """The api_key auto-extend loop must surface LLMTR in the model picker."""
        from hermes_cli.models import CANONICAL_PROVIDERS

        slugs = {p.slug for p in CANONICAL_PROVIDERS}
        assert "llmtr" in slugs
