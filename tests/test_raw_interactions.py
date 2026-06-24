import json
from types import SimpleNamespace

import pytest

from hermes_cli.middleware import run_llm_execution_middleware


@pytest.fixture(autouse=True)
def capture_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_CAPTURE_INTERACTIONS", "1")
    monkeypatch.setenv("HERMES_CAPTURE_DIR", str(tmp_path))
    monkeypatch.delenv("HERMES_CAPTURE_GZIP", raising=False)
    return tmp_path


def _read_records(path):
    files = list(path.glob("*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_run_llm_execution_middleware_captures_success(capture_env):
    request = {"model": "test-model", "messages": [{"role": "user", "content": "make a dice game"}]}

    response = run_llm_execution_middleware(
        request,
        lambda req: SimpleNamespace(id="resp-1", output_text="ok", echoed=req),
        original_request={"model": "original", "messages": request["messages"]},
        task_id="task-1",
        turn_id="turn-1",
        api_request_id="turn-1:api:1",
        session_id="session-1",
        platform="telegram",
        model="test-model",
        provider="test-provider",
        base_url="https://example.invalid/v1",
        api_mode="chat_completions",
        api_call_count=1,
    )

    assert response.output_text == "ok"
    [record] = _read_records(capture_env)
    assert record["schema_version"] == "hermes.raw_interaction.v1"
    assert record["kind"] == "llm_call"
    assert record["status"] == "success"
    assert record["context"]["session_id"] == "session-1"
    assert record["request"]["model"] == "original"
    assert record["response"]["attributes"]["output_text"] == "ok"
    assert record["scores"] == {}
    assert record["annotations"] == {}
    assert record["replay"]["request"] == record["request"]


def test_run_llm_execution_middleware_captures_error(capture_env):
    request = {"model": "test-model", "messages": [{"role": "user", "content": "fail"}]}

    with pytest.raises(RuntimeError, match="provider exploded"):
        run_llm_execution_middleware(
            request,
            lambda req: (_ for _ in ()).throw(RuntimeError("provider exploded")),
            task_id="task-1",
            turn_id="turn-1",
            api_request_id="turn-1:api:1",
            session_id="session-1",
            platform="telegram",
            model="test-model",
            provider="test-provider",
            base_url="https://example.invalid/v1",
            api_mode="chat_completions",
            api_call_count=1,
        )

    [record] = _read_records(capture_env)
    assert record["status"] == "error"
    assert record["request"] == request
    assert record["error"]["type"] == "builtins.RuntimeError"
    assert record["error"]["message"] == "provider exploded"
    assert record["replay"]["provider"] == "test-provider"
