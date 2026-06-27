"""Runtime dependency checks for skill deletion.

Curator can consolidate or prune skills automatically, but deleting a skill is
only safe when runtime entrypoints that invoke Hermes by skill name have either
been migrated or are known to be auto-migratable. This module keeps that check
small and deterministic so it can run before the irreversible filesystem delete.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional

from hermes_constants import get_hermes_home

_MAX_SCAN_BYTES = 1_000_000
_RUNTIME_DIR_NAMES = ("bin", "scripts")
_TEXT_SUFFIXES = {
    "",
    ".bash",
    ".fish",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
    ".zsh",
}
_SECRET_NAMES = {".env", "auth.json", "secrets.json"}


@dataclass(frozen=True)
class SkillRuntimeReference:
    """A runtime surface that still refers to a skill by name."""

    surface: str
    path: str
    line: Optional[int]
    text: str
    auto_migratable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _skill_pattern(skill_name: str) -> re.Pattern[str]:
    escaped = re.escape(skill_name)
    return re.compile(rf"(?<![A-Za-z0-9_.-]){escaped}(?![A-Za-z0-9_.-])")


def _is_text_candidate(path: Path) -> bool:
    if path.name in _SECRET_NAMES:
        return False
    if path.suffix.lower() in _TEXT_SUFFIXES:
        return True
    try:
        return os.access(path, os.X_OK)
    except OSError:
        return False


def _iter_runtime_files(hermes_home: Path) -> Iterable[Path]:
    for dirname in _RUNTIME_DIR_NAMES:
        root = hermes_home / dirname
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            try:
                if (
                    path.is_file()
                    and _is_text_candidate(path)
                    and path.stat().st_size <= _MAX_SCAN_BYTES
                ):
                    yield path
            except OSError:
                continue


def _scan_text_file(
    path: Path,
    pattern: re.Pattern[str],
    surface: str,
) -> List[SkillRuntimeReference]:
    refs: List[SkillRuntimeReference] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return refs

    for line_no, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            refs.append(
                SkillRuntimeReference(
                    surface=surface,
                    path=str(path),
                    line=line_no,
                    text=line.strip()[:240],
                    auto_migratable=False,
                )
            )
    return refs


def _scan_cron_jobs(hermes_home: Path, skill_name: str) -> List[SkillRuntimeReference]:
    jobs_file = hermes_home / "cron" / "jobs.json"
    try:
        if not jobs_file.exists() or jobs_file.stat().st_size > _MAX_SCAN_BYTES:
            return []
    except OSError:
        return []

    try:
        payload = json.loads(jobs_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(jobs, list):
        return []

    refs: List[SkillRuntimeReference] = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            continue
        skills = job.get("skills")
        single_skill = job.get("skill")
        matched = False
        if isinstance(skills, list) and skill_name in skills:
            matched = True
        if single_skill == skill_name:
            matched = True
        if not matched:
            continue
        job_id = job.get("id") or f"index:{index}"
        job_name = job.get("name") or "unnamed"
        refs.append(
            SkillRuntimeReference(
                surface="cron.jobs",
                path=f"{jobs_file}#{job_id}",
                line=None,
                text=f"cron job {job_name!r} references skill {skill_name!r}",
                auto_migratable=True,
            )
        )
    return refs


def find_skill_runtime_references(
    skill_name: str,
    hermes_home: Optional[Path] = None,
) -> List[SkillRuntimeReference]:
    """Find runtime entrypoints that refer to ``skill_name``.

    References in Hermes cron jobs are marked auto-migratable because
    ``cron.jobs.rewrite_skill_refs`` already rewrites those after a curator run.
    Script references under ``bin`` and ``scripts`` are blocking because Hermes
    has no deterministic migrator for arbitrary commands yet.
    """

    home = Path(hermes_home) if hermes_home is not None else get_hermes_home()
    pattern = _skill_pattern(skill_name)
    refs: List[SkillRuntimeReference] = []

    refs.extend(_scan_cron_jobs(home, skill_name))
    for file_path in _iter_runtime_files(home):
        surface = f"hermes.{file_path.parent.name}"
        refs.extend(_scan_text_file(file_path, pattern, surface))

    return refs


def blocking_skill_runtime_references(
    skill_name: str,
    hermes_home: Optional[Path] = None,
) -> List[SkillRuntimeReference]:
    """Return references that deletion cannot safely auto-migrate."""

    return [
        ref
        for ref in find_skill_runtime_references(skill_name, hermes_home=hermes_home)
        if not ref.auto_migratable
    ]
