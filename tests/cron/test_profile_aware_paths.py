"""Regression tests for #48649 — cron jobs + skill resolution must honor the
active profile HOME, not the import-time default.

Root cause: ``cron/jobs.py`` and ``tools/skills_tool.py`` froze their path
globals (``JOBS_FILE``/``CRON_DIR``/``OUTPUT_DIR`` and ``SKILLS_DIR``) at import
time from ``get_hermes_home()``. When a profile is applied in-session via the
``_HERMES_HOME_OVERRIDE`` ContextVar (set AFTER those modules import), the frozen
globals still pointed at the default home, so a profile session's ``cronjob``
tool wrote to the global cron dir and the scheduler resolved skills from the
global skills dir (profile skills silently skipped).

These tests assert the path globals resolve DYNAMICALLY against the current
``get_hermes_home()`` so an override is honored, while remaining byte-identical
to the platform default when no override is active.
"""

import importlib

import pytest

import hermes_constants


@pytest.fixture(autouse=True)
def _clear_path_attribute_pollution():
    """Strip any real CRON_DIR/JOBS_FILE/OUTPUT_DIR/SKILLS_DIR/HERMES_HOME module
    attributes left behind by other tests' monkeypatching.

    Those names are normally served dynamically via module ``__getattr__`` (PEP
    562). ``monkeypatch.setattr`` on a dynamic name captures the resolved value
    and, on teardown, restores it as a REAL attribute — which then shadows the
    dynamic resolution for every later test in the same process. We delete the
    shadow before and after each test here so these tests observe the real
    dynamic behavior regardless of suite ordering.
    """
    from cron import jobs as cron_jobs
    from tools import skills_tool

    def _strip():
        for mod, names in (
            (cron_jobs, ("CRON_DIR", "JOBS_FILE", "OUTPUT_DIR", "HERMES_DIR")),
            (skills_tool, ("SKILLS_DIR", "HERMES_HOME")),
        ):
            for n in names:
                if n in vars(mod):
                    delattr(mod, n)

    _strip()
    yield
    _strip()


@pytest.fixture()
def profile_home(tmp_path, monkeypatch):
    """A tmp profile home with cron/ and skills/ dirs, applied via the override."""
    home = tmp_path / ".hermes" / "profiles" / "worker_alpha"
    (home / "cron").mkdir(parents=True, exist_ok=True)
    (home / "skills").mkdir(parents=True, exist_ok=True)
    # Ensure no stray env var interferes with the ContextVar-override path.
    monkeypatch.delenv("HERMES_HOME", raising=False)
    return home


def _set_override(home):
    """Apply the profile HOME via the public ContextVar override seam."""
    return hermes_constants.set_hermes_home_override(str(home))


def _reset_override(token):
    hermes_constants.reset_hermes_home_override(token)


# ---------------------------------------------------------------------------
# cron/jobs.py — path globals must track the override
# ---------------------------------------------------------------------------


def test_cron_jobs_paths_follow_profile_override(profile_home):
    from cron import jobs as cron_jobs

    token = _set_override(profile_home)
    try:
        assert cron_jobs.CRON_DIR == profile_home / "cron"
        assert cron_jobs.JOBS_FILE == profile_home / "cron" / "jobs.json"
        assert cron_jobs.OUTPUT_DIR == profile_home / "cron" / "output"
    finally:
        _reset_override(token)


def test_create_job_writes_to_profile_cron_dir(profile_home, tmp_path):
    from cron import jobs as cron_jobs

    default_jobs = tmp_path / "default-jobs-should-not-exist.json"
    token = _set_override(profile_home)
    try:
        cron_jobs.create_job(prompt="profile scan", schedule="every 1h", name="alpha")
    finally:
        _reset_override(token)

    # Job landed in the profile's cron dir, not the default home.
    profile_jobs = profile_home / "cron" / "jobs.json"
    assert profile_jobs.exists(), "create_job did not write to the profile cron dir"
    assert not default_jobs.exists()


def test_cron_jobs_paths_default_when_no_override(monkeypatch, tmp_path):
    """No override + no env var → resolves to the platform default home (no change)."""
    from cron import jobs as cron_jobs

    monkeypatch.delenv("HERMES_HOME", raising=False)
    expected = hermes_constants.get_hermes_home() / "cron" / "jobs.json"
    assert cron_jobs.JOBS_FILE == expected


# ---------------------------------------------------------------------------
# tools/skills_tool.py — SKILLS_DIR must track the override
# ---------------------------------------------------------------------------


def test_skills_dir_follows_profile_override(profile_home):
    from tools import skills_tool

    token = _set_override(profile_home)
    try:
        assert skills_tool.SKILLS_DIR == profile_home / "skills"
    finally:
        _reset_override(token)


def test_skill_view_resolves_profile_skill(profile_home):
    """A skill that exists ONLY in the profile is found when the override is active."""
    import json

    from tools import skills_tool

    skill_dir = profile_home / "skills" / "demo" / "profile-only-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: profile-only-skill\ndescription: present only in the profile\n---\n\nBody.\n",
        encoding="utf-8",
    )

    token = _set_override(profile_home)
    try:
        result = json.loads(skills_tool.skill_view("profile-only-skill"))
    finally:
        _reset_override(token)

    assert result.get("success") is True, f"profile skill not resolved: {result.get('error')}"
    assert result.get("name") == "profile-only-skill"


def test_skills_dir_default_when_no_override(monkeypatch):
    from tools import skills_tool

    monkeypatch.delenv("HERMES_HOME", raising=False)
    expected = hermes_constants.get_hermes_home() / "skills"
    assert skills_tool.SKILLS_DIR == expected
