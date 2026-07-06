from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest_env_names(plugin: str) -> set[str]:
    manifest_path = REPO_ROOT / "plugins" / "platforms" / plugin / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    env_names: set[str] = set()
    for section in ("requires_env", "optional_env"):
        for entry in manifest.get(section) or []:
            if isinstance(entry, str):
                env_names.add(entry)
            elif isinstance(entry, dict) and entry.get("name"):
                env_names.add(str(entry["name"]))
    return env_names


def test_matrix_plugin_metadata_advertises_home_room_env_vars():
    names = _manifest_env_names("matrix")

    assert "MATRIX_HOME_ROOM" in names
    assert "MATRIX_HOME_ROOM_NAME" in names
    assert "MATRIX_HOME_ROOM_THREAD_ID" in names
    assert "MATRIX_HOME_CHANNEL" not in names
    assert "MATRIX_HOME_CHANNEL_NAME" not in names


def test_matrix_env_docs_advertise_home_room_env_vars():
    docs_path = (
        REPO_ROOT / "website" / "docs" / "reference" / "environment-variables.md"
    )
    docs = docs_path.read_text(encoding="utf-8")

    assert "`MATRIX_HOME_ROOM`" in docs
    assert "`MATRIX_HOME_ROOM_NAME`" in docs
    assert "`MATRIX_HOME_ROOM_THREAD_ID`" in docs
    assert "`MATRIX_HOME_CHANNEL`" not in docs
    assert "`MATRIX_HOME_CHANNEL_NAME`" not in docs


def test_config_env_registry_uses_matrix_home_room_env_vars():
    from hermes_cli.config import OPTIONAL_ENV_VARS

    assert "MATRIX_HOME_ROOM" in OPTIONAL_ENV_VARS
    assert "MATRIX_HOME_ROOM_NAME" in OPTIONAL_ENV_VARS
    assert "MATRIX_HOME_ROOM_THREAD_ID" in OPTIONAL_ENV_VARS
    assert "MATRIX_HOME_CHANNEL" not in OPTIONAL_ENV_VARS
    assert "MATRIX_HOME_CHANNEL_NAME" not in OPTIONAL_ENV_VARS
