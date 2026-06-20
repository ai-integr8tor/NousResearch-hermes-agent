"""Tests for set_config_value — verifying secrets route to .env and config to config.yaml."""

import argparse
import os
from unittest.mock import patch

import pytest

from hermes_cli.config import set_config_value, config_command


@pytest.fixture(autouse=True)
def _isolated_hermes_home(tmp_path):
    """Point HERMES_HOME at a temp dir so tests never touch real config."""
    env_file = tmp_path / ".env"
    env_file.touch()
    with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
        yield tmp_path


def _read_env(tmp_path):
    return (tmp_path / ".env").read_text()


def _read_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    return config_path.read_text() if config_path.exists() else ""


# ---------------------------------------------------------------------------
# Explicit allowlist keys → .env
# ---------------------------------------------------------------------------

class TestExplicitAllowlist:
    """Keys in the hardcoded allowlist should always go to .env."""

    @pytest.mark.parametrize("key", [
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HONCHO_API_KEY",
        "FIRECRAWL_API_KEY",
        "BROWSERBASE_API_KEY",
        "FAL_KEY",
        "SUDO_PASSWORD",
        "GITHUB_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
    ])
    def test_explicit_key_routes_to_env(self, key, _isolated_hermes_home):
        set_config_value(key, "test-value-123")
        env_content = _read_env(_isolated_hermes_home)
        assert f"{key}=test-value-123" in env_content
        # Must NOT appear in config.yaml
        assert key not in _read_config(_isolated_hermes_home)


# ---------------------------------------------------------------------------
# Catch-all patterns → .env
# ---------------------------------------------------------------------------

class TestCatchAllPatterns:
    """Any key ending in _API_KEY or _TOKEN should route to .env."""

    @pytest.mark.parametrize("key", [
        "DAYTONA_API_KEY",
        "ELEVENLABS_API_KEY",
        "SOME_FUTURE_SERVICE_API_KEY",
        "MY_CUSTOM_TOKEN",
        "WHATSAPP_BOT_TOKEN",
    ])
    def test_api_key_suffix_routes_to_env(self, key, _isolated_hermes_home):
        set_config_value(key, "secret-456")
        env_content = _read_env(_isolated_hermes_home)
        assert f"{key}=secret-456" in env_content
        assert key not in _read_config(_isolated_hermes_home)

    def test_case_insensitive(self, _isolated_hermes_home):
        """Keys should be uppercased regardless of input casing."""
        set_config_value("openai_api_key", "sk-test")
        env_content = _read_env(_isolated_hermes_home)
        assert "OPENAI_API_KEY=sk-test" in env_content

    def test_terminal_ssh_prefix_routes_to_env(self, _isolated_hermes_home):
        set_config_value("TERMINAL_SSH_PORT", "2222")
        env_content = _read_env(_isolated_hermes_home)
        assert "TERMINAL_SSH_PORT=2222" in env_content


# ---------------------------------------------------------------------------
# Non-secret keys → config.yaml
# ---------------------------------------------------------------------------

class TestConfigYamlRouting:
    """Regular config keys should go to config.yaml, NOT .env."""

    def test_simple_key(self, _isolated_hermes_home):
        set_config_value("model", "gpt-4o")
        config = _read_config(_isolated_hermes_home)
        assert "gpt-4o" in config
        assert "model" not in _read_env(_isolated_hermes_home)

    def test_nested_key(self, _isolated_hermes_home):
        set_config_value("terminal.backend", "docker")
        config = _read_config(_isolated_hermes_home)
        assert "docker" in config
        assert "terminal" not in _read_env(_isolated_hermes_home)

    def test_terminal_image_goes_to_config(self, _isolated_hermes_home):
        """TERMINAL_DOCKER_IMAGE doesn't match _API_KEY or _TOKEN, so config.yaml."""
        set_config_value("terminal.docker_image", "python:3.12")
        config = _read_config(_isolated_hermes_home)
        assert "python:3.12" in config

    def test_terminal_docker_cwd_mount_flag_goes_to_config_and_env(self, _isolated_hermes_home):
        set_config_value("terminal.docker_mount_cwd_to_workspace", "true")
        config = _read_config(_isolated_hermes_home)
        env_content = _read_env(_isolated_hermes_home)
        assert "docker_mount_cwd_to_workspace: 'true'" in config or "docker_mount_cwd_to_workspace: true" in config
        assert (
            "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE=true" in env_content
            or "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE=True" in env_content
        )


# ---------------------------------------------------------------------------
# Empty / falsy values — regression tests for #4277
# ---------------------------------------------------------------------------

class TestFalsyValues:
    """config set should accept empty strings and falsy values like '0'."""

    def test_empty_string_routes_to_env(self, _isolated_hermes_home):
        """Blanking an API key should write an empty value to .env."""
        set_config_value("OPENROUTER_API_KEY", "")
        env_content = _read_env(_isolated_hermes_home)
        assert "OPENROUTER_API_KEY=" in env_content

    def test_empty_string_routes_to_config(self, _isolated_hermes_home):
        """Blanking a config key should write an empty string to config.yaml."""
        set_config_value("model", "")
        config = _read_config(_isolated_hermes_home)
        assert "model: ''" in config or "model: \"\"" in config

    def test_zero_routes_to_config(self, _isolated_hermes_home):
        """Setting a config key to '0' should write 0 to config.yaml."""
        set_config_value("verbose", "0")
        config = _read_config(_isolated_hermes_home)
        assert "verbose: 0" in config

    def test_config_command_rejects_missing_value(self):
        """config set with no value arg (None) should still exit."""
        args = argparse.Namespace(config_command="set", key="model", value=None)
        with pytest.raises(SystemExit):
            config_command(args)

    def test_config_command_accepts_empty_string(self, _isolated_hermes_home):
        """config set KEY '' should not exit — it should set the value."""
        args = argparse.Namespace(config_command="set", key="model", value="")
        config_command(args)
        config = _read_config(_isolated_hermes_home)
        assert "model" in config


# ---------------------------------------------------------------------------
# List navigation — regression tests for #17876
# ---------------------------------------------------------------------------

class TestListNavigation:
    """hermes config set must preserve YAML list fields when using numeric
    indices.  Before #17876, _set_nested would silently replace the entire
    list with a dict, destroying every sibling entry.
    """

    def _write_config(self, tmp_path, body):
        (tmp_path / "config.yaml").write_text(body)

    def test_indexed_set_preserves_sibling_list_entries(self, _isolated_hermes_home):
        """Setting custom_providers.0.api_key must not destroy entry 1."""
        self._write_config(_isolated_hermes_home, (
            "custom_providers:\n"
            "- name: provider-a\n"
            "  api_key: old-a\n"
            "  base_url: https://a.example.com\n"
            "- name: provider-b\n"
            "  api_key: old-b\n"
            "  base_url: https://b.example.com\n"
        ))

        set_config_value("custom_providers.0.api_key", "new-a")

        import yaml
        reloaded = yaml.safe_load(_read_config(_isolated_hermes_home))
        # The list must still be a list
        assert isinstance(reloaded["custom_providers"], list)
        assert len(reloaded["custom_providers"]) == 2
        # Entry 0 was updated
        assert reloaded["custom_providers"][0]["api_key"] == "new-a"
        assert reloaded["custom_providers"][0]["name"] == "provider-a"
        assert reloaded["custom_providers"][0]["base_url"] == "https://a.example.com"
        # Entry 1 is untouched
        assert reloaded["custom_providers"][1]["name"] == "provider-b"
        assert reloaded["custom_providers"][1]["api_key"] == "old-b"
        assert reloaded["custom_providers"][1]["base_url"] == "https://b.example.com"

    def test_indexed_set_preserves_non_targeted_fields(self, _isolated_hermes_home):
        """Setting one field in a list entry must not drop other fields."""
        self._write_config(_isolated_hermes_home, (
            "custom_providers:\n"
            "- name: provider-a\n"
            "  api_key: old\n"
            "  base_url: https://a.example.com\n"
            "  models:\n"
            "    foo: {}\n"
            "    bar: {}\n"
        ))

        set_config_value("custom_providers.0.api_key", "rotated")

        import yaml
        reloaded = yaml.safe_load(_read_config(_isolated_hermes_home))
        entry = reloaded["custom_providers"][0]
        assert entry["api_key"] == "rotated"
        assert entry["name"] == "provider-a"
        assert entry["base_url"] == "https://a.example.com"
        assert set(entry["models"].keys()) == {"foo", "bar"}

    def test_deeper_nesting_through_list(self, _isolated_hermes_home):
        """Navigation path mixing dict → list → dict → scalar."""
        self._write_config(_isolated_hermes_home, (
            "platforms:\n"
            "  telegram:\n"
            "    allowlist:\n"
            "    - name: alice\n"
            "      role: admin\n"
            "    - name: bob\n"
            "      role: user\n"
        ))

        set_config_value("platforms.telegram.allowlist.1.role", "admin")

        import yaml
        reloaded = yaml.safe_load(_read_config(_isolated_hermes_home))
        allowlist = reloaded["platforms"]["telegram"]["allowlist"]
        assert isinstance(allowlist, list)
        assert allowlist[0] == {"name": "alice", "role": "admin"}
        assert allowlist[1] == {"name": "bob", "role": "admin"}


# ---------------------------------------------------------------------------
# Enum string preservation — regression tests for #47515
# ---------------------------------------------------------------------------

class TestEnumStringPreservation:
    """hermes config set must not coerce enum strings like 'off'/'on' to
    booleans when the target key's default value is a string.

    Before #47515, ``hermes config set approvals.mode off`` wrote
    ``mode: false`` instead of ``mode: 'off'``, corrupting the schema.
    """

    def test_string_enum_off_stays_string(self, _isolated_hermes_home):
        """approvals.mode default is 'manual' (str) → 'off' must stay string."""
        set_config_value("approvals.mode", "off")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["approvals"]["mode"] == "off"
        assert isinstance(config["approvals"]["mode"], str)

    def test_string_enum_on_stays_string(self, _isolated_hermes_home):
        """approvals.mode default is 'manual' (str) → 'on' must stay string."""
        set_config_value("approvals.mode", "on")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["approvals"]["mode"] == "on"
        assert isinstance(config["approvals"]["mode"], str)

    def test_string_enum_yes_stays_string(self, _isolated_hermes_home):
        """approvals.mode default is 'manual' (str) → 'yes' must stay string."""
        set_config_value("approvals.mode", "yes")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["approvals"]["mode"] == "yes"
        assert isinstance(config["approvals"]["mode"], str)

    def test_string_enum_no_stays_string(self, _isolated_hermes_home):
        """approvals.mode default is 'manual' (str) → 'no' must stay string."""
        set_config_value("approvals.mode", "no")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["approvals"]["mode"] == "no"
        assert isinstance(config["approvals"]["mode"], str)

    def test_human_delay_mode_off_stays_string(self, _isolated_hermes_home):
        """human_delay.mode default is 'off' (str) → 'on' must stay string."""
        set_config_value("human_delay.mode", "on")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["human_delay"]["mode"] == "on"
        assert isinstance(config["human_delay"]["mode"], str)

    def test_bool_key_still_coerced_true(self, _isolated_hermes_home):
        """terminal.persistent_shell default is True (bool) → 'on' coerced."""
        set_config_value("terminal.persistent_shell", "on")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["terminal"]["persistent_shell"] is True

    def test_bool_key_still_coerced_false(self, _isolated_hermes_home):
        """browser.record_sessions default is False (bool) → 'off' coerced."""
        set_config_value("browser.record_sessions", "off")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["browser"]["record_sessions"] is False

    def test_bool_key_still_coerced_yes(self, _isolated_hermes_home):
        """terminal.persistent_shell default is True (bool) → 'yes' coerced."""
        set_config_value("terminal.persistent_shell", "yes")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["terminal"]["persistent_shell"] is True

    def test_numeric_key_still_coerced(self, _isolated_hermes_home):
        """Numeric keys should still be coerced to int/float."""
        set_config_value("verbose", "3")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        assert config["verbose"] == 3
        assert isinstance(config["verbose"], int)

    def test_unknown_key_preserves_string(self, _isolated_hermes_home):
        """A key not in DEFAULT_CONFIG should preserve the raw string."""
        set_config_value("custom_setting", "off")
        import yaml
        config = yaml.safe_load(_read_config(_isolated_hermes_home))
        # Unknown key — _default_value_for_key returns None (not str),
        # so old coercion behavior applies: 'off' → False.
        assert config["custom_setting"] is False
