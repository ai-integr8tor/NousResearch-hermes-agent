"""Declarative configuration schema for desktop memory providers.

Each memory provider *declares* its configurable surface here — the fields, their
types, which values are secrets, and (for selects) the allowed options. A single
generic renderer in the desktop UI and a single generic ``GET/PUT
/api/memory/providers/{name}/config`` endpoint pair drive the whole experience,
so adding a new provider (mem0, honcho, ...) is pure declaration with zero
bespoke UI components or endpoints.

This module is intentionally pure data: it imports nothing from the config/env
layer. ``web_server`` owns the generic read/write logic that interprets these
declarations against config.yaml, the provider config file, and the env store.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field

# Field kinds understood by the generic renderer.
KIND_TEXT = "text"
KIND_SELECT = "select"
KIND_SECRET = "secret"


@dataclass(frozen=True)
class ProviderFieldOption:
    """A single choice for a ``select`` field."""

    value: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class ProviderField:
    """One configurable field on a memory provider.

    A field is stored in exactly one place, decided by ``kind``:

    * ``text`` / ``select`` — persisted to the provider's JSON config file
      (``<hermes_home>/<provider>/config.json``) under ``key``.
    * ``secret`` — persisted to the env store under ``env_key`` and never read
      back out over the API (only an ``is_set`` flag is surfaced).

    ``aliases`` and ``env_fallbacks`` let a field read legacy values written by
    earlier CLI/env setup without re-introducing per-provider code.
    """

    key: str
    label: str
    kind: str = KIND_TEXT
    default: str = ""
    description: str = ""
    placeholder: str = ""
    options: tuple[ProviderFieldOption, ...] = ()
    env_key: str | None = None
    aliases: tuple[str, ...] = ()
    env_fallbacks: tuple[str, ...] = ()

    @property
    def is_secret(self) -> bool:
        return self.kind == KIND_SECRET

    def allowed_values(self) -> set[str]:
        return {opt.value for opt in self.options}


@dataclass(frozen=True)
class MemoryProvider:
    """A declared memory provider and its configurable fields."""

    name: str
    label: str
    fields: tuple[ProviderField, ...] = dataclass_field(default_factory=tuple)


HINDSIGHT = MemoryProvider(
    name="hindsight",
    label="Hindsight",
    fields=(
        ProviderField(
            key="mode",
            label="Mode",
            kind=KIND_SELECT,
            default="cloud",
            description="How Hermes connects to Hindsight.",
            options=(
                ProviderFieldOption(
                    "cloud",
                    "Cloud",
                    "Hindsight Cloud API (lightweight, just needs an API key)",
                ),
                ProviderFieldOption(
                    "local_embedded",
                    "Local Embedded",
                    "Run a managed local Hindsight daemon with embedded PostgreSQL (needs LLM API key)",
                ),
                ProviderFieldOption(
                    "local_external",
                    "Local External",
                    "Connect to an existing Hindsight instance",
                ),
            ),
        ),
        ProviderField(
            key="api_key",
            label="Cloud API key",
            kind=KIND_SECRET,
            env_key="HINDSIGHT_API_KEY",
            description="Hindsight Cloud API key (cloud mode only).",
            placeholder="Enter Hindsight Cloud API key",
        ),
        ProviderField(
            key="llm_api_key",
            label="LLM API key",
            kind=KIND_SECRET,
            env_key="HINDSIGHT_LLM_API_KEY",
            description="LLM API key for memory extraction (local embedded mode).",
            placeholder="Enter LLM API key",
        ),
        ProviderField(
            key="llm_provider",
            label="LLM provider",
            kind=KIND_TEXT,
            default="openai",
            description="LLM provider for local embedded mode (openai, anthropic, openai_compatible, ollama, etc.).",
        ),
        ProviderField(
            key="llm_base_url",
            label="LLM base URL",
            kind=KIND_TEXT,
            description="OpenAI-compatible endpoint URL (for openai_compatible provider).",
            env_fallbacks=("HINDSIGHT_API_LLM_BASE_URL",),
        ),
        ProviderField(
            key="llm_model",
            label="LLM model",
            kind=KIND_TEXT,
            default="gpt-4o-mini",
            description="Model name for LLM calls (e.g. gpt-4o-mini, glm-5.2-heavy).",
        ),
        ProviderField(
            key="api_url",
            label="API URL",
            kind=KIND_TEXT,
            default="https://api.hindsight.vectorize.io",
            aliases=("apiUrl",),
            env_fallbacks=("HINDSIGHT_API_URL",),
        ),
        ProviderField(
            key="bank_id",
            label="Bank ID",
            kind=KIND_TEXT,
            default="hermes",
            aliases=("bankId",),
        ),
        ProviderField(
            key="recall_budget",
            label="Recall budget",
            kind=KIND_SELECT,
            default="mid",
            aliases=("budget",),
            options=(
                ProviderFieldOption("low", "low"),
                ProviderFieldOption("mid", "mid"),
                ProviderFieldOption("high", "high"),
            ),
        ),
    ),
)


# Registry of providers that expose a desktop config surface. Providers without
# an entry here (e.g. ``builtin``) simply render no config panel.
MEMORY_PROVIDERS: dict[str, MemoryProvider] = {
    HINDSIGHT.name: HINDSIGHT,
}


def get_memory_provider(name: str) -> MemoryProvider | None:
    """Return the declared provider for ``name``, or ``None`` if undeclared."""

    return MEMORY_PROVIDERS.get(name)
