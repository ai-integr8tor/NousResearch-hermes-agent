"""E2E tests for session<->workspace binding (issue #48190).

Exercises the real SessionDB against a temp HERMES_HOME: schema auto-migration
of the new columns, git remote/branch capture at create, the --workspace filter,
and the workspace_key grouping derivation. No mocks.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, text=True)


def _make_repo(path, remote_url, branch="main"):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@e.local")
    _git(path, "config", "user.name", "t")
    _git(path, "remote", "add", "origin", remote_url)
    (path / "f.txt").write_text("x")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    if branch != "main":
        _git(path, "checkout", "-qb", branch)


class SessionWorkspaceBindingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        os.environ["HERMES_HOME"] = str(self.home)
        # Fresh import of the state module against this HERMES_HOME.
        import importlib
        import hermes_state
        importlib.reload(hermes_state)
        self.hs = hermes_state
        self.db = hermes_state.SessionDB()

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("HERMES_HOME", None)

    def test_columns_migrated(self):
        cols = {r[1] for r in self.db._conn.execute(
            "PRAGMA table_info(sessions)").fetchall()}
        self.assertIn("git_remote", cols)
        self.assertIn("git_branch", cols)
        self.assertIn("cwd", cols)  # pre-existing, still present

    def test_capture_from_git_repo(self):
        repo = self.home / "repoA"
        _make_repo(repo, "https://github.com/owner/repoA.git", branch="feat/x")
        self.db.create_session("s1", "cli", cwd=str(repo))
        row = self.db.get_session("s1")
        # remote normalized: scheme + .git stripped
        self.assertEqual(row["git_remote"], "github.com/owner/repoA")
        self.assertEqual(row["git_branch"], "feat/x")
        # workspace_key prefers the remote
        self.assertEqual(self.hs.workspace_key(row), "github.com/owner/repoA")

    def test_ssh_remote_normalizes_same_as_https(self):
        self.assertEqual(
            self.hs._normalize_git_remote("git@github.com:owner/repo.git"),
            self.hs._normalize_git_remote("https://github.com/owner/repo.git"),
        )
        self.assertEqual(
            self.hs._normalize_git_remote("git@github.com:owner/repo.git"),
            "github.com/owner/repo",
        )

    def test_non_git_dir_falls_back_to_cwd_key(self):
        plain = self.home / "plain"
        plain.mkdir()
        self.db.create_session("s2", "cli", cwd=str(plain))
        row = self.db.get_session("s2")
        self.assertIsNone(row["git_remote"])
        self.assertEqual(self.hs.workspace_key(row), str(plain))

    def test_child_session_not_bound(self):
        repo = self.home / "repoB"
        _make_repo(repo, "https://github.com/owner/repoB.git")
        self.db.create_session("parent", "cli", cwd=str(repo))
        self.db.create_session(
            "child", "cli", cwd=str(repo), parent_session_id="parent")
        child = self.db.get_session("child")
        # child sessions (subagents/compression) must not get workspace identity
        self.assertIsNone(child["git_remote"])
        self.assertIsNone(child["git_branch"])

    def test_workspace_filter(self):
        repo_a = self.home / "wsA"
        repo_b = self.home / "wsB"
        _make_repo(repo_a, "https://github.com/owner/aaa.git")
        _make_repo(repo_b, "https://github.com/owner/bbb.git")
        self.db.create_session("a1", "cli", cwd=str(repo_a))
        self.db.create_session("b1", "cli", cwd=str(repo_b))
        # add a user message so rows surface in rich listing
        for sid in ("a1", "b1"):
            self.db.append_message(sid, "user", "hello")
        only_a = self.db.list_sessions_rich(workspace="owner/aaa")
        ids = {r["id"] for r in only_a}
        self.assertIn("a1", ids)
        self.assertNotIn("b1", ids)

    def test_backwards_compat_unbound_session(self):
        # A session created with no cwd has null workspace fields and renders
        # as unbound (workspace_key None) — no crash.
        self.db.create_session("legacy", "cli")
        row = self.db.get_session("legacy")
        self.assertIsNone(row.get("git_remote"))
        self.assertIsNone(self.hs.workspace_key(row))


if __name__ == "__main__":
    unittest.main()
