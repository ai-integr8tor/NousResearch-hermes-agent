"""Tests for web extract configurable summarization thresholds.

Coverage:
  _read_web_extract_config() — config reading with fallback to defaults.
  process_content_with_llm() — uses config values for MAX_OUTPUT_SIZE, min_length, max_tokens.
  _call_summarizer_llm() — injects character limit into system prompt.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestReadWebExtractConfig:
    """Test _read_web_extract_config reads config values correctly."""

    def test_defaults_when_no_config(self):
        """Returns hardcoded defaults when config has no web section."""
        with patch("hermes_cli.config.load_config", return_value={}):
            from tools.web_tools import _read_web_extract_config
            cfg = _read_web_extract_config()
            assert cfg["max_output_size"] == 5000
            assert cfg["min_length"] == 5000
            assert cfg["max_tokens"] == 20000

    def test_defaults_when_config_load_fails(self):
        """Returns hardcoded defaults when load_config raises."""
        with patch("hermes_cli.config.load_config", side_effect=Exception("no config")):
            from tools.web_tools import _read_web_extract_config
            cfg = _read_web_extract_config()
            assert cfg["max_output_size"] == 5000
            assert cfg["min_length"] == 5000
            assert cfg["max_tokens"] == 20000

    def test_reads_custom_values(self):
        """Reads custom values from web config section."""
        config = {
            "web": {
                "extract_summary_max_chars": 10000,
                "extract_min_length": 3000,
                "extract_summary_max_tokens": 30000,
            }
        }
        with patch("hermes_cli.config.load_config", return_value=config):
            from tools.web_tools import _read_web_extract_config
            cfg = _read_web_extract_config()
            assert cfg["max_output_size"] == 10000
            assert cfg["min_length"] == 3000
            assert cfg["max_tokens"] == 30000

    def test_ignores_invalid_values(self):
        """Ignores non-numeric or zero/negative values, uses defaults."""
        config = {
            "web": {
                "extract_summary_max_chars": "not_a_number",
                "extract_min_length": 0,
                "extract_summary_max_tokens": -1,
            }
        }
        with patch("hermes_cli.config.load_config", return_value=config):
            from tools.web_tools import _read_web_extract_config
            cfg = _read_web_extract_config()
            assert cfg["max_output_size"] == 5000
            assert cfg["min_length"] == 5000
            assert cfg["max_tokens"] == 20000

    def test_partial_config_uses_defaults_for_missing(self):
        """Only overrides values that are present in config."""
        config = {
            "web": {
                "extract_summary_max_chars": 8000,
            }
        }
        with patch("hermes_cli.config.load_config", return_value=config):
            from tools.web_tools import _read_web_extract_config
            cfg = _read_web_extract_config()
            assert cfg["max_output_size"] == 8000
            assert cfg["min_length"] == 5000
            assert cfg["max_tokens"] == 20000


class TestCallSummarizerLlmPromptInjection:
    """Test that _call_summarizer_llm injects character limit into system prompt."""

    @pytest.mark.asyncio
    async def test_system_prompt_includes_max_output_size(self):
        """System prompt should contain the configured max_output_size."""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="summary"))]

        with patch(
            "tools.web_tools._resolve_web_extract_auxiliary",
            return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {}),
        ), patch(
            "tools.web_tools.async_call_llm",
            new=AsyncMock(return_value=response),
        ) as mock_call:
            from tools.web_tools import _call_summarizer_llm
            await _call_summarizer_llm(
                "content", "", None, max_output_size=12345,
            )

        # Check that the system prompt contains the character limit
        call_args = mock_call.call_args
        messages = call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "12,345" in system_msg or "12345" in system_msg

    @pytest.mark.asyncio
    async def test_default_max_output_size_in_prompt(self):
        """Default 5000 should appear in prompt when no override."""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="summary"))]

        with patch(
            "tools.web_tools._resolve_web_extract_auxiliary",
            return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {}),
        ), patch(
            "tools.web_tools.async_call_llm",
            new=AsyncMock(return_value=response),
        ) as mock_call:
            from tools.web_tools import _call_summarizer_llm
            await _call_summarizer_llm("content", "", None)

        call_args = mock_call.call_args
        messages = call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "5,000" in system_msg or "5000" in system_msg

    @pytest.mark.asyncio
    async def test_chunk_prompt_does_not_include_char_limit(self):
        """Chunk-specific prompt should NOT include the character limit."""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="chunk summary"))]

        with patch(
            "tools.web_tools._resolve_web_extract_auxiliary",
            return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {}),
        ), patch(
            "tools.web_tools.async_call_llm",
            new=AsyncMock(return_value=response),
        ) as mock_call:
            from tools.web_tools import _call_summarizer_llm
            await _call_summarizer_llm(
                "content", "", None, is_chunk=True, chunk_info="[Chunk 1/3]",
                max_output_size=12345,
            )

        call_args = mock_call.call_args
        messages = call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        # Chunk prompt is about extracting from a section, not about output size
        assert "12,345" not in system_msg

    @pytest.mark.asyncio
    async def test_max_tokens_passed_to_llm_call(self):
        """max_tokens parameter should be passed through to async_call_llm."""
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="summary"))]

        with patch(
            "tools.web_tools._resolve_web_extract_auxiliary",
            return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {}),
        ), patch(
            "tools.web_tools.async_call_llm",
            new=AsyncMock(return_value=response),
        ) as mock_call:
            from tools.web_tools import _call_summarizer_llm
            await _call_summarizer_llm("content", "", None, max_tokens=30000)

        call_args = mock_call.call_args
        assert call_args.kwargs["max_tokens"] == 30000


class TestProcessContentWithLlmConfig:
    """Test that process_content_with_llm reads config values."""

    @pytest.mark.asyncio
    async def test_uses_config_max_output_size(self):
        """Output should be capped at config value, not hardcoded 5000."""
        long_summary = "x" * 8000
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content=long_summary))]

        config = {"web": {"extract_summary_max_chars": 6000}}
        with patch("hermes_cli.config.load_config", return_value=config), \
             patch("tools.web_tools._resolve_web_extract_auxiliary",
                   return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {})), \
             patch("tools.web_tools.async_call_llm",
                   new=AsyncMock(return_value=response)):
            from tools.web_tools import process_content_with_llm
            result = await process_content_with_llm("a" * 6000, min_length=100)

        truncation_msg = "\n\n[... summary truncated for context management ...]"
        assert result is not None
        assert len(result) <= 6000 + len(truncation_msg)
        assert len(result) > 5000  # Would have been capped at 5000 with old hardcoded value

    @pytest.mark.asyncio
    async def test_uses_config_min_length(self):
        """Should skip processing when content < config min_length."""
        config = {"web": {"extract_min_length": 3000}}
        with patch("hermes_cli.config.load_config", return_value=config), \
             patch("tools.web_tools._resolve_web_extract_auxiliary",
                   return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {})), \
             patch("tools.web_tools.async_call_llm",
                   new=AsyncMock(return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="s"))]))):
            from tools.web_tools import process_content_with_llm
            # Content is 2000 chars, below config min_length of 3000
            result = await process_content_with_llm("a" * 2000)

        assert result is None  # Skipped because below min_length

    @pytest.mark.asyncio
    async def test_explicit_min_length_overrides_config(self):
        """When caller passes explicit min_length, config is not used."""
        config = {"web": {"extract_min_length": 10000}}
        with patch("hermes_cli.config.load_config", return_value=config), \
             patch("tools.web_tools._resolve_web_extract_auxiliary",
                   return_value=(MagicMock(base_url="https://api.test.com/v1"), "test-model", {})), \
             patch("tools.web_tools.async_call_llm",
                   new=AsyncMock(return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="summary"))]))):
            from tools.web_tools import process_content_with_llm
            # Explicit min_length=100 overrides config's 10000
            result = await process_content_with_llm("a" * 500, min_length=100)

        assert result is not None  # Processed because explicit min_length=100 < 500


class TestConfigKeysInDefaultConfig:
    """Verify the new config keys exist in DEFAULT_CONFIG."""

    def test_extract_summary_max_chars_in_defaults(self):
        from hermes_cli.config import DEFAULT_CONFIG
        assert "extract_summary_max_chars" in DEFAULT_CONFIG["web"]
        assert DEFAULT_CONFIG["web"]["extract_summary_max_chars"] == 5000

    def test_extract_min_length_in_defaults(self):
        from hermes_cli.config import DEFAULT_CONFIG
        assert "extract_min_length" in DEFAULT_CONFIG["web"]
        assert DEFAULT_CONFIG["web"]["extract_min_length"] == 5000

    def test_extract_summary_max_tokens_in_defaults(self):
        from hermes_cli.config import DEFAULT_CONFIG
        assert "extract_summary_max_tokens" in DEFAULT_CONFIG["web"]
        assert DEFAULT_CONFIG["web"]["extract_summary_max_tokens"] == 20000
