from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


def test_spawn_hermes_action_uses_noninteractive_sudo_when_requested(monkeypatch, tmp_path):
    import hermes_cli.web_server as web_server

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        proc = MagicMock()
        proc.pid = 12345
        return proc

    monkeypatch.setattr(web_server.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(web_server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(web_server, "_ACTION_LOG_DIR", tmp_path)

    proc = web_server._spawn_hermes_action(
        ["gateway", "restart", "--system"],
        "gateway-restart",
        sudo_if_needed=True,
    )

    assert proc.pid == 12345
    assert captured["cmd"][:2] == ["sudo", "-n"]
    assert captured["cmd"][2:5] == [web_server.sys.executable, "-m", "hermes_cli.main"]
    assert captured["cmd"][-3:] == ["gateway", "restart", "--system"]
    assert captured["kwargs"]["stdin"] is web_server.subprocess.DEVNULL
    assert captured["kwargs"]["env"]["HERMES_NONINTERACTIVE"] == "1"


def test_spawn_hermes_action_does_not_sudo_when_root(monkeypatch, tmp_path):
    import hermes_cli.web_server as web_server

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        proc = MagicMock()
        proc.pid = 12345
        return proc

    monkeypatch.setattr(web_server.os, "geteuid", lambda: 0)
    monkeypatch.setattr(web_server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(web_server, "_ACTION_LOG_DIR", tmp_path)

    web_server._spawn_hermes_action(
        ["gateway", "restart", "--system"],
        "gateway-restart",
        sudo_if_needed=True,
    )

    assert captured["cmd"][:3] == [web_server.sys.executable, "-m", "hermes_cli.main"]
    assert "sudo" not in captured["cmd"]


def test_restart_gateway_uses_system_scope_when_system_unit_exists(monkeypatch, tmp_path):
    import hermes_cli.web_server as web_server

    calls: list[tuple[list[str], str, bool]] = []

    class FakePath:
        def exists(self):
            return True

    def fake_get_systemd_unit_path(*, system=False):
        assert system is True
        return FakePath()

    def fake_spawn(subcommand, name, *, sudo_if_needed=False):
        calls.append((subcommand, name, sudo_if_needed))
        proc = MagicMock()
        proc.pid = 67890
        return proc

    monkeypatch.setattr(web_server, "_spawn_hermes_action", fake_spawn)
    monkeypatch.setattr("hermes_cli.gateway.get_systemd_unit_path", fake_get_systemd_unit_path)

    import anyio

    response = anyio.run(web_server.restart_gateway)

    assert response["ok"] is True
    assert response["pid"] == 67890
    assert calls == [(["gateway", "restart", "--system"], "gateway-restart", True)]


def test_restart_gateway_uses_user_scope_without_system_unit(monkeypatch):
    import hermes_cli.web_server as web_server

    calls: list[tuple[list[str], str, bool]] = []

    class FakePath:
        def exists(self):
            return False

    monkeypatch.setattr(
        "hermes_cli.gateway.get_systemd_unit_path",
        lambda *, system=False: FakePath(),
    )

    def fake_spawn(subcommand, name, *, sudo_if_needed=False):
        calls.append((subcommand, name, sudo_if_needed))
        proc = MagicMock()
        proc.pid = 13579
        return proc

    monkeypatch.setattr(web_server, "_spawn_hermes_action", fake_spawn)

    import anyio

    response = anyio.run(web_server.restart_gateway)

    assert response["ok"] is True
    assert response["pid"] == 13579
    assert calls == [(["gateway", "restart"], "gateway-restart", False)]
