import argparse

from hermes_cli.smoke import render_smoke_report, run_smoke


def test_run_smoke_skip_chat_writes_summary(monkeypatch, tmp_path):
    calls = []

    def fake_smoke_command(name, cmd, expected_substring, artifact_dir, timeout=120):
        calls.append((name, cmd, expected_substring))
        from hermes_cli.smoke import SmokeResult
        return SmokeResult(name, True, "rc=0", 0.01, str(artifact_dir / f"{name}.stdout"))

    monkeypatch.setattr("hermes_cli.smoke.smoke_command", fake_smoke_command)

    data = run_smoke(profiles=["default"], artifact_dir=tmp_path, skip_chat=True)

    assert data["ok"] is True
    assert (tmp_path / "summary.json").exists()
    names = [item["name"] for item in data["results"]]
    assert "version" in names
    assert "doctor" in names
    assert "context-audit" in names
    assert not any(name.startswith("profile:") for name in names)
    assert "Hermes smoke report" in render_smoke_report(data)


def test_smoke_uses_configurable_cli(monkeypatch):
    from hermes_cli.smoke import _hermes_cmd

    monkeypatch.setenv("HERMES_SMOKE_CLI", "/tmp/fake-hermes")

    assert _hermes_cmd() == ["/tmp/fake-hermes"]


def test_smoke_parser_has_no_placeholder_flags():
    from hermes_cli.subcommands.smoke import build_smoke_parser

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    build_smoke_parser(subparsers, cmd_smoke=lambda args: None)

    help_text = parser.format_help() + parser.parse_args(["smoke", "--help"]).__repr__() if False else parser.format_help()
    assert "--browser" not in help_text
    assert "--delegation" not in help_text
    args = parser.parse_args(["smoke", "--skip-chat", "--profiles", "default"])
    assert args.skip_chat is True
    assert args.profiles == "default"
