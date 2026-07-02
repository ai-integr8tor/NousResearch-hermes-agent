"""Runware provider profile.

Runware (https://runware.ai) exposes an OpenAI-compatible chat completions
endpoint at https://api.runware.ai/v1, fronting both open-weight models run
on Runware's own Sonic Inference Engine (GLM, DeepSeek, MiniMax, Qwen,
Kimi, ...) and pass-through access to closed-source frontier models
(Anthropic, OpenAI, Google, xAI) under one account and bill. Model IDs are
plain slugs (e.g. "openai-gpt-5-4", "anthropic-claude-sonnet-4-6",
"minimax-m2-7") — no special parsing quirks elsewhere in the codebase.

GET /v1/models returns a bare JSON array (not the usual {"data": [...]}
wrapper) with rich per-model metadata — context_length, max_output_tokens,
and OpenRouter-shaped pricing — which the base ProviderProfile.fetch_models()
and agent.model_metadata.fetch_endpoint_model_metadata() both already parse,
so the model list and context lengths resolve dynamically from the live
catalog instead of a hardcoded table.

Docs: https://runware.ai/docs/platform/openai
"""

from providers import register_provider
from providers.base import ProviderProfile


class RunwareProfile(ProviderProfile):
    """Runware — per-model max_tokens cap.

    When ``max_tokens`` is omitted from the request, Runware's OpenAI-compat
    endpoint does not fall back to the model's own completion-token limit —
    it 400s with "'settings.maxTokens' must be an integer between 1 and
    <model's real cap>" (e.g. 384000 for deepseek-v4-flash). Hermes only
    sends an explicit max_tokens when the user configured one or a profile
    declares a default (see ProviderProfile.get_max_tokens), so Runware
    models were left with no value at all on a fresh conversation.

    Caps below are the ``max_output_tokens`` values from Runware's live
    /v1/models response (verified 2026-07-02). Models not listed here fall
    back to None (no max_tokens sent, matching prior behavior) rather than
    guessing a number that might exceed some other model's cap.
    """

    _MODEL_MAX_TOKENS = {
        "openai-gpt-5-4": 128000,
        "openai-gpt-5-4-mini": 128000,
        "openai-gpt-5-4-nano": 128000,
        "openai-gpt-5-4-pro": 128000,
        "openai-gpt-5-mini": 128000,
        "openai-gpt-5-nano": 128000,
        "openai-gpt-5-5": 128000,
        "anthropic-claude-opus-4-7": 128000,
        "anthropic-claude-opus-4-8": 128000,
        "anthropic-claude-sonnet-4-6": 128000,
        "anthropic-claude-haiku-4-5": 64000,
        "anthropic-claude-fable-5": 128000,
        "google-gemini-3-1-pro": 65536,
        "google-gemini-3-1-flash-lite": 65536,
        "google-gemini-3-flash": 65536,
        "google-gemini-3-5-flash": 65536,
        "google-gemma-4-31b": 65536,
        "deepseek-v4-flash": 384000,
        "deepseek-v4-pro": 384000,
        "minimax-m2-5": 196608,
        "minimax-m2-7": 131072,
        "minimax-m2-7-highspeed": 131072,
        "minimax-m3": 512000,
        "zai-glm-4-7": 131072,
        "zai-glm-5-1": 131072,
        "moonshotai-kimi-k2-6": 49152,
        "xai-grok-4-3": 131072,
        "qwen35_397b_a17b_fp8": 128000,
        "qwen35_27b_fp8": 128000,
    }

    def get_max_tokens(self, model: str | None) -> int | None:
        return self._MODEL_MAX_TOKENS.get(model or "", self.default_max_tokens)


runware = RunwareProfile(
    name="runware",
    aliases=("runware-ai", "runwareai"),
    display_name="Runware",
    description="Runware — open + closed source LLMs on one OpenAI-compatible endpoint",
    signup_url="https://runware.ai/signup",
    env_vars=("RUNWARE_API_KEY", "RUNWARE_BASE_URL"),
    base_url="https://api.runware.ai/v1",
    auth_type="api_key",
    default_aux_model="deepseek-v4-flash",
    fallback_models=(
        "openai-gpt-5-4",
        "openai-gpt-5-4-mini",
        "anthropic-claude-opus-4-8",
        "anthropic-claude-sonnet-4-6",
        "anthropic-claude-haiku-4-5",
        "google-gemini-3-1-pro",
        "google-gemini-3-1-flash-lite",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "minimax-m3",
        "minimax-m2-7",
        "zai-glm-4-7",
        "moonshotai-kimi-k2-6",
        "xai-grok-4-3",
        "qwen35_397b_a17b_fp8",
    ),
)

register_provider(runware)
