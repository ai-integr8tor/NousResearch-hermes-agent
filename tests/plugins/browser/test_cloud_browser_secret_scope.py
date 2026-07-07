import pytest

from agent import secret_scope
from agent.secret_scope import UnscopedSecretError
from plugins.browser.browser_use.provider import BrowserUseBrowserProvider
from plugins.browser.browserbase.provider import BrowserbaseBrowserProvider
from plugins.browser.firecrawl.provider import FirecrawlBrowserProvider


@pytest.fixture(autouse=True)
def _reset_secret_scope():
    secret_scope.set_multiplex_active(False)
    yield
    secret_scope.set_multiplex_active(False)


def test_browserbase_uses_profile_secret_scope_not_process_env(monkeypatch):
    monkeypatch.setenv("BROWSERBASE_API_KEY", "foreign-key")
    monkeypatch.setenv("BROWSERBASE_PROJECT_ID", "foreign-project")
    monkeypatch.setenv("BROWSERBASE_BASE_URL", "https://foreign.example")

    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({
        "BROWSERBASE_API_KEY": "scoped-key",
        "BROWSERBASE_PROJECT_ID": "scoped-project",
        "BROWSERBASE_BASE_URL": "https://scoped.example/",
    })
    try:
        config = BrowserbaseBrowserProvider()._get_config_or_none()
    finally:
        secret_scope.reset_secret_scope(token)

    assert config == {
        "api_key": "scoped-key",
        "project_id": "scoped-project",
        "base_url": "https://scoped.example",
    }


def test_browser_use_uses_profile_secret_scope_not_process_env(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "foreign-key")

    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({"BROWSER_USE_API_KEY": "scoped-key"})
    try:
        config = BrowserUseBrowserProvider()._get_config_or_none(refresh_token=False)
    finally:
        secret_scope.reset_secret_scope(token)

    assert config == {
        "api_key": "scoped-key",
        "base_url": "https://api.browser-use.com/api/v3",
        "managed_mode": False,
    }


def test_firecrawl_uses_profile_secret_scope_not_process_env(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "foreign-key")
    monkeypatch.setenv("FIRECRAWL_API_URL", "https://foreign.example")

    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({
        "FIRECRAWL_API_KEY": "scoped-key",
        "FIRECRAWL_API_URL": "https://scoped.example",
    })
    try:
        provider = FirecrawlBrowserProvider()
        assert provider.is_available() is True
        assert provider._api_url() == "https://scoped.example"
        assert provider._headers()["Authorization"] == "Bearer scoped-key"
    finally:
        secret_scope.reset_secret_scope(token)


def test_cloud_browser_provider_unscoped_multiplex_read_fails_closed(monkeypatch):
    monkeypatch.setenv("BROWSERBASE_API_KEY", "foreign-key")
    monkeypatch.setenv("BROWSERBASE_PROJECT_ID", "foreign-project")

    secret_scope.set_multiplex_active(True)

    with pytest.raises(UnscopedSecretError):
        BrowserbaseBrowserProvider()._get_config_or_none()
