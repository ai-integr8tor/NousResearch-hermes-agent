"""Tests for PR 2: multi-source fallback chain and search_engine parameter."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest


class TestGetFallbackChain:
    """_get_fallback_chain() produces ordered, deduplicated chain."""

    def test_empty_config_returns_all_providers(self):
        """No config → chain should include all registered providers."""
        from tools.web_tools import _get_fallback_chain
        with patch("tools.web_tools._load_web_config") as mock_cfg:
            mock_cfg.return_value = {}
            chain = _get_fallback_chain()
            assert len(chain) > 0
            # All entries should be unique
            assert len(chain) == len(set(chain))

    def test_explicit_backend_first(self):
        """web.backend should be first element."""
        from tools.web_tools import _get_fallback_chain
        with patch("tools.web_tools._load_web_config") as mock_cfg:
            mock_cfg.return_value = {"backend": "ddgs"}
            chain = _get_fallback_chain()
            assert chain[0] == "ddgs"

    def test_fallback_backends_respected(self):
        """web.fallback_backends controls ordering."""
        from tools.web_tools import _get_fallback_chain
        with patch("tools.web_tools._load_web_config") as mock_cfg:
            mock_cfg.return_value = {"fallback_backends": ["serper", "baidu", "ddgs"]}
            chain = _get_fallback_chain()
            # serper, baidu, ddgs must appear in that order
            positions = {name: chain.index(name) for name in ["serper", "baidu", "ddgs"] if name in chain}
            assert positions["serper"] < positions["baidu"]
            assert positions["baidu"] < positions["ddgs"]

    def test_string_fallback_parsed(self):
        """String fallback_backends should be comma-split."""
        from tools.web_tools import _get_fallback_chain
        with patch("tools.web_tools._load_web_config") as mock_cfg:
            mock_cfg.return_value = {"fallback_backends": "brave-free, ddgs"}
            chain = _get_fallback_chain()
            assert chain[0] == "brave-free"
            assert chain[1] == "ddgs"


class TestSearchWithFallback:
    """_search_with_fallback() stops at first success, skips failures."""

    def test_first_success_returns_immediately(self):
        from tools.web_tools import _search_with_fallback

        chain = ["backend-a", "backend-b"]
        results_stack = [
            {"success": True, "data": {"web": [{"title": "hit"}]}},
        ]
        with patch("tools.web_tools.get_provider") as mock_gp:
            mock_provider = MagicMock()
            mock_provider.is_available.return_value = True
            mock_provider.supports_search.return_value = True
            mock_provider.search.side_effect = lambda *a, **kw: results_stack.pop(0) if results_stack else None
            mock_gp.return_value = mock_provider
            result, errors = _search_with_fallback("test", 5, chain)
            assert result is not None
            assert result["success"] is True
            # Should only call search once (first provider succeeds)
            assert mock_provider.search.call_count == 1

    def test_skip_unavailable_provider(self):
        from tools.web_tools import _search_with_fallback

        chain = ["unavailable", "good"]
        with patch("tools.web_tools.get_provider") as mock_gp:
            mock_unavail = MagicMock()
            mock_unavail.is_available.return_value = False
            mock_unavail.supports_search.return_value = True

            mock_good = MagicMock()
            mock_good.is_available.return_value = True
            mock_good.supports_search.return_value = True
            mock_good.search.return_value = {"success": True, "data": {"web": [{"title": "x"}]}}

            mock_gp.side_effect = lambda name: mock_unavail if name == "unavailable" else mock_good
            result, errors = _search_with_fallback("test", 5, chain)
            assert result is not None
            assert result["success"] is True
            assert "unavailable: not available" in errors[0]

    def test_skip_zero_results(self):
        from tools.web_tools import _search_with_fallback

        chain = ["empty", "good"]
        with patch("tools.web_tools.get_provider") as mock_gp:
            mock_empty = MagicMock()
            mock_empty.is_available.return_value = True
            mock_empty.supports_search.return_value = True
            mock_empty.search.return_value = {"success": True, "data": {"web": []}}

            mock_good = MagicMock()
            mock_good.is_available.return_value = True
            mock_good.supports_search.return_value = True
            mock_good.search.return_value = {"success": True, "data": {"web": [{"title": "x"}]}}

            mock_gp.side_effect = lambda name: mock_empty if name == "empty" else mock_good
            result, errors = _search_with_fallback("test", 5, chain)
            assert result is not None
            assert result["success"] is True
            assert "empty: returned 0 results" in errors[0]

    def test_all_fail_returns_none(self):
        from tools.web_tools import _search_with_fallback

        chain = ["fail-a", "fail-b"]
        with patch("tools.web_tools.get_provider") as mock_gp:
            mock_provider = MagicMock()
            mock_provider.is_available.return_value = True
            mock_provider.supports_search.return_value = True
            mock_provider.search.return_value = {"success": False, "error": "test-error"}
            mock_gp.return_value = mock_provider
            result, errors = _search_with_fallback("test", 5, chain)
            assert result is None
            assert len(errors) == 2

    def test_provider_crash_skipped(self):
        from tools.web_tools import _search_with_fallback

        chain = ["crasher", "good"]
        with patch("tools.web_tools.get_provider") as mock_gp:
            mock_bad = MagicMock()
            mock_bad.is_available.return_value = True
            mock_bad.supports_search.return_value = True
            mock_bad.search.side_effect = RuntimeError("boom")

            mock_good = MagicMock()
            mock_good.is_available.return_value = True
            mock_good.supports_search.return_value = True
            mock_good.search.return_value = {"success": True, "data": {"web": [{"title": "x"}]}}

            mock_gp.side_effect = lambda name: mock_bad if name == "crasher" else mock_good
            result, errors = _search_with_fallback("test", 5, chain)
            assert result is not None
            assert "crasher: boom" in errors[0]

    def test_provider_not_found_skipped(self):
        from tools.web_tools import _search_with_fallback

        chain = ["nonexistent", "good"]
        with patch("tools.web_tools.get_provider") as mock_gp:
            mock_good = MagicMock()
            mock_good.is_available.return_value = True
            mock_good.supports_search.return_value = True
            mock_good.search.return_value = {"success": True, "data": {"web": [{"title": "x"}]}}
            mock_gp.side_effect = lambda name: None if name == "nonexistent" else mock_good
            result, errors = _search_with_fallback("test", 5, chain)
            assert result is not None
            assert "nonexistent: not found" in errors[0]


class TestGetValidEngineNames:
    """_get_valid_engine_names() returns dynamically updated set."""

    def test_returns_non_empty_set(self):
        from tools.web_tools import _get_valid_engine_names
        names = _get_valid_engine_names()
        assert isinstance(names, set)
        assert len(names) > 0

    def test_includes_existing_backends(self):
        from tools.web_tools import _get_valid_engine_names
        names = _get_valid_engine_names()
        assert "firecrawl" in names
        assert "ddgs" in names


class TestGetRegisteredBackendNames:
    """_get_registered_backend_names() is used for config validation."""

    def test_no_hardcoded_set_in_source(self):
        """Verify no hardcoded backend set remains in web_tools.py."""
        import tools.web_tools
        with open(tools.web_tools.__file__) as f:
            source = f.read()
        assert "configured in _get_registered_backend_names()" in source
        assert 'configured in {"parallel", "firecrawl"' not in source
        assert 'configured in {"exa", "parallel", "firecrawl"' not in source
