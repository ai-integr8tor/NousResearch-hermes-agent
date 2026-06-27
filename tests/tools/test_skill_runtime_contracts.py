from __future__ import annotations

import json

from tools.skill_runtime_contracts import (
    blocking_skill_runtime_references,
    find_skill_runtime_references,
)


def test_finds_wrapper_skill_reference(tmp_path):
    hermes_home = tmp_path / ".hermes"
    bin_dir = hermes_home / "bin"
    bin_dir.mkdir(parents=True)
    wrapper = bin_dir / "run_daily.sh"
    wrapper.write_text("hermes chat -s legacy-skill 'run brief'\n", encoding="utf-8")

    refs = find_skill_runtime_references("legacy-skill", hermes_home=hermes_home)

    assert len(refs) == 1
    assert refs[0].surface == "hermes.bin"
    assert refs[0].path == str(wrapper)
    assert refs[0].line == 1
    assert refs[0].auto_migratable is False


def test_does_not_match_skill_name_as_substring(tmp_path):
    hermes_home = tmp_path / ".hermes"
    bin_dir = hermes_home / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "run_daily.sh").write_text(
        "hermes chat -s legacy-skill-v2 'run brief'\n",
        encoding="utf-8",
    )

    assert find_skill_runtime_references("legacy-skill", hermes_home=hermes_home) == []


def test_cron_references_are_reported_as_auto_migratable(tmp_path):
    hermes_home = tmp_path / ".hermes"
    cron_dir = hermes_home / "cron"
    cron_dir.mkdir(parents=True)
    (cron_dir / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "job-1",
                        "name": "daily",
                        "skills": ["legacy-skill"],
                        "skill": "legacy-skill",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    refs = find_skill_runtime_references("legacy-skill", hermes_home=hermes_home)

    assert len(refs) == 1
    assert refs[0].surface == "cron.jobs"
    assert refs[0].auto_migratable is True
    assert blocking_skill_runtime_references("legacy-skill", hermes_home=hermes_home) == []
