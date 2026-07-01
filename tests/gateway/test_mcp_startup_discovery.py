import logging
import sys
import threading
import types


def test_startup_mcp_discovery_runs_in_daemon_thread(monkeypatch):
    from gateway import run as gateway_run

    started = threading.Event()
    release = threading.Event()

    def discover_mcp_tools():
        started.set()
        release.wait(timeout=2)
        return ["mcp_example_tool"]

    monkeypatch.delenv("HERMES_GATEWAY_SKIP_STARTUP_MCP_DISCOVERY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "tools.mcp_tool",
        types.SimpleNamespace(discover_mcp_tools=discover_mcp_tools),
    )

    thread = gateway_run._start_gateway_mcp_discovery_thread()

    assert thread is not None
    assert thread.daemon is True
    assert thread.name == "gateway-mcp-discovery"
    assert started.wait(timeout=1)
    assert thread.is_alive()

    release.set()
    thread.join(timeout=1)
    assert not thread.is_alive()


def test_startup_mcp_discovery_skip_env(monkeypatch):
    from gateway import run as gateway_run

    called = False

    def discover_mcp_tools():
        nonlocal called
        called = True
        return []

    monkeypatch.setenv("HERMES_GATEWAY_SKIP_STARTUP_MCP_DISCOVERY", "1")
    monkeypatch.setitem(
        sys.modules,
        "tools.mcp_tool",
        types.SimpleNamespace(discover_mcp_tools=discover_mcp_tools),
    )

    thread = gateway_run._start_gateway_mcp_discovery_thread()

    assert thread is None
    assert called is False


def test_startup_mcp_discovery_logs_completion(monkeypatch, caplog):
    from gateway import run as gateway_run

    def discover_mcp_tools():
        return ["mcp_one", "mcp_two"]

    monkeypatch.delenv("HERMES_GATEWAY_SKIP_STARTUP_MCP_DISCOVERY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "tools.mcp_tool",
        types.SimpleNamespace(discover_mcp_tools=discover_mcp_tools),
    )

    with caplog.at_level(logging.INFO, logger=gateway_run.__name__):
        thread = gateway_run._start_gateway_mcp_discovery_thread()
        assert thread is not None
        thread.join(timeout=1)

    assert "Startup MCP discovery completed in background (2 tool(s))" in caplog.text
