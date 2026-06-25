"""Shared gpt-image-2 catalog for the OpenAI image-gen backends.

The API-key (``openai``) and ChatGPT/Codex-OAuth (``openai-codex``) plugins both
drive the same underlying model, ``gpt-image-2``, at the same three quality
tiers. They diverge only in transport and auth — the model catalog, the
aspect→size map, the edit reference cap, and the tier-resolution logic are
properties of the model and were identical in both plugins. Keep them here so
the two can't drift.

Each plugin selects its tier from config under its own ``image_gen.<name>``
subsection, falling back to the top-level ``image_gen.model`` and then
:data:`DEFAULT_MODEL`; the ``OPENAI_IMAGE_MODEL`` env var overrides both.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

# The API model both backends drive. The three catalog IDs below all resolve to
# it with a different ``quality`` setting.
API_MODEL = "gpt-image-2"

MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2-low": {
        "display": "GPT Image 2 (Low)",
        "speed": "~15s",
        "strengths": "Fast iteration, lowest cost",
        "quality": "low",
    },
    "gpt-image-2-medium": {
        "display": "GPT Image 2 (Medium)",
        "speed": "~40s",
        "strengths": "Balanced — default",
        "quality": "medium",
    },
    "gpt-image-2-high": {
        "display": "GPT Image 2 (High)",
        "speed": "~2min",
        "strengths": "Highest fidelity, strongest prompt adherence",
        "quality": "high",
    },
}

DEFAULT_MODEL = "gpt-image-2-medium"

SIZES = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}

# gpt-image-2's edit endpoint accepts up to 16 reference images.
MAX_REFERENCE_IMAGES = 16


def load_image_gen_config() -> Dict[str, Any]:
    """Read the ``image_gen`` section from config.yaml (returns {} on any failure)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen config: %s", exc)
        return {}


def resolve_tier(subsection_key: str) -> Tuple[str, Dict[str, Any]]:
    """Resolve the active quality tier, returning ``(model_id, meta)``.

    Precedence (first hit wins): the ``OPENAI_IMAGE_MODEL`` env var, the
    ``image_gen.<subsection_key>.model`` config key, the top-level
    ``image_gen.model`` config key, then :data:`DEFAULT_MODEL`. Values that
    aren't one of the known tier IDs are ignored.
    """
    env_override = os.environ.get("OPENAI_IMAGE_MODEL")
    if env_override and env_override in MODELS:
        return env_override, MODELS[env_override]

    cfg = load_image_gen_config()
    sub = cfg.get(subsection_key) if isinstance(cfg.get(subsection_key), dict) else {}
    candidate = None
    if isinstance(sub, dict):
        value = sub.get("model")
        if isinstance(value, str) and value in MODELS:
            candidate = value
    if candidate is None:
        top = cfg.get("model")
        if isinstance(top, str) and top in MODELS:
            candidate = top

    if candidate is not None:
        return candidate, MODELS[candidate]

    return DEFAULT_MODEL, MODELS[DEFAULT_MODEL]
