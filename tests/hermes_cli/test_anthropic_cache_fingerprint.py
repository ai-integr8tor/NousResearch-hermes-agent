"""Regression tests for #59342: provider_models_cache key must depend on the
effective base_url, so that running Claude via Nous Portal (or any
anthropic-compatible proxy) does not poison the native-Anthropic cache slot
and vice versa.

Layers covered (see .automation/runs/<ts>/59342/LAYERS.md):

- L1: catalog fetch via proxy returns the proxy's catalog
- L2: cache key collides between native + proxy when base_url is ignored
- L3: _credential_fingerprint does not include the effective base_url
- L4: picker contamination downstream
- L5: cross-tenant catalog sharing on cache hit
- Edge A: no base_url (default Anthropic) keeps current cache key behavior
- Edge B: explicit api.anthropic.com base_url produces a different key from unset
- Edge C: proxy base_url produces a different key from native
- Edge D: changing base_url in config invalidates the cached entry
- Edge E: already-poisoned cache is naturally evicted by fingerprint change
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from hermes_cli.models import (
    _credential_fingerprint,
    cached_provider_model_ids,
    provider_model_ids,
)


# ─── fixtures ──────────────────────────────────────────────────────────


def _write_cache(tmp_path, payload):
    """Write a provider_models_cache.json into the per-test HERMES_HOME."""
    path = tmp_path / "provider_models_cache.json"
    path.write_text(json.dumps(payload))
    return path


def _no_anthropic_live(*args, **kwargs):
    """Stub for _fetch_anthropic_models when the test doesn't care about the
    network call. Tests that DO care about the live call patch _fetch_anthropic_models
    directly with their own stub."""
    return None


# ─── L3: _credential_fingerprint must include the effective base_url ───


class TestCredentialFingerprintIncludesBaseUrl:
    def test_fingerprint_changes_when_base_url_changes(self, tmp_path, monkeypatch):
        """If the model config switches base_url from a proxy to native, the
        fingerprint must change so the cache slot is invalidated."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "auth.json").write_text("{}")
        (tmp_path / "credentials.json").write_text("{}")

        # No config at all → fingerprint A
        with patch("hermes_cli.models._get_model_config_dict", return_value={}):
            fp_default = _credential_fingerprint("anthropic")

        # Proxy base_url configured → fingerprint B
        with patch(
            "hermes_cli.models._get_model_config_dict",
            return_value={"provider": "anthropic", "base_url": "https://inference-api.nousresearch.com/v1"},
        ):
            fp_proxy = _credential_fingerprint("anthropic")

        # Native Anthropic base_url configured → fingerprint C
        with patch(
            "hermes_cli.models._get_model_config_dict",
            return_value={"provider": "anthropic", "base_url": "https://api.anthropic.com/v1"},
        ):
            fp_native = _credential_fingerprint("anthropic")

        # All three must be distinct — the cache slot for "anthropic" must
        # not collide between (no-config) and (proxy) and (native-explicit).
        assert fp_default != fp_proxy, (
            f"Fingerprint did not change when base_url was set to a proxy "
            f"(default={fp_default}, proxy={fp_proxy}) — cache slot collides."
        )
        assert fp_default != fp_native, (
            f"Fingerprint did not change when base_url was set to native "
            f"(default={fp_default}, native={fp_native}) — cache slot collides."
        )
        assert fp_proxy != fp_native, (
            f"Fingerprint did not distinguish proxy from native "
            f"(proxy={fp_proxy}, native={fp_native})."
        )

    def test_fingerprint_stable_for_same_base_url(self, tmp_path, monkeypatch):
        """Same base_url must produce the same fingerprint across calls —
        stability is required so the cache hit path still works."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "auth.json").write_text("{}")
        (tmp_path / "credentials.json").write_text("{}")

        cfg = {"provider": "anthropic", "base_url": "https://api.anthropic.com/v1"}
        with patch("hermes_cli.models._get_model_config_dict", return_value=cfg):
            fp1 = _credential_fingerprint("anthropic")
        with patch("hermes_cli.models._get_model_config_dict", return_value=cfg):
            fp2 = _credential_fingerprint("anthropic")
        assert fp1 == fp2, f"Same base_url produced different fingerprints: {fp1} vs {fp2}"

    def test_fingerprint_stable_for_no_base_url(self, tmp_path, monkeypatch):
        """No model config (or empty config) must produce a stable fingerprint
        that doesn't depend on transient filesystem state across calls."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "auth.json").write_text("{}")
        (tmp_path / "credentials.json").write_text("{}")

        with patch("hermes_cli.models._get_model_config_dict", return_value={}):
            fp1 = _credential_fingerprint("anthropic")
        with patch("hermes_cli.models._get_model_config_dict", return_value={}):
            fp2 = _credential_fingerprint("anthropic")
        assert fp1 == fp2, f"Default fingerprint unstable: {fp1} vs {fp2}"


# ─── L1 + L2: cached_provider_model_ids must segregate proxy vs native ──


class TestCacheKeySegregatesByBaseUrl:
    def _stub_live_for(self, models_to_return):
        """Returns a side_effect that mimics _fetch_anthropic_models based on
        its `base_url` argument. The stub distinguishes native vs proxy and
        returns the appropriate catalog."""
        def _stub(*, base_url=None, api_key=None, **kwargs):
            if base_url and "nousresearch" in base_url:
                # Proxy catalog: includes the full Portal catalog
                return list(models_to_return["proxy"])
            if base_url and "anthropic" in base_url:
                return list(models_to_return["native"])
            # Default (no base_url) → native catalog
            return list(models_to_return.get("default", models_to_return["native"]))
        return _stub

    def test_proxy_fetch_writes_to_distinct_cache_slot(self, tmp_path, monkeypatch):
        """When a proxy base_url is configured, the cache slot for the proxy
        catalog must be distinct from the native-Anthropic cache slot.

        Pre-fix: the slot is `cache["anthropic"]` regardless of base_url, so
        a proxy fetch overwrites the native catalog. The regression test
        verifies the slot key now includes the base_url."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        catalogs = {
            "native": ["claude-opus-4", "claude-sonnet-4", "claude-haiku-4"],
            "proxy": [
                "anthropic/claude-opus-4", "anthropic/claude-sonnet-4",
                "qwen/qwen3.7-max", "deepseek/deepseek-v4",
                "z-ai/glm-5.2", "ai21/jamba-large-1.7",
            ],
        }
        stub = self._stub_live_for(catalogs)

        with patch("hermes_cli.models._fetch_anthropic_models", side_effect=stub):
            # 1) First, fetch the proxy catalog.
            with patch(
                "hermes_cli.models._get_model_config_dict",
                return_value={"provider": "anthropic", "base_url": "https://inference-api.nousresearch.com/v1"},
            ):
                proxy_ids = cached_provider_model_ids("anthropic")

            assert proxy_ids == catalogs["proxy"], (
                f"Proxy fetch returned the wrong catalog: {proxy_ids}"
            )

            # 2) The cache file must now contain entries under distinct slots
            #    for proxy and native, not a single shared "anthropic" key.
            cache_path = tmp_path / "provider_models_cache.json"
            cache = json.loads(cache_path.read_text())
            assert len(cache) >= 1
            # The shared "anthropic" slot alone is the bug.
            # Acceptable keys after the fix:
            #   - "anthropic" (default / no-base-url)
            #   - "anthropic+base_url=<host>" (or similar encoding)
            #   - the proxy catalog MUST live under a key that is distinct
            #     from the slot a native fetch would write to.
            keys = list(cache.keys())
            assert any("nousresearch" in k for k in keys) or any(
                k != "anthropic" for k in keys
            ), (
                f"Cache keys after proxy fetch do not encode base_url — "
                f"got {keys}. The proxy catalog collides with the native slot."
            )

    def test_native_fetch_after_proxy_does_not_return_poisoned_catalog(self, tmp_path, monkeypatch):
        """The exact symptom from the issue: pick a Claude model served via
        Nous Portal, then switch back to a native Anthropic credential, and
        the picker must show the native catalog, not the Nous Portal catalog.

        Pre-fix: cached_provider_model_ids("anthropic") returns the proxy
        catalog. Post-fix: a base_url change forces a re-fetch."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        catalogs = {
            "native": ["claude-opus-4", "claude-sonnet-4", "claude-haiku-4"],
            "proxy": [
                "anthropic/claude-opus-4", "anthropic/claude-sonnet-4",
                "qwen/qwen3.7-max", "deepseek/deepseek-v4", "z-ai/glm-5.2",
            ],
        }
        stub = self._stub_live_for(catalogs)

        with patch("hermes_cli.models._fetch_anthropic_models", side_effect=stub):
            # 1) Fetch while proxy is configured.
            with patch(
                "hermes_cli.models._get_model_config_dict",
                return_value={"provider": "anthropic", "base_url": "https://inference-api.nousresearch.com/v1"},
            ):
                proxy_ids = cached_provider_model_ids("anthropic")
            assert any("qwen" in m for m in proxy_ids), (
                f"Proxy fetch should include qwen models: {proxy_ids}"
            )

            # 2) Switch to native (no base_url).
            with patch("hermes_cli.models._get_model_config_dict", return_value={}):
                native_ids = cached_provider_model_ids("anthropic")

            # The native (no-base_url) path merges the curated Anthropic
            # catalog with the live fetch, so `native_ids` will contain the
            # full curated claude list — NOT the 3-element stub. What matters
            # is that NO proxy-only models leaked through: the proxy catalog
            # (qwen, deepseek, z-ai, ai21) must be entirely absent, proving
            # the base_url change invalidated the poisoned cache slot.
            proxy_only = ("qwen", "deepseek", "z-ai", "ai21")
            leaked = [m for m in native_ids if any(v in m for v in proxy_only)]
            assert not leaked, (
                f"Native fetch returned proxy catalog — cache was not "
                f"invalidated by base_url change. Leaked: {leaked}"
            )
            # And the native result must differ from the proxy catalog.
            assert native_ids != proxy_ids, (
                f"Native fetch returned the exact proxy catalog: {native_ids}"
            )

    def test_proxy_then_proxy_returns_same_catalog_via_cache(self, tmp_path, monkeypatch):
        """Two consecutive proxy fetches with the same base_url must hit the
        cache and return the same list — fingerprint change shouldn't bust
        the cache on a stable config."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        catalogs = {
            "native": ["claude-opus-4"],
            "proxy": ["anthropic/claude-opus-4", "qwen/qwen3.7-max"],
        }
        stub = self._stub_live_for(catalogs)
        cfg = {"provider": "anthropic", "base_url": "https://inference-api.nousresearch.com/v1"}

        with patch("hermes_cli.models._fetch_anthropic_models", side_effect=stub) as m:
            with patch("hermes_cli.models._get_model_config_dict", return_value=cfg):
                a = cached_provider_model_ids("anthropic")
            with patch("hermes_cli.models._get_model_config_dict", return_value=cfg):
                b = cached_provider_model_ids("anthropic")
            assert a == b
            # Second call must hit the cache (live fetch not called again).
            assert m.call_count == 1, (
                f"Live fetch called {m.call_count} times for stable base_url — "
                f"cache hit broken."
            )

    def test_default_anthropic_cache_slot_unchanged_for_no_config(self, tmp_path, monkeypatch):
        """Edge case A: users with no `model.base_url` set must continue to
        cache under the bare `anthropic` slot. This preserves the existing
        cache layout for the default config and avoids invalidating every
        native-Anthropic user's cache on upgrade."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        # The cfg_base_url-empty branch in provider_model_ids() merges the
        # live fetch with _PROVIDER_MODELS["anthropic"] (curated catalog).
        # Use a stub that adds ONE distinctive live-only model so we can
        # detect the merge deterministically without enumerating the curated
        # list.
        def _stub(*, base_url=None, api_key=None, **kwargs):
            return ["claude-opus-4-9-live"]

        with patch("hermes_cli.models._fetch_anthropic_models", side_effect=_stub):
            with patch("hermes_cli.models._get_model_config_dict", return_value={}):
                cached_provider_model_ids("anthropic")

        cache_path = tmp_path / "provider_models_cache.json"
        cache = json.loads(cache_path.read_text())
        # Bare "anthropic" key is preserved for the default (no-config) case.
        assert "anthropic" in cache, (
            f"Default-config users lost the bare 'anthropic' cache slot. "
            f"Got keys: {list(cache.keys())}"
        )
        # The cached models for "anthropic" include the stub-returned live model
        # (plus curated entries; the curated list is what it is).
        assert "claude-opus-4-9-live" in cache["anthropic"]["models"], (
            f"Live fetch did not land in the bare 'anthropic' cache slot. "
            f"Got: {cache['anthropic']['models']}"
        )


# ─── L4: provider_model_ids path (called by the picker) ───────────────


class TestProviderModelIdsSegregatesByBaseUrl:
    def test_provider_model_ids_returns_proxy_catalog_when_base_url_set(self, tmp_path, monkeypatch):
        """The picker calls provider_model_ids('anthropic') — the cfg_base_url
        branch must return the proxy catalog, not the native one, and the
        cache fingerprint must encode the base_url so this catalog is
        stored under a slot that won't collide with native."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        proxy_catalog = ["anthropic/claude-opus-4", "qwen/qwen3.7-max"]

        with patch("hermes_cli.models._fetch_anthropic_models", return_value=proxy_catalog):
            with patch(
                "hermes_cli.models._get_model_config_dict",
                return_value={"provider": "anthropic", "base_url": "https://inference-api.nousresearch.com/v1"},
            ):
                ids = provider_model_ids("anthropic")

        assert ids == proxy_catalog
        # And the cache slot must encode the base_url.
        cache_path = tmp_path / "provider_models_cache.json"
        if cache_path.exists():
            cache = json.loads(cache_path.read_text())
            # After the fix, the bare "anthropic" key alone is not acceptable
            # for a proxy fetch — it must be qualified.
            if "anthropic" in cache and len(cache) == 1:
                pytest.fail(
                    f"Proxy catalog written to bare 'anthropic' slot — will "
                    f"collide with native. Keys: {list(cache.keys())}"
                )


# ─── L5: cross-tenant catalog sharing on cache hit ────────────────────


class TestCrossTenantCacheSegregation:
    def test_litellm_proxy_base_url_distinct_from_nous_portal(self, tmp_path, monkeypatch):
        """Two different proxies (LiteLLM vs Nous Portal) must not share a
        cache slot — their catalogs will differ."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        catalogs = {
            "native": ["claude-opus-4"],
            "proxy": ["anthropic/claude-opus-4", "qwen/qwen3.7-max"],
        }

        def _stub(*, base_url=None, api_key=None, **kwargs):
            if base_url and "litellm" in base_url:
                return ["anthropic/claude-opus-4", "openai/gpt-5.5"]
            if base_url and "nousresearch" in base_url:
                return list(catalogs["proxy"])
            if base_url and "anthropic" in base_url:
                return list(catalogs["native"])
            return list(catalogs["native"])

        with patch("hermes_cli.models._fetch_anthropic_models", side_effect=_stub):
            with patch(
                "hermes_cli.models._get_model_config_dict",
                return_value={"provider": "anthropic", "base_url": "https://inference-api.nousresearch.com/v1"},
            ):
                a = cached_provider_model_ids("anthropic")

            with patch(
                "hermes_cli.models._get_model_config_dict",
                return_value={"provider": "anthropic", "base_url": "https://litellm.internal.example.com/v1"},
            ):
                b = cached_provider_model_ids("anthropic")

        assert a != b, (
            f"Two different proxies produced the same cache hit — base_url "
            f"not encoded in the cache key. a={a}, b={b}"
        )


# ─── Edge E: already-poisoned caches are naturally evicted ────────────


class TestStaleCacheEviction:
    def test_existing_poisoned_entry_evicted_by_fingerprint_change(self, tmp_path, monkeypatch):
        """A user upgrading from a buggy Hermes may have a poisoned
        `cache["anthropic"]` entry from a previous proxy fetch. The new
        fingerprint (which now includes base_url) must NOT match the old
        fingerprint, so the live fetch is re-attempted instead of returning
        the poisoned entry."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        # Simulate a poisoned cache: bare "anthropic" slot containing proxy
        # models, with a fingerprint computed under the OLD logic (no
        # base_url) — represented here as a fixed string.
        poisoned = {
            "anthropic": {
                "fp": "OLD-FINGERPRINT-NO-BASE-URL",
                "at": 0.0,
                "models": ["qwen/qwen3.7-max", "deepseek/deepseek-v4"],
            }
        }
        cache_path = tmp_path / "provider_models_cache.json"
        cache_path.write_text(json.dumps(poisoned))

        # New live fetch returns the real (native) catalog. The native
        # (no-base_url) path merges this with the curated Anthropic list, so
        # `ids` will contain curated claude models too — what matters is that
        # the poisoned proxy models are gone AND a live fetch actually ran
        # (proving the stale entry was evicted rather than returned).
        with patch(
            "hermes_cli.models._fetch_anthropic_models", return_value=["claude-opus-4"]
        ) as live:
            with patch("hermes_cli.models._get_model_config_dict", return_value={}):
                ids = cached_provider_model_ids("anthropic")

        assert live.call_count >= 1, (
            "Live fetch not called — stale poisoned entry was returned as a hit."
        )
        assert all("qwen" not in i and "deepseek" not in i for i in ids), (
            f"Stale poisoned cache returned instead of the live catalog. Got: {ids}"
        )
        assert "claude-opus-4" in ids, (
            f"Live native model missing from result. Got: {ids}"
        )

    def test_already_correct_cache_still_hits(self, tmp_path, monkeypatch):
        """Sanity: a cache entry written through the fix's own logic must
        still hit on a subsequent fetch with the same config — the
        base_url-aware slot key must not break the cache-hit path.

        Rather than hand-seed a slot key (whose exact shape is an
        implementation detail and differs between native and proxied configs),
        we populate the cache via a real fetch and assert the second call is
        a cache hit (only one live fetch)."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))

        cfg = {"provider": "anthropic", "base_url": "https://api.anthropic.com/v1"}
        stub_catalog = ["claude-opus-4", "claude-sonnet-4"]

        def _stub(*, base_url=None, api_key=None, **kwargs):
            return list(stub_catalog)

        with patch("hermes_cli.models._fetch_anthropic_models", side_effect=_stub) as m:
            with patch("hermes_cli.models._get_model_config_dict", return_value=cfg):
                first = cached_provider_model_ids("anthropic")
                second = cached_provider_model_ids("anthropic")

        assert first == stub_catalog, f"First fetch returned wrong catalog: {first}"
        assert second == stub_catalog, f"Second fetch returned wrong catalog: {second}"
        assert m.call_count == 1, (
            f"Live fetch called {m.call_count} times — cache hit broken for "
            f"a stable base_url config."
        )
