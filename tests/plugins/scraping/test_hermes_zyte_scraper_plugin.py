"""Tests for the bundled scraping/hermes-zyte-scraper plugin."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hermes_cli.config import OPTIONAL_ENV_VARS


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_DIR = REPO_ROOT / "plugins" / "scraping" / "hermes-zyte-scraper"


class TestManifest:
    def test_plugin_directory_exists(self):
        assert PLUGIN_DIR.is_dir()
        assert (PLUGIN_DIR / "plugin.yaml").exists()
        assert (PLUGIN_DIR / "__init__.py").exists()

    def test_manifest_fields(self):
        data = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
        assert data["name"] == "hermes-zyte-scraper"
        assert data["version"]
        assert data["kind"] == "standalone"
        env_names = [
            e["name"] if isinstance(e, dict) else e
            for e in data["requires_env"]
        ]
        assert "ZYTE_API_KEY" in env_names
        assert "SCRAPY_CLOUD_API_KEY" in env_names
        tools = data["provides_tools"]
        assert "zyte_extract" in tools
        assert "zyte_schedule" in tools


class TestEnvRegistry:
    def test_zyte_keys_in_optional_env_vars(self):
        for key in (
            "ZYTE_API_KEY",
            "SCRAPY_CLOUD_API_KEY",
            "SCRAPY_CLOUD_PROJECT_ID",
        ):
            assert key in OPTIONAL_ENV_VARS, f"{key} missing from OPTIONAL_ENV_VARS"
            assert OPTIONAL_ENV_VARS[key]["password"] is (
                key != "SCRAPY_CLOUD_PROJECT_ID"
            )
            assert "zyte" in str(OPTIONAL_ENV_VARS[key]["tools"]).lower() or key.endswith(
                "_PROJECT_ID"
            )


class TestDiscovery:
    def test_plugin_is_discovered_as_standalone_opt_in(self, tmp_path, monkeypatch):
        from hermes_cli import plugins as plugins_mod

        home = tmp_path / ".hermes"
        home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(home))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        manager = plugins_mod.PluginManager()
        manager.discover_and_load()

        loaded = manager._plugins.get("scraping/hermes-zyte-scraper")
        assert loaded is not None, "plugin not discovered"
        assert loaded.enabled is False
        assert "not enabled" in (loaded.error or "").lower()
