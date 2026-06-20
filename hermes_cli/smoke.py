"""Runtime smoke diagnostics for ``hermes smoke``.

The command is intentionally conservative: it writes artifacts under /tmp,
prints a compact report, and does not mutate Hermes config/gateway/cron state.
Profile chat smokes are real CLI calls because configuration-only checks cannot
prove provider/auth/runtime usability.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class SmokeResult:
    name: str
    ok: bool
    detail: str
    elapsed_s: float | None = None
    artifact: str | None = None


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _hermes_cmd() -> List[str]:
    """Return the production Hermes CLI command, with a source-tree fallback."""
    explicit = os.environ.get("HERMES_SMOKE_CLI")
    if explicit:
        return [explicit]
    installed = shutil.which("hermes")
    if installed:
        return [installed]
    return [sys.executable, "-m", "hermes_cli.main"]


def _run(cmd: List[str], timeout: int = 120, env: dict[str, str] | None = None) -> tuple[int, str, str, float]:
    start = time.monotonic()
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)
    return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - start


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def smoke_profile(profile: str, artifact_dir: Path, timeout: int = 180) -> SmokeResult:
    expected = f"SMOKE_{profile}_OK"
    cmd = [
        *_hermes_cmd(),
        "--profile",
        profile,
        "chat",
        "-Q",
        "--max-turns",
        "1",
        "--source",
        "smoke",
        "-q",
        f"Antworte exakt: {expected}",
    ]
    safe_profile = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in profile)
    out_path = artifact_dir / f"profile-{safe_profile}.stdout"
    err_path = artifact_dir / f"profile-{safe_profile}.stderr"
    try:
        rc, out, err, elapsed = _run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _write(out_path, _timeout_text(exc.stdout))
        _write(err_path, _timeout_text(exc.stderr))
        return SmokeResult(f"profile:{profile}", False, f"timeout after {timeout}s", None, str(out_path))
    _write(out_path, out)
    _write(err_path, err)
    got = " ".join(out.split())
    ok = rc == 0 and got == expected
    detail = f"rc={rc}; stdout={got[:120]!r}"
    if not ok and expected in got:
        detail += "; expected token present but output not exact"
    return SmokeResult(f"profile:{profile}", ok, detail, elapsed, str(out_path))


def smoke_command(name: str, cmd: List[str], expected_substring: str | None, artifact_dir: Path, timeout: int = 120) -> SmokeResult:
    out_path = artifact_dir / f"{name}.stdout"
    err_path = artifact_dir / f"{name}.stderr"
    try:
        rc, out, err, elapsed = _run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _write(out_path, _timeout_text(exc.stdout))
        _write(err_path, _timeout_text(exc.stderr))
        return SmokeResult(name, False, f"timeout after {timeout}s", None, str(out_path))
    _write(out_path, out)
    _write(err_path, err)
    combined = out + err
    ok = rc == 0 and (expected_substring is None or expected_substring in combined)
    return SmokeResult(name, ok, f"rc={rc}", elapsed, str(out_path))


def _openrouter_credits() -> SmokeResult:
    try:
        from hermes_cli.config import get_env_value
        import urllib.request

        key = get_env_value("OPENROUTER_API_KEY") or ""
        if not key:
            return SmokeResult("openrouter-credits", False, "OPENROUTER_API_KEY missing")
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {key}", "User-Agent": "hermes-smoke"},
        )
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed HTTPS endpoint
            data = json.load(resp)
        elapsed = time.monotonic() - start
        credits = (data or {}).get("data") or {}
        total = float(credits.get("total_credits") or 0)
        usage = float(credits.get("total_usage") or 0)
        remaining = total - usage
        return SmokeResult("openrouter-credits", True, f"remaining_usd={remaining:.2f}", elapsed)
    except Exception as exc:  # pragma: no cover - network/env dependent
        return SmokeResult("openrouter-credits", False, f"{type(exc).__name__}: {exc}")


def run_smoke(
    profiles: Iterable[str] = ("default", "cheap", "lab"),
    *,
    artifact_dir: str | Path | None = None,
    skip_chat: bool = False,
    include_credits: bool = False,
) -> Dict[str, Any]:
    artifacts = Path(artifact_dir or f"/tmp/hermes-smoke-{_now_stamp()}").expanduser().resolve()
    artifacts.mkdir(parents=True, exist_ok=True)

    results: List[SmokeResult] = []
    base = _hermes_cmd()
    results.append(smoke_command("version", base + ["--version"], "Hermes Agent", artifacts, timeout=60))
    results.append(smoke_command("auth-list", base + ["auth", "list"], None, artifacts, timeout=120))
    results.append(smoke_command("tools-list", base + ["tools", "list"], None, artifacts, timeout=120))
    results.append(smoke_command("doctor", base + ["doctor"], "Hermes Doctor", artifacts, timeout=240))
    results.append(smoke_command("gateway-status", base + ["gateway", "status"], None, artifacts, timeout=120))
    results.append(smoke_command("cron-status", base + ["cron", "status"], None, artifacts, timeout=120))
    results.append(smoke_command("context-audit", base + ["context", "audit", "--cwd", os.getcwd()], "Context audit", artifacts, timeout=120))

    if include_credits:
        results.append(_openrouter_credits())

    if not skip_chat:
        for profile in profiles:
            results.append(smoke_profile(profile, artifacts))

    payload = {
        "artifact_dir": str(artifacts),
        "results": [asdict(r) for r in results],
        "ok": all(r.ok for r in results),
    }
    _write(artifacts / "summary.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def render_smoke_report(data: Dict[str, Any]) -> str:
    lines = ["Hermes smoke report", f"  artifacts: {data['artifact_dir']}", ""]
    for item in data["results"]:
        mark = "OK" if item["ok"] else "FAIL"
        elapsed = "" if item.get("elapsed_s") is None else f" ({item['elapsed_s']:.2f}s)"
        lines.append(f"  {mark:4} {item['name']:<24} {item['detail']}{elapsed}")
    lines.append("")
    lines.append(f"Overall: {'OK' if data['ok'] else 'FAIL'}")
    return "\n".join(lines)


def cmd_smoke(args: Any) -> None:
    profiles_raw = getattr(args, "profiles", "default,cheap,lab") or ""
    profiles = [p.strip() for p in profiles_raw.split(",") if p.strip()]
    data = run_smoke(
        profiles=profiles,
        artifact_dir=getattr(args, "output_dir", None),
        skip_chat=getattr(args, "skip_chat", False),
        include_credits=getattr(args, "credits", False),
    )
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_smoke_report(data))
    raise SystemExit(0 if data["ok"] else 1)
