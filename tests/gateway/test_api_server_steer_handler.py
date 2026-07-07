"""Direct tests for /v1/runs/{run_id}/steer without opening a test socket."""

from unittest.mock import MagicMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


class _Request:
    def __init__(self, run_id: str, payload=None, headers=None, json_error: Exception | None = None):
        self.match_info = {"run_id": run_id}
        self.headers = headers or {}
        self.method = "POST"
        self.path_qs = f"/v1/runs/{run_id}/steer"
        self.remote = "127.0.0.1"
        self.transport = None
        self._payload = payload
        self._json_error = json_error

    async def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def _adapter(api_key: str = "") -> APIServerAdapter:
    extra = {"key": api_key} if api_key else {}
    return APIServerAdapter(PlatformConfig(enabled=True, extra=extra))


@pytest.mark.asyncio
async def test_steer_handler_accepts_active_run():
    adapter = _adapter()
    run_id = "run_live"
    agent = MagicMock()
    agent.steer.return_value = True
    adapter._run_statuses[run_id] = {"run_id": run_id, "status": "running"}
    adapter._active_run_agents[run_id] = agent

    response = await adapter._handle_steer_run(
        _Request(run_id, {"text": "  also check auth  "}),
    )

    assert response.status == 200
    assert '"status": "accepted"' in response.text
    agent.steer.assert_called_once_with("also check auth")
    assert adapter._run_statuses[run_id]["last_event"] == "run.steered"


@pytest.mark.asyncio
async def test_steer_handler_rejects_empty_payload():
    adapter = _adapter()
    run_id = "run_empty"
    agent = MagicMock()
    adapter._run_statuses[run_id] = {"run_id": run_id, "status": "running"}
    adapter._active_run_agents[run_id] = agent

    response = await adapter._handle_steer_run(_Request(run_id, {"text": "  "}))

    assert response.status == 400
    assert '"status": "empty_payload"' in response.text
    agent.steer.assert_not_called()


@pytest.mark.asyncio
async def test_steer_handler_reports_missing_run():
    adapter = _adapter()

    response = await adapter._handle_steer_run(_Request("run_missing", {"text": "hello"}))

    assert response.status == 404
    assert '"status": "run_not_found"' in response.text


@pytest.mark.asyncio
async def test_steer_handler_reports_completed_run():
    adapter = _adapter()
    run_id = "run_done"
    adapter._run_statuses[run_id] = {"run_id": run_id, "status": "completed"}

    response = await adapter._handle_steer_run(_Request(run_id, {"text": "too late"}))

    assert response.status == 409
    assert '"status": "run_completed"' in response.text


@pytest.mark.asyncio
async def test_steer_handler_requires_auth():
    adapter = _adapter(api_key="sk-secret")
    run_id = "run_auth"
    agent = MagicMock()
    adapter._run_statuses[run_id] = {"run_id": run_id, "status": "running"}
    adapter._active_run_agents[run_id] = agent

    response = await adapter._handle_steer_run(_Request(run_id, {"text": "hello"}))

    assert response.status == 401
    agent.steer.assert_not_called()
