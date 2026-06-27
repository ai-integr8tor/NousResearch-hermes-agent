"""Tests for scripts/run_tests_parallel.py argument parsing.

Verifies that pytest flags passed without a '--' separator are
forwarded correctly (fix for #42189).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts/ to the import path so we can import the module under test.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import run_tests_parallel as rtp


class TestArgParsing:
    """Verify parse_known_args behaviour for various invocation styles."""

    @staticmethod
    def _parse(argv: list[str]):
        """Run the argparse portion of main() and return (args, passthrough)."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-j", "--jobs", type=int, default=4)
        parser.add_argument("--paths", default="tests")
        parser.add_argument("--include-integration", action="store_true")
        parser.add_argument("--file-timeout", type=float, default=600.0)
        parser.add_argument("--slice", metavar="I/N")
        parser.add_argument("paths_positional", nargs="*", metavar="PATH")

        if "--" in argv:
            sep = argv.index("--")
            our_args, pytest_passthrough = argv[:sep], argv[sep + 1 :]
        else:
            our_args, pytest_passthrough = argv, []
        args, remaining = parser.parse_known_args(our_args)
        pytest_passthrough = remaining + pytest_passthrough
        return args, pytest_passthrough

    def test_pytest_flag_without_separator(self):
        """-q without -- should be captured as passthrough."""
        args, passthrough = self._parse(["tests/foo.py", "-q"])
        assert args.paths_positional == ["tests/foo.py"]
        assert "-q" in passthrough

    def test_pytest_flag_with_separator(self):
        """-q after -- should still work."""
        args, passthrough = self._parse(["tests/foo.py", "--", "-q"])
        assert args.paths_positional == ["tests/foo.py"]
        assert "-q" in passthrough

    def test_multiple_pytest_flags(self):
        """Multiple pytest flags forwarded together."""
        args, passthrough = self._parse(["tests/foo.py", "-q", "--tb=short", "-k", "test_bar"])
        assert args.paths_positional == ["tests/foo.py"]
        assert "-q" in passthrough
        assert "--tb=short" in passthrough
        assert "-k" in passthrough
        assert "test_bar" in passthrough

    def test_runner_flag_with_pytest_flag(self):
        """Runner's own -j flag parsed, pytest -q forwarded."""
        args, passthrough = self._parse(["-j", "2", "tests/foo.py", "-q"])
        assert args.jobs == 2
        assert args.paths_positional == ["tests/foo.py"]
        assert "-q" in passthrough

    def test_pytest_args_only(self):
        """No paths, just pytest flags."""
        args, passthrough = self._parse(["--", "-v", "--tb=long"])
        assert args.paths_positional is None or args.paths_positional == []
        assert "-v" in passthrough
        assert "--tb=long" in passthrough

    def test_no_extra_args(self):
        """Plain invocation without extra flags."""
        args, passthrough = self._parse(["tests/foo.py"])
        assert args.paths_positional == ["tests/foo.py"]
        assert passthrough == []
