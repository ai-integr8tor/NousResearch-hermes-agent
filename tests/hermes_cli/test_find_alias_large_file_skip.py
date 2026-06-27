"""Regression: find_alias_for_profile must skip large files in the wrapper dir.

Pre-fix it read/decoded every extensionless file in ~/.local/bin (including
huge binaries like `claude`, `gh`, `agy`) just to resolve a profile alias.
On the dashboard that ran synchronously on the asyncio event loop and starved
WebSocket delivery, timing out the Hermes Desktop ("loop stalled >10s").
"""
from hermes_cli import profiles


def test_find_alias_skips_large_files(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "_get_wrapper_dir", lambda: tmp_path)
    # A real, tiny wrapper for profile "cato".
    (tmp_path / "cato").write_text('#!/bin/sh\nexec hermes -p cato "$@"\n')
    # A large extensionless file that also contains the needle and sorts first.
    # Pre-fix: read in full and wins as a bogus alias. Post-fix: skipped (>4 KiB).
    (tmp_path / "aaa_big").write_text("x" * 200_000 + '\nexec hermes -p cato\n')
    assert profiles.find_alias_for_profile("cato") == "cato"
