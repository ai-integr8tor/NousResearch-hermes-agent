"""Regression tests for _is_fork() URL normalization in hermes_cli/main.py.

Bug: Issue #59584 - _is_fork() returns True (false positive) when the
origin remote URL contains embedded credentials, e.g.:

    https://<token>@github.com/NousResearch/hermes-agent.git

The current implementation only strips trailing slashes and `.git` suffixes
but does not strip the `user:token@` or `token@` credentials prefix. This
causes a false "Updating from fork:" warning during `hermes update` even
when the user is pulling from the genuine NousResearch/hermes-agent repo.

Each test exercises the production function directly. They should:
1. FAIL on upstream/main (RED) - the bug is still present
2. PASS after the fix (GREEN)
"""
from __future__ import annotations

from hermes_cli.main import _is_fork


class TestIsForkCredentialsPrefix:
    """Embedded credentials in HTTPS URLs should not trigger fork detection."""

    def test_token_in_https_url_is_not_fork(self):
        """A token-prefixed HTTPS URL to the official repo should NOT be detected as a fork."""
        url = "https://ghp_abc123def456@github.com/NousResearch/hermes-agent.git"
        assert _is_fork(url) is False, (
            f"Expected URL with token prefix to official repo to be detected as official, "
            f"but _is_fork({url!r}) returned True"
        )

    def test_user_pass_in_https_url_is_not_fork(self):
        """A user:password-prefixed HTTPS URL should not be detected as a fork."""
        url = "https://user:pass@github.com/NousResearch/hermes-agent.git"
        assert _is_fork(url) is False

    def test_token_in_https_url_no_dot_git_is_not_fork(self):
        """A token-prefixed HTTPS URL without .git suffix should not be detected as a fork."""
        url = "https://ghp_abc123@github.com/NousResearch/hermes-agent"
        assert _is_fork(url) is False

    def test_token_in_https_url_with_trailing_slash_is_not_fork(self):
        """A token-prefixed HTTPS URL with trailing slash should not be detected as a fork."""
        url = "https://ghp_abc123@github.com/NousResearch/hermes-agent.git/"
        assert _is_fork(url) is False

    def test_password_containing_at_sign_is_not_fork(self):
        """A password containing '@' must still strip all credentials (RFC 3986)."""
        url = "https://user:p@ss@github.com/NousResearch/hermes-agent.git"
        assert _is_fork(url) is False


class TestIsForkExistingBehavior:
    """Existing normalization behavior should still work after the fix."""

    def test_official_https_url_is_not_fork(self):
        """The official HTTPS URL should not be detected as a fork."""
        assert _is_fork("https://github.com/NousResearch/hermes-agent.git") is False

    def test_official_https_url_no_dot_git_is_not_fork(self):
        assert _is_fork("https://github.com/NousResearch/hermes-agent") is False

    def test_official_ssh_url_is_not_fork(self):
        """The official SSH URL should not be detected as a fork."""
        assert _is_fork("git@github.com:NousResearch/hermes-agent.git") is False

    def test_none_url_is_not_fork(self):
        """None should be safe and return False (matches existing behavior)."""
        assert _is_fork(None) is False

    def test_empty_string_is_not_fork(self):
        """Empty string should be safe and return False (matches existing behavior)."""
        assert _is_fork("") is False


class TestIsForkActualForks:
    """Actual fork URLs should still be detected as forks."""

    def test_different_owner_is_fork(self):
        """A URL pointing to a different owner should still be a fork."""
        assert _is_fork("https://github.com/someuser/hermes-agent.git") is True

    def test_different_repo_name_is_fork(self):
        """A URL pointing to a different repo name should still be a fork."""
        assert _is_fork("https://github.com/NousResearch/some-other-repo.git") is True

    def test_token_in_fork_url_is_still_fork(self):
        """A token-prefixed URL to a different repo should still be a fork."""
        assert _is_fork("https://ghp_abc@github.com/someuser/hermes-agent.git") is True
