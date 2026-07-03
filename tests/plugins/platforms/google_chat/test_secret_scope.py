from types import SimpleNamespace

import pytest

from agent import secret_scope
from agent.secret_scope import UnscopedSecretError
from plugins.platforms.google_chat import adapter as google_chat


@pytest.fixture(autouse=True)
def _reset_secret_scope():
    secret_scope.set_multiplex_active(False)
    yield
    secret_scope.set_multiplex_active(False)


def test_env_enablement_uses_profile_secret_scope_not_process_env(monkeypatch):
    monkeypatch.setattr(google_chat, "check_google_chat_requirements", lambda: True)
    monkeypatch.setenv("GOOGLE_CHAT_PROJECT_ID", "foreign-project")
    monkeypatch.setenv(
        "GOOGLE_CHAT_SUBSCRIPTION_NAME",
        "projects/foreign-project/subscriptions/foreign-sub",
    )
    monkeypatch.setenv("GOOGLE_CHAT_SERVICE_ACCOUNT_JSON", '{"project_id":"foreign"}')
    monkeypatch.setenv("GOOGLE_CHAT_HOME_CHANNEL", "spaces/FOREIGN")

    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({
        "GOOGLE_CHAT_PROJECT_ID": "scoped-project",
        "GOOGLE_CHAT_SUBSCRIPTION_NAME": "projects/scoped-project/subscriptions/scoped-sub",
        "GOOGLE_CHAT_SERVICE_ACCOUNT_JSON": '{"project_id":"scoped"}',
        "GOOGLE_CHAT_HOME_CHANNEL": "spaces/SCOPED",
        "GOOGLE_CHAT_HOME_CHANNEL_NAME": "Scoped Home",
    })
    try:
        seed = google_chat._env_enablement()
    finally:
        secret_scope.reset_secret_scope(token)

    assert seed == {
        "project_id": "scoped-project",
        "subscription_name": "projects/scoped-project/subscriptions/scoped-sub",
        "service_account_json": '{"project_id":"scoped"}',
        "home_channel": {"chat_id": "spaces/SCOPED", "name": "Scoped Home"},
    }


def test_env_enablement_unscoped_multiplex_read_fails_closed(monkeypatch):
    monkeypatch.setattr(google_chat, "check_google_chat_requirements", lambda: True)
    monkeypatch.setenv("GOOGLE_CHAT_PROJECT_ID", "foreign-project")
    monkeypatch.setenv(
        "GOOGLE_CHAT_SUBSCRIPTION_NAME",
        "projects/foreign-project/subscriptions/foreign-sub",
    )

    secret_scope.set_multiplex_active(True)

    with pytest.raises(UnscopedSecretError):
        google_chat._env_enablement()


def test_load_sa_credentials_uses_profile_secret_scope_not_process_env(monkeypatch):
    class _FakeCredentials:
        @staticmethod
        def from_service_account_info(info, scopes):
            return {"info": info, "scopes": scopes}

    monkeypatch.setattr(
        google_chat,
        "service_account",
        SimpleNamespace(Credentials=_FakeCredentials),
    )
    monkeypatch.setenv("GOOGLE_CHAT_SERVICE_ACCOUNT_JSON", '{"project_id":"foreign"}')

    instance = google_chat.GoogleChatAdapter.__new__(google_chat.GoogleChatAdapter)
    instance.config = SimpleNamespace(extra={})
    secret_scope.set_multiplex_active(True)
    token = secret_scope.set_secret_scope({
        "GOOGLE_CHAT_SERVICE_ACCOUNT_JSON": '{"project_id":"scoped"}'
    })
    try:
        credentials = google_chat.GoogleChatAdapter._load_sa_credentials(instance)
    finally:
        secret_scope.reset_secret_scope(token)

    assert credentials["info"] == {"project_id": "scoped"}
    assert credentials["scopes"] == google_chat._CHAT_SCOPES
