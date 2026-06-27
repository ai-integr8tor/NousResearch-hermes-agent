"""LLMTR provider profile.

LLMTR (https://llmtr.com) is a Türkiye-based, OpenAI-compatible AI gateway.
Like OpenRouter, it fronts many upstream providers behind a single endpoint and
routes by ``provider/model`` slugs (e.g. ``anthropic/claude-opus-4.8``,
``openai/gpt-5.5``, ``google/gemini-3.1-pro-preview``). API keys are prefixed
``llmtr-`` and sent as a standard ``Authorization: Bearer`` header, so the base
``ProviderProfile`` (OpenAI chat-completions transport, ``/v1/models`` catalog)
wires it up without any custom hooks.
"""

from providers import register_provider
from providers.base import ProviderProfile

llmtr = ProviderProfile(
    name="llmtr",
    aliases=("llm-tr", "llmtr-com", "llmtr.com"),
    env_vars=("LLMTR_API_KEY", "LLMTR_BASE_URL"),
    display_name="LLMTR",
    description="LLMTR — Türkiye-based OpenAI-compatible AI gateway (198+ models)",
    signup_url="https://llmtr.com",
    base_url="https://llmtr.com/v1",
    # Curated agentic (tool-calling) models shown in the picker when the live
    # /v1/models fetch is unavailable. LLMTR routes by provider/model slugs.
    fallback_models=(
        "anthropic/claude-opus-4.8",
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5.5",
        "google/gemini-3.1-pro-preview",
        "deepseek/deepseek-v4-pro",
        "qwen/qwen3.7-max",
        "zai/glm-5.1",
    ),
    # Cheap, fast model for auxiliary tasks (compression, vision, summaries).
    default_aux_model="google/gemini-2.5-flash",
)

register_provider(llmtr)
