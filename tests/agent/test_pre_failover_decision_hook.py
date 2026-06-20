"""Tests for the pre_failover_decision plugin hook.

The hook fires inside the retry loop just before the fallback chain is
activated, giving plugins the opportunity to redirect, retry, or abort
the failover decision.
"""

import types
from unittest.mock import MagicMock, patch

import pytest

from agent.error_classifier import ClassifiedError, FailoverReason


@pytest.fixture
def mock_agent():
    """Minimal mock agent for testing _invoke_pre_failover_decision."""
    agent = MagicMock()
    agent.model = "claude-opus-4"
    agent.provider = "bedrock"
    agent.base_url = "https://bedrock-runtime.us-west-2.amazonaws.com"
    agent.api_mode = "bedrock_converse"
    agent.session_id = "test-session-123"
    agent.platform = "tui"
    return agent


@pytest.fixture
def classified_rate_limit():
    """A ClassifiedError for rate limiting."""
    return ClassifiedError(
        reason=FailoverReason.rate_limit,
        status_code=429,
        retryable=True,
        should_compress=False,
        should_rotate_credential=False,
        should_fallback=True,
    )


@pytest.fixture
def classified_auth():
    """A ClassifiedError for auth failure."""
    return ClassifiedError(
        reason=FailoverReason.auth,
        status_code=401,
        retryable=False,
        should_compress=False,
        should_rotate_credential=False,
        should_fallback=True,
    )


class TestPreFailoverDecisionHook:
    """Test that _invoke_pre_failover_decision correctly dispatches."""

    def test_no_hook_registered_returns_none(self, mock_agent, classified_rate_limit):
        """When no plugin registers the hook, returns None."""
        with patch("hermes_cli.plugins.has_hook", return_value=False):
            from run_agent import AIAgent

            # Call the real method on a mock by binding it
            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result is None

    def test_redirect_action_returned(self, mock_agent, classified_rate_limit):
        """Plugin returning redirect action is picked up."""
        redirect_result = {
            "action": "redirect",
            "model": "qwen3-30b",
            "provider": "custom:llm-local",
        }
        with patch("hermes_cli.plugins.has_hook", return_value=True), \
             patch("hermes_cli.plugins.invoke_hook", return_value=[redirect_result]):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result == redirect_result

    def test_retry_action_returned(self, mock_agent, classified_rate_limit):
        """Plugin returning retry action is picked up."""
        with patch("hermes_cli.plugins.has_hook", return_value=True), \
             patch("hermes_cli.plugins.invoke_hook", return_value=[{"action": "retry"}]):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=1,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result == {"action": "retry"}

    def test_abort_action_returned(self, mock_agent, classified_auth):
        """Plugin returning abort action is picked up."""
        abort_result = {"action": "abort", "message": "Auth permanently failed."}
        with patch("hermes_cli.plugins.has_hook", return_value=True), \
             patch("hermes_cli.plugins.invoke_hook", return_value=[abort_result]):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_auth,
                retry_count=3,
                max_retries=3,
                error_type="AuthenticationError",
                error_message="Invalid credentials",
                status_code=401,
            )
            assert result == abort_result

    def test_continue_action_is_ignored(self, mock_agent, classified_rate_limit):
        """Plugin returning continue action is treated as no-op."""
        with patch("hermes_cli.plugins.has_hook", return_value=True), \
             patch("hermes_cli.plugins.invoke_hook", return_value=[{"action": "continue"}]):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result is None

    def test_empty_dict_is_ignored(self, mock_agent, classified_rate_limit):
        """Plugin returning empty dict is treated as no-op."""
        with patch("hermes_cli.plugins.has_hook", return_value=True), \
             patch("hermes_cli.plugins.invoke_hook", return_value=[{}]):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result is None

    def test_first_actionable_wins(self, mock_agent, classified_rate_limit):
        """When multiple plugins respond, first actionable result wins."""
        results = [
            {"action": "continue"},  # ignored
            {"action": "redirect", "model": "fast-model", "provider": "local"},
            {"action": "abort", "message": "too late"},  # never reached
        ]
        with patch("hermes_cli.plugins.has_hook", return_value=True), \
             patch("hermes_cli.plugins.invoke_hook", return_value=results):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result["action"] == "redirect"
            assert result["model"] == "fast-model"

    def test_exception_in_hook_returns_none(self, mock_agent, classified_rate_limit):
        """If plugin hook raises, gracefully returns None."""
        with patch("hermes_cli.plugins.has_hook", side_effect=RuntimeError("boom")):
            from run_agent import AIAgent

            result = AIAgent._invoke_pre_failover_decision(
                mock_agent,
                classified=classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result is None


class TestTryFailoverWithHook:
    """Test the _try_failover_with_hook helper in conversation_loop."""

    def test_no_hook_returns_none(self, mock_agent, classified_rate_limit):
        """When no plugin intercedes, returns None."""
        mock_agent._invoke_pre_failover_decision.return_value = None

        from agent.conversation_loop import _try_failover_with_hook

        result = _try_failover_with_hook(
            mock_agent, classified_rate_limit,
            retry_count=3,
            max_retries=3,
            error_type="APIError",
            error_message="Rate limited",
            status_code=429,
        )
        assert result is None

    def test_redirect_calls_switch_model(self, mock_agent, classified_rate_limit):
        """Redirect action calls switch_model and returns 'redirected'."""
        mock_agent._invoke_pre_failover_decision.return_value = {
            "action": "redirect",
            "model": "qwen3-30b",
            "provider": "custom:llm-local",
            "base_url": "http://localhost:58080",
        }

        from agent.conversation_loop import _try_failover_with_hook

        with patch("agent.agent_runtime_helpers.switch_model") as mock_switch:
            result = _try_failover_with_hook(
                mock_agent, classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result == "redirected"
            mock_switch.assert_called_once_with(
                mock_agent,
                "qwen3-30b",
                "custom:llm-local",
                api_key="",
                base_url="http://localhost:58080",
                api_mode="",
            )

    def test_retry_returns_retry(self, mock_agent, classified_rate_limit):
        """Retry action returns 'retry' without calling switch_model."""
        mock_agent._invoke_pre_failover_decision.return_value = {"action": "retry"}

        from agent.conversation_loop import _try_failover_with_hook

        result = _try_failover_with_hook(
            mock_agent, classified_rate_limit,
            retry_count=1,
            max_retries=3,
            error_type="APIError",
            error_message="Rate limited",
            status_code=429,
        )
        assert result == "retry"

    def test_abort_sets_message_and_returns_abort(self, mock_agent, classified_auth):
        """Abort action stores message on agent and returns 'abort'."""
        mock_agent._invoke_pre_failover_decision.return_value = {
            "action": "abort",
            "message": "Cannot recover from auth failure.",
        }

        from agent.conversation_loop import _try_failover_with_hook

        result = _try_failover_with_hook(
            mock_agent, classified_auth,
            retry_count=3,
            max_retries=3,
            error_type="AuthError",
            error_message="Invalid token",
            status_code=401,
        )
        assert result == "abort"
        assert mock_agent._failover_abort_message == "Cannot recover from auth failure."

    def test_redirect_failure_falls_through(self, mock_agent, classified_rate_limit):
        """If switch_model raises, returns None (falls through to normal fallback)."""
        mock_agent._invoke_pre_failover_decision.return_value = {
            "action": "redirect",
            "model": "bad-model",
            "provider": "nonexistent",
        }

        from agent.conversation_loop import _try_failover_with_hook

        with patch("agent.agent_runtime_helpers.switch_model", side_effect=ValueError("Unknown provider")):
            result = _try_failover_with_hook(
                mock_agent, classified_rate_limit,
                retry_count=3,
                max_retries=3,
                error_type="APIError",
                error_message="Rate limited",
                status_code=429,
            )
            assert result is None


class TestHookInValidHooks:
    """Verify the hook is registered in VALID_HOOKS."""

    def test_pre_failover_decision_in_valid_hooks(self):
        from hermes_cli.plugins import VALID_HOOKS

        assert "pre_failover_decision" in VALID_HOOKS
