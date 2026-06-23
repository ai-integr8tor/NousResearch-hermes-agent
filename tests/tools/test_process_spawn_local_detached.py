"""Regression tests for terminal(background=true) child-process survival.

The bug: a long-lived process spawned via :meth:`ProcessRegistry.spawn_local`
(the local backend of the agent's ``terminal(background=true)``) gets killed
within 30-60s when the parent's Windows job object is reaped — because
``spawn_local`` was passing only ``CREATE_NO_WINDOW`` to ``subprocess.Popen``
and the child stayed in the parent's job.  On Windows, the parent process
(e.g. ``hermes.exe`` invoked from a shell, from the Desktop GUI's bootstrap,
or from a Tauri/Electron-spawned child) routinely participates in a job
object that gets torn down on parent lifecycle events, taking the
"background" child with it.

The fix: use :func:`hermes_cli._subprocess_compat.windows_detach_popen_kwargs`
instead of ``windows_hide_flags``.  That helper returns
``{creationflags: CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS |
CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB}`` on Windows and
``{start_new_session: True}`` on POSIX — the cross-platform patterns that
keep the child alive past parent cleanup.  ``CREATE_BREAKAWAY_FROM_JOB``
(0x01000000) is the flag that actually does the work on Windows:
without it, even with ``DETACHED_PROCESS`` the child is still a member
of the parent's job at birth and dies when the job is reaped.

The other local spawn sites (``hermes_cli/gateway.py``, ``gateway/run.py``,
``gateway/slash_commands.py``) were already using this helper.  This
regression guard ensures ``process_registry.spawn_local`` doesn't fall
back to the unsafe-on-Windows ``windows_hide_flags`` again.

Skip on non-Windows: the failure mode is a Windows job-object cleanup
bug.  POSIX uses ``start_new_session=True`` which is the OS-correct
equivalent.  The static signature check still runs everywhere so a
regression that reverts the helper call is caught on Linux CI too.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import pytest

_IS_WINDOWS = platform.system() == "Windows"

# ``tests/conftest.py`` already adds the project root to ``sys.path`` for
# every test in the suite, so the ``from tools.process_registry import ...``
# below works without a per-file ``sys.path`` shim.  We keep this comment
# as a breadcrumb in case someone copy-pastes this test file out of the
# tree (e.g. into a worktree without the shared conftest).

from tools.process_registry import ProcessRegistry  # noqa: E402


# =============================================================================
# Static checks (cheap, run on every CI, fail fast)
# =============================================================================


def test_spawn_local_uses_detach_popen_kwargs():
    """``spawn_local`` must use the platform-aware detach helper, not windows_hide_flags.

    This is a static source-text check; it runs on every platform so a
    regression that reverts the helper call is caught on Linux CI too
    (where the integration test below is skipped).  We narrow the
    check to the actual Popen() call inside spawn_local (the
    ``proc = subprocess.Popen(...)`` block) to avoid false positives
    from the explanatory comment we add and from the import line, both
    of which legitimately mention ``windows_hide_flags`` for context.
    """
    root = Path(__file__).resolve().parents[2]
    source = (root / "tools" / "process_registry.py").read_text(encoding="utf-8")
    # Extract spawn_local function body
    start = source.find("def spawn_local")
    assert start != -1, "could not find def spawn_local in process_registry.py"
    end = source.find("\n    def ", start + 1)
    body = source[start:end if end != -1 else start + 200 * 80]

    # Find the Popen(...) call's kwargs block.  We extract the
    # ~10 lines after `proc = subprocess.Popen(` so we look at
    # actual code, not the explanatory comment above it.
    popen_marker = "proc = subprocess.Popen("
    popen_idx = body.find(popen_marker)
    assert popen_idx != -1, "could not find Popen call inside spawn_local"
    popen_block = body[popen_idx : popen_idx + 1500]

    # The Popen kwargs block must include the detach helper (either
    # stored as _popen_kwargs or spread inline).
    assert "**_popen_kwargs" in popen_block, (
        "spawn_local's Popen call must spread the precomputed "
        "_popen_kwargs (which holds the result of "
        "windows_detach_popen_kwargs()) so the child runs in its own "
        "session on both platforms.  Without the spread, the child is "
        "born in the parent's job object and dies when the parent "
        "exits.  This re-introduces the 30-60s child-death bug."
    )
    # The old pattern (windows_hide_flags as the actual call) must not
    # be in the Popen kwargs block.  Match the call form to avoid the
    # comment and import false-positives.
    assert "windows_hide_flags(" not in popen_block, (
        "spawn_local's Popen call still uses windows_hide_flags() — "
        "that hides the console but does NOT detach from the parent's "
        "job.  Replace with windows_detach_popen_kwargs()."
    )


def test_spawn_local_spawn_kwargs_invoke_compat_helper():
    """The Popen() call inside spawn_local must spread the detach helper's kwargs.

    The canonical pattern in the codebase (hermes_cli/gateway.py,
    gateway/run.py, gateway/slash_commands.py) is either::

        _popen_kwargs = windows_detach_popen_kwargs()
        subprocess.Popen(..., **_popen_kwargs)

    or directly::

        subprocess.Popen(..., **windows_detach_popen_kwargs())

    Either is acceptable.  The forbidden pattern is the old
    ``windows_hide_flags()`` (no DETACHED_PROCESS, no BREAKAWAY) or the
    bare ``{}`` on non-Windows (no session detachment at all).
    """
    root = Path(__file__).resolve().parents[2]
    source = (root / "tools" / "process_registry.py").read_text(encoding="utf-8")
    # The Popen call for the non-PTY/PTY-fallback path is the one we patched.
    # Look for the kwargs-spread pattern in the spawn_local function.
    start = source.find("def spawn_local")
    assert start != -1
    end = source.find("\n    def ", start + 1)
    body = source[start:end if end != -1 else start + 200 * 80]
    # Accept either the stored-then-spread or the inline-spread form.
    stored_form = (
        "_popen_kwargs = windows_detach_popen_kwargs()" in body
        and "**_popen_kwargs" in body
    )
    inline_form = "**windows_detach_popen_kwargs()" in body
    assert stored_form or inline_form, (
        "spawn_local's Popen call must spread windows_detach_popen_kwargs() "
        "(either as a stored _popen_kwargs or inline) so the child runs "
        "in its own session on both platforms."
    )


# =============================================================================
# Deterministic integration test (sub-second, environment-independent)
# =============================================================================

# How long the child needs to live for the post-spawn membership check
# to succeed.  We don't need it to survive 60s — just long enough to
# probe its job membership.  1.5s is more than enough on a modern
# machine; bash + Python boot on Windows can take ~1s.
_CHILD_BOOT_SECONDS = 1.5


def _real_python_sleep_marker(seconds: float, marker_path: str) -> str:
    """Return a command that writes a marker file and sleeps for ``seconds``.

    Implementation note: spawn_local wraps the command in
    ``bash -lic "set +m; <command>"`` on Windows (git-bash).  Bash on
    Windows strips backslashes during MSYS path translation, so
    ``C:\\foo\\bar\\python.exe`` arrives at the child as
    ``C:foobarpython.exe`` (no separators, command not found).  Use
    forward slashes for any path inside the command.
    """
    exe_posix = sys.executable.replace("\\", "/")
    marker_posix = marker_path.replace("\\", "/")
    return (
        f"{exe_posix} -c "
        f"\"import time, pathlib; "
        f"pathlib.Path('{marker_posix}').write_text('alive'); "
        f"time.sleep({seconds})\""
    )


@pytest.mark.skipif(not _IS_WINDOWS, reason="Windows job object API is required")
def test_spawn_local_child_breaks_away_from_parent_job(tmp_path):
    """Deterministic regression guard: the child must NOT be in the parent's job.

    Setup:
      1. Create a Windows job object with JOB_OBJECT_LIMIT_BREAKAWAY_OK
         (the parent's "I allow children to escape" flag).
      2. Assign THIS test process to the job.  Now spawn_local's
         children will inherit this job by default.
      3. Call process_registry.spawn_local to spawn a child.
      4. Probe the child's job membership via IsProcessInJob.

    Pre-patch: ``spawn_local`` used ``windows_hide_flags()`` which
    sets only CREATE_NO_WINDOW.  The child is born into the parent's
    job and stays a member.  ``IsProcessInJob`` returns True.
    Test FAILS.

    Post-patch: ``spawn_local`` uses ``windows_detach_popen_kwargs()``
    which includes CREATE_BREAKAWAY_FROM_JOB.  The child breaks out
    of the parent's job at birth.  ``IsProcessInJob`` returns False.
    Test PASSES.

    This test does not depend on whether the parent process is
    itself in a constrained job — we set up the constraint ourselves,
    so the result is deterministic across CI runners, dev machines,
    and the Hermes Desktop GUI's Tauri-spawned processes.
    """
    # Skip cleanly if pywin32 isn't available (it's a Windows-only
    # optional dep that not every dev box has installed).  The test
    # is already gated on _IS_WINDOWS but Linux/macOS runners that
    # happen to have win32api on sys.path should still be able to
    # skip without an ImportError.
    pytest.importorskip("win32api")
    pytest.importorskip("win32job")
    pytest.importorskip("win32process")

    import ctypes
    import ctypes.wintypes as wt
    import win32api
    import win32job
    import win32process

    # Constants from MSDN
    JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
    JobObjectExtendedLimitInformation = 9
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    # Create the job and set the BREAKAWAY_OK limit flag.
    # We use raw ctypes here because the pywin32 dict form for
    # JOBOBJECT_EXTENDED_LIMIT_INFORMATION requires every field
    # to be present (including IO_COUNTERS, ProcessMemoryLimit, etc.)
    # and varies subtly across pywin32 versions.  The raw struct is
    # rock-solid: 144-byte zeroed buffer, write LimitFlags at offset 16.
    _job_obj = win32job.CreateJobObject(None, "")
    # pywin32 stub types declare CreateJobObject as int | None but
    # it always returns a valid HANDLE in practice.  Coerce + assert
    # to keep static analyzers (pyright) happy and fail loudly if
    # the API ever returns None.
    job_h = int(_job_obj) if _job_obj is not None else 0
    assert job_h != 0, "CreateJobObject returned NULL"
    buf = ctypes.create_string_buffer(144)
    ctypes.c_ulong.from_buffer(buf, 16).value = JOB_OBJECT_LIMIT_BREAKAWAY_OK
    kernel32 = ctypes.windll.kernel32
    kernel32.SetInformationJobObject.argtypes = [
        wt.HANDLE, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong
    ]
    kernel32.SetInformationJobObject.restype = wt.BOOL
    ok = kernel32.SetInformationJobObject(
        job_h,
        JobObjectExtendedLimitInformation,
        ctypes.cast(buf, ctypes.c_void_p),
        144,
    )
    assert ok, (
        f"SetInformationJobObject failed with err={ctypes.GetLastError()}. "
        "The test cannot run without being able to set up the job."
    )

    try:
        # Assign this process (the test parent) to the job.
        # Every child this process spawns will inherit the job by
        # default — UNLESS the child uses CREATE_BREAKAWAY_FROM_JOB.
        _our_handle_obj = win32process.GetCurrentProcess()
        our_handle = int(_our_handle_obj) if _our_handle_obj is not None else 0
        assert our_handle != 0, "GetCurrentProcess returned NULL"
        win32job.AssignProcessToJobObject(job_h, our_handle)
        assert win32job.IsProcessInJob(our_handle, job_h), (
            "Could not assign the test process to the job.  The "
            "test cannot simulate the parent-job-membership condition."
        )

        # Spawn a short-lived child via the actual code path under test.
        registry = ProcessRegistry()
        marker = tmp_path / "alive.marker"
        session = registry.spawn_local(
            _real_python_sleep_marker(_CHILD_BOOT_SECONDS, str(marker)),
            cwd=str(tmp_path),
        )

        try:
            # Probe the child's job membership.  This is the load-bearing
            # assertion: the child MUST NOT be in our job if the fix
            # is in effect.
            assert session.pid is not None, "spawn_local returned no pid"
            _child_handle_obj = win32api.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(session.pid)
            )
            assert _child_handle_obj is not None, (
                f"OpenProcess returned NULL for pid {session.pid} — "
                "child may have died between spawn and probe."
            )
            child_handle = int(_child_handle_obj)
            try:
                child_in_job = bool(
                    win32job.IsProcessInJob(child_handle, job_h)
                )
            finally:
                win32api.CloseHandle(child_handle)

            assert child_in_job is False, (
                f"REGRESSION: spawn_local's child (pid={session.pid}) landed "
                f"in the parent's job object.  The fix "
                f"(windows_detach_popen_kwargs with CREATE_BREAKAWAY_FROM_JOB) "
                f"is not in effect.  This is the bug.  Without the breakaway "
                f"flag, the child dies when the parent's job is reaped on "
                f"agent shutdown, gateway restart, or any Tauri/Electron-"
                f"spawned parent's lifecycle event."
            )
        finally:
            # Clean up the child so it doesn't linger past the test.
            try:
                registry.kill_process(session.id)
            except Exception:
                if session.pid is not None:
                    try:
                        subprocess.run(
                            ["taskkill", "/T", "/F", "/PID", str(session.pid)],
                            check=False,
                            capture_output=True,
                        )
                    except Exception:
                        pass
    finally:
        # We did NOT set KILL_ON_JOB_CLOSE on the job, so closing the
        # handle is safe — it just decrements the refcount.  Our
        # process stays a member of the job for the rest of pytest's
        # lifetime, but pytest is exiting soon anyway.
        win32api.CloseHandle(job_h)


# =============================================================================
# End-to-end integration test (60s, slow, may flake on plain shells)
# =============================================================================

# The 60s survival test is the original "symptom-level" regression
# guard.  It catches the bug in real-world conditions (parent in a
# constrained job, parent cleanup triggers death) but ONLY when the
# parent process is itself in such a job.  The deterministic test
# above (test_spawn_local_child_breaks_away_from_parent_job) is the
# load-bearing one.  Keep this as a secondary end-to-end check.
#
# On CI runners where the parent pytest process is in a constrained
# job (e.g. when running under the Hermes Desktop GUI's bootstrap,
# a Tauri/Electron-spawned subprocess, or Windows Terminal with
# default job settings), this test fails pre-patch.  On plain shells
# (git-bash, PowerShell), the parent has no job constraints and the
# test may pass even on unpatched code — that's why the deterministic
# test above is the real guard.

# How long a long-lived process must survive to be considered "fixed".
# The bug kills within 30-60s on Windows. 60s is comfortably past the
# original failure window and short enough for a CI test on a developer
# machine.  Don't lower this without re-running the manual repro.
SURVIVAL_SECONDS = 60


@pytest.mark.skipif(not _IS_WINDOWS, reason="real-process death bug is Windows-specific")
def test_spawn_local_child_survives_60s(tmp_path):
    """A real long-lived child must stay alive for at least 60s.

    End-to-end version of the deterministic test above.  This one
    measures the *symptom* (parent-driven child death within the bug
    window) rather than the *mechanism* (job membership at birth).
    It is the most realistic reproduction of the original failure
    mode but may not reproduce on a plain shell where the parent
    process is not itself in a constrained job.
    """
    registry = ProcessRegistry()
    marker = tmp_path / "alive.marker"
    session = registry.spawn_local(
        _real_python_sleep_alive_marker(SURVIVAL_SECONDS + 5, str(marker)),
        cwd=str(tmp_path),
    )
    try:
        # 1. The child must have actually started and run.
        # The marker is written within ~50ms of Python boot.
        deadline = time.time() + 10
        while time.time() < deadline:
            if marker.exists():
                break
            time.sleep(0.1)
        assert marker.exists(), (
            f"child did not write the alive marker within 10s; "
            f"session.exited={session.exited}, pid={session.pid}"
        )

        # 2. After 60s, the session must still report running.
        time.sleep(SURVIVAL_SECONDS)
        assert session.exited is False, (
            f"session.exited became True after {SURVIVAL_SECONDS}s — the "
            f"child died.  session.exit_code="
            f"{getattr(session, 'exit_code', None)}, pid={session.pid}"
        )

        # 3. The OS process must still be alive.
        if session.pid is not None:
            try:
                os.kill(session.pid, 0)
            except ProcessLookupError:
                pytest.fail(
                    f"OS reports pid {session.pid} no longer exists after "
                    f"{SURVIVAL_SECONDS}s — the child died silently."
                )
            except (PermissionError, OSError):
                # PermissionError can mean "exists but we lack access",
                # which is "alive enough" for this test.
                pass

    finally:
        # Clean up the child so it doesn't linger for 65s after the test
        # completes.  Use the registry's own kill so the session is
        # properly transitioned to "exited" state.
        try:
            registry.kill_process(session.id)
        except Exception:
            if session.pid is not None:
                try:
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(session.pid)],
                        check=False, capture_output=True,
                    )
                except Exception:
                    pass


def _real_python_sleep_alive_marker(seconds: float, marker_path: str) -> str:
    """Return a command that writes a marker file and sleeps for ``seconds``.

    Identical to :func:`_real_python_sleep_marker` but takes an
    explicit ``seconds`` argument; kept for backward compatibility
    with the original 60s-survival test.
    """
    return _real_python_sleep_marker(seconds, marker_path)
