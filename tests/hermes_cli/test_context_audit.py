import json

from hermes_cli.context_audit import measure_context_budget, render_context_audit


def test_context_audit_reports_cwd_context_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    text = "x" * 21000
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")

    data = measure_context_budget(cwd=tmp_path, platform="cli")

    assert data["cwd"] == str(tmp_path.resolve())
    assert data["context_files"][0]["path"] == str((tmp_path / "AGENTS.md").resolve())
    assert data["context_files"][0]["over_default_limit"] is True

    rendered = render_context_audit(data)
    assert "Context audit" in rendered
    assert "AGENTS.md" in rendered
    assert "OVER-CAP" in rendered


def test_context_audit_payload_is_json_serializable(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    (tmp_path / "AGENTS.md").write_text("small context", encoding="utf-8")

    data = measure_context_budget(cwd=tmp_path, platform="cli")

    encoded = json.dumps(data, ensure_ascii=False)
    assert "small context" not in encoded
    assert str((tmp_path / "AGENTS.md").resolve()) in encoded
