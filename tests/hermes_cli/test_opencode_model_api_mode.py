"""Tests for OpenCode per-model API mode routing."""

from hermes_cli.models import opencode_model_api_mode



def test_opencode_go_qwen37_plus_uses_anthropic_messages():
    assert opencode_model_api_mode("opencode-go", "qwen3.7-plus") == "anthropic_messages"


def test_opencode_go_deepseek_v4_flash_uses_chat_completions():
    assert opencode_model_api_mode("opencode-go", "deepseek-v4-flash") == "chat_completions"
