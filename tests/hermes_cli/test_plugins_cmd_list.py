import argparse
import json

from hermes_cli import plugins_cmd


def _args(**kwargs):
    defaults = {
        "enabled": False,
        "user": False,
        "no_bundled": False,
        "plain": False,
        "json": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_filter_plugin_entries_enabled_only():
    entries = [
        ("disk-cleanup", "2.0.0", "Bundled", "bundled", None, "disk-cleanup"),
        ("web-search-plus", "2.2.0", "Search", "git", None, "web-search-plus"),
        ("old-plugin", "1.0.0", "Old", "user", None, "old-plugin"),
    ]

    filtered = plugins_cmd._filter_plugin_entries(
        entries,
        _args(enabled=True),
        enabled={"disk-cleanup", "web-search-plus"},
        disabled={"old-plugin"},
    )

    assert [entry[0] for entry in filtered] == ["disk-cleanup", "web-search-plus"]


def test_filter_plugin_entries_no_bundled():
    entries = [
        ("disk-cleanup", "2.0.0", "Bundled", "bundled", None, "disk-cleanup"),
        ("drawthings-grpc", "0.3.0", "Draw Things", "user", None, "drawthings-grpc"),
        ("web-search-plus", "2.2.0", "Search", "git", None, "web-search-plus"),
    ]

    filtered = plugins_cmd._filter_plugin_entries(
        entries,
        _args(no_bundled=True),
        enabled=set(),
        disabled=set(),
    )

    assert [entry[0] for entry in filtered] == ["drawthings-grpc", "web-search-plus"]


def test_cmd_list_plain_compact_output(monkeypatch, capsys):
    entries = [
        ("disk-cleanup", "2.0.0", "Bundled", "bundled", None, "disk-cleanup"),
        ("web-search-plus", "2.2.0", "Search", "git", None, "web-search-plus"),
    ]
    monkeypatch.setattr(plugins_cmd, "_discover_all_plugins", lambda: entries)
    monkeypatch.setattr(plugins_cmd, "_get_enabled_set", lambda: {"web-search-plus"})
    monkeypatch.setattr(plugins_cmd, "_get_disabled_set", lambda: set())

    plugins_cmd.cmd_list(_args(plain=True, no_bundled=True))

    out = capsys.readouterr().out
    assert "web-search-plus" in out
    assert "enabled" in out
    assert "disk-cleanup" not in out
    assert "Search" not in out  # plain mode stays compact, no descriptions


def test_cmd_list_json_output(monkeypatch, capsys):
    entries = [("web-search-plus", "2.2.0", "Search", "git", None, "web-search-plus")]
    monkeypatch.setattr(plugins_cmd, "_discover_all_plugins", lambda: entries)
    monkeypatch.setattr(plugins_cmd, "_get_enabled_set", lambda: {"web-search-plus"})
    monkeypatch.setattr(plugins_cmd, "_get_disabled_set", lambda: set())

    plugins_cmd.cmd_list(_args(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "name": "web-search-plus",
            "status": "enabled",
            "version": "2.2.0",
            "description": "Search",
            "source": "git",
        }
    ]


def test_discover_all_plugins_includes_entrypoints(monkeypatch):
    """Verify that _discover_all_plugins finds entry-point plugins via importlib."""
    from unittest.mock import MagicMock
    from pathlib import Path

    fake_ep = MagicMock()
    fake_ep.name = "my-pip-plugin"
    fake_ep.value = "my_pip_plugin:register"
    fake_ep.group = "hermes_agent.plugins"
    fake_ep.dist.version = "1.2.3"
    fake_ep.dist.metadata = {"Summary": "A test pip plugin"}

    class FakeSelectableGroups:
        def select(self, group):
            if group == "hermes_agent.plugins":
                return [fake_ep]
            return []

    # Mock importlib.metadata.entry_points
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: FakeSelectableGroups())

    # Mock directory scanning to be empty
    monkeypatch.setattr(plugins_cmd, "_scan_level", lambda *a, **kw: None)

    plugins = plugins_cmd._discover_all_plugins()
    assert len(plugins) == 1
    name, version, description, source, path, key = plugins[0]
    assert name == "my-pip-plugin"
    assert version == "1.2.3"
    assert description == "A test pip plugin"
    assert source == "pip"

