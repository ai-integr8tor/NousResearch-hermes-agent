"""Raw LLM interaction capture for later scoring and replay.

This module is deliberately small and dependency-light because it runs in the
hot path around every provider call when enabled.  It records the exact provider
request payload Hermes is about to send plus either the raw provider response
object (best-effort serialized) or the raised exception.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_constants import get_hermes_home

_SCHEMA_VERSION = "hermes.raw_interaction.v1"
_WRITE_LOCK = threading.Lock()


def _env_enabled(name: str) -> Optional[bool]:
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def capture_enabled() -> bool:
    """Return whether raw interaction capture is enabled.

    Config key: ``interaction_capture.enabled``.
    Env override: ``HERMES_CAPTURE_INTERACTIONS=1``.
    """
    env = _env_enabled("HERMES_CAPTURE_INTERACTIONS")
    if env is not None:
        return env
    try:
        from hermes_cli.config import cfg_get, load_config_readonly

        cfg = load_config_readonly()
        return bool(cfg_get(cfg, "interaction_capture", "enabled", default=False))
    except Exception:
        return False


def capture_dir() -> Path:
    """Directory where raw interactions are appended as JSONL.

    Config key: ``interaction_capture.dir``.  Env override:
    ``HERMES_CAPTURE_DIR``.  Defaults to
    ``$HERMES_HOME/interactions/raw``.
    """
    env_dir = os.environ.get("HERMES_CAPTURE_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    try:
        from hermes_cli.config import cfg_get, load_config_readonly

        cfg = load_config_readonly()
        configured = cfg_get(cfg, "interaction_capture", "dir", default=None)
        if configured:
            return Path(str(configured)).expanduser()
    except Exception:
        pass
    return get_hermes_home() / "interactions" / "raw"


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Best-effort conversion of SDK objects into JSON-safe structures.

    We intentionally do not redact request/response content here: this feature
    exists to support exact future scoring, research, and replay.  The only
    transformation is serialization so the record can be written reliably.
    """
    if depth > 12:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"__bytes__": True, "utf8": value.decode("utf-8", errors="replace")}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, depth=depth + 1) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return _json_safe(dataclasses.asdict(value), depth=depth + 1)
        except Exception:
            pass
    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                if attr == "model_dump":
                    return _json_safe(fn(mode="json"), depth=depth + 1)
                return _json_safe(fn(), depth=depth + 1)
            except TypeError:
                try:
                    return _json_safe(fn(), depth=depth + 1)
                except Exception:
                    pass
            except Exception:
                pass
    if hasattr(value, "__dict__"):
        try:
            return {
                "__class__": f"{value.__class__.__module__}.{value.__class__.__name__}",
                "attributes": _json_safe(vars(value), depth=depth + 1),
                "repr": repr(value),
            }
        except Exception:
            pass
    return repr(value)


def _daily_jsonl_path(base_dir: Path) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    compress = _env_enabled("HERMES_CAPTURE_GZIP")
    if compress is None:
        try:
            from hermes_cli.config import cfg_get, load_config_readonly

            cfg = load_config_readonly()
            compress = bool(cfg_get(cfg, "interaction_capture", "gzip", default=False))
        except Exception:
            compress = False
    suffix = ".jsonl.gz" if compress else ".jsonl"
    return base_dir / f"{date}{suffix}"


def write_interaction_record(record: Dict[str, Any]) -> Optional[Path]:
    """Append one already-formed capture record. Returns the written path."""
    base = capture_dir()
    path = _daily_jsonl_path(base)
    try:
        base.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with _WRITE_LOCK:
            if path.suffix == ".gz":
                with gzip.open(path, "at", encoding="utf-8") as fh:
                    fh.write(line)
            else:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
        return path
    except Exception:
        # Capture must never break the agent path.  Logging from here can recurse
        # into provider calls in unusual plugin setups, so stay silent.
        return None


def capture_llm_success(request: Dict[str, Any], response: Any, **context: Any) -> Optional[Path]:
    if not capture_enabled():
        return None
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "schema_version": _SCHEMA_VERSION,
        "record_id": str(uuid.uuid4()),
        "captured_at": now,
        "unix_time": time.time(),
        "kind": "llm_call",
        "status": "success",
        "context": _json_safe(context),
        "request": _json_safe(request),
        "response": _json_safe(response),
        "error": None,
        "scores": {},
        "annotations": {},
        "replay": {
            "api_mode": context.get("api_mode"),
            "provider": context.get("provider"),
            "model": context.get("model"),
            "base_url": context.get("base_url"),
            "request": _json_safe(request),
        },
    }
    return write_interaction_record(record)


def capture_llm_error(request: Dict[str, Any], error: BaseException, **context: Any) -> Optional[Path]:
    if not capture_enabled():
        return None
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "schema_version": _SCHEMA_VERSION,
        "record_id": str(uuid.uuid4()),
        "captured_at": now,
        "unix_time": time.time(),
        "kind": "llm_call",
        "status": "error",
        "context": _json_safe(context),
        "request": _json_safe(request),
        "response": None,
        "error": {
            "type": f"{error.__class__.__module__}.{error.__class__.__name__}",
            "message": str(error),
            "traceback": traceback.format_exception(type(error), error, error.__traceback__),
        },
        "scores": {},
        "annotations": {},
        "replay": {
            "api_mode": context.get("api_mode"),
            "provider": context.get("provider"),
            "model": context.get("model"),
            "base_url": context.get("base_url"),
            "request": _json_safe(request),
        },
    }
    return write_interaction_record(record)
