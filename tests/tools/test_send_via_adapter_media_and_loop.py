"""Tests for the platform-agnostic gateway-send fixes in
``tools.send_message_tool``:

1. In-process media routing — ``_send_via_adapter`` must actually deliver media
   through the live adapter's typed media methods (not silently drop it), with a
   capability gate so non-overriding plugins never post a base placeholder.
2. Cross-loop send marshaling — ``_await_on_adapter_loop`` must run the send on
   the adapter's own (gateway) loop, fixing the production ``RuntimeError:
   Timeout context manager should be used inside a task``.

These use the real ``MattermostAdapter`` only as a convenient *concrete*
file-capable adapter (it overrides the typed media methods); the code under
test is platform-agnostic.
"""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, patch

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import SendResult


def _make_adapter():
    """A real MattermostAdapter (concrete file-capable adapter) with mocked config."""
    from plugins.platforms.mattermost.adapter import MattermostAdapter
    config = PlatformConfig(
        enabled=True,
        token="test-token",
        extra={"url": "https://mm.example.com"},
    )
    return MattermostAdapter(config)


# ---------------------------------------------------------------------------
# In-process media propagation through the live adapter path
# ---------------------------------------------------------------------------

class TestSendViaAdapterMediaPropagation:
    """``_send_via_adapter``'s live in-process path must ACTUALLY deliver media,
    not silently drop it. When a live adapter is present and media is present it
    routes each canonical ``(path, is_voice)`` tuple through the adapter's typed
    media methods (the same path ``cron.scheduler._send_media_via_adapter``
    uses); text-only sends keep using the live ``adapter.send`` fast path."""

    def _patch_runner(self, adapter):
        """Patch gateway.run._gateway_runner_ref to return a runner exposing
        ``adapters`` containing the given adapter for Platform.MATTERMOST."""
        runner = SimpleNamespace(adapters={Platform.MATTERMOST: adapter})
        import gateway.run as grun
        return patch.object(grun, "_gateway_runner_ref", lambda: runner)

    @pytest.mark.asyncio
    async def test_media_actually_uploads_via_real_adapter(self, tmp_path):
        """Drive the REAL MattermostAdapter delivery path with a canonical
        ``[(path, False)]`` tuple, mocking only the network primitives
        (``_upload_file`` / ``_api_post``). An upload MUST actually be
        attempted — this is the empirical proof the tuple is not dropped."""
        from tools.send_message_tool import _send_via_adapter

        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")

        adapter = _make_adapter()
        adapter._upload_file = AsyncMock(return_value="file_id_1")
        adapter._api_post = AsyncMock(return_value={"id": "post_1"})
        adapter.send = AsyncMock(return_value=SendResult(success=True, message_id="text_post"))

        pconfig = SimpleNamespace(token="tok", extra={"url": "https://mm.example.com"})
        media = [(str(img), False)]

        with self._patch_runner(adapter):
            result = await _send_via_adapter(
                Platform.MATTERMOST, pconfig, "chan_1", "see attached",
                media_files=media,
            )

        assert result.get("success") is True
        adapter._upload_file.assert_awaited_once()
        up_args = adapter._upload_file.await_args
        assert up_args.args[0] == "chan_1"  # channel_id
        adapter._api_post.assert_awaited_once()
        post_payload = adapter._api_post.await_args.args[1]
        assert post_payload["channel_id"] == "chan_1"
        assert post_payload["file_ids"] == ["file_id_1"]

    @pytest.mark.asyncio
    async def test_media_routes_to_document_for_non_image(self, tmp_path):
        """A non-image file routes through ``send_document`` → ``_upload_file``
        (still a real upload, proving extension-based dispatch works)."""
        from tools.send_message_tool import _send_via_adapter

        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")

        adapter = _make_adapter()
        adapter._upload_file = AsyncMock(return_value="file_pdf")
        adapter._api_post = AsyncMock(return_value={"id": "post_pdf"})
        adapter.send = AsyncMock(return_value=SendResult(success=True, message_id="t"))

        pconfig = SimpleNamespace(token="tok", extra={"url": "https://mm.example.com"})

        with self._patch_runner(adapter):
            result = await _send_via_adapter(
                Platform.MATTERMOST, pconfig, "chan_1", "doc", media_files=[(str(doc), False)],
            )

        assert result.get("success") is True
        adapter._upload_file.assert_awaited_once()
        assert adapter._api_post.await_args.args[1]["file_ids"] == ["file_pdf"]

    @pytest.mark.asyncio
    async def test_text_only_still_uses_live_adapter(self):
        """Byte-identical text-only hot path: no media → live adapter.send,
        and the media-dispatch helper is never touched."""
        from tools.send_message_tool import _send_via_adapter

        live_result = SimpleNamespace(success=True, message_id="live1", error=None)
        live_adapter = SimpleNamespace(
            send=AsyncMock(return_value=live_result),
            send_image_file=AsyncMock(),
            send_document=AsyncMock(),
            send_voice=AsyncMock(),
            send_video=AsyncMock(),
        )

        with self._patch_runner(live_adapter):
            result = await _send_via_adapter(
                Platform.MATTERMOST, SimpleNamespace(token="tok", extra={}),
                "chan_1", "hello", media_files=None,
            )

        assert result.get("success") is True
        assert result.get("message_id") == "live1"
        live_adapter.send.assert_awaited_once()
        live_adapter.send_image_file.assert_not_called()
        live_adapter.send_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_overriding_adapter_does_not_post_placeholder(self, tmp_path):
        """A file-capable plugin adapter that does NOT override the base media
        methods (e.g. irc / ntfy / simplex) must NOT have media routed to the
        BASE placeholder method on the in-process path.

        The base ``send_image_file`` / ``send_document`` post a text placeholder
        like ``📎 File: <local-path>`` via ``self.send`` — leaking a local
        filesystem path into the channel. The capability gate must skip such
        adapters entirely on this path, preserving the prior behavior."""
        from gateway.platforms.base import BasePlatformAdapter
        from tools.send_message_tool import _deliver_media_via_live_adapter

        class _NonOverridingAdapter(BasePlatformAdapter):
            def __init__(self):
                self.platform = Platform.MATTERMOST
                # Spy on the placeholder sink: the base media methods call
                # self.send(...). It must never be invoked here.
                self.send_calls = []

            async def connect(self):
                return True

            async def disconnect(self):
                return None

            async def send(self, *args, **kwargs):
                self.send_calls.append((args, kwargs))
                return SimpleNamespace(success=True, message_id="x")

            async def get_chat_info(self, chat_id):
                return {}

        adapter = _NonOverridingAdapter()

        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"%PDF-1.4 fake")

        result = await _deliver_media_via_live_adapter(
            adapter, Platform.MATTERMOST, "chan_1",
            [(str(img), False), (str(doc), False)],
        )

        assert not (isinstance(result, dict) and result.get("error"))
        assert adapter.send_calls == []

    @pytest.mark.asyncio
    async def test_overriding_adapter_still_delivers_media(self, tmp_path):
        """The capability gate must NOT regress a genuinely file-capable adapter:
        the real MattermostAdapter (which overrides the media methods) still
        uploads its media via the in-process dispatch path."""
        from tools.send_message_tool import _deliver_media_via_live_adapter

        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")

        adapter = _make_adapter()
        adapter._upload_file = AsyncMock(return_value="file_id_1")
        adapter._api_post = AsyncMock(return_value={"id": "post_1"})

        result = await _deliver_media_via_live_adapter(
            adapter, Platform.MATTERMOST, "chan_1", [(str(img), False)],
        )

        assert not (isinstance(result, dict) and result.get("error"))
        adapter._upload_file.assert_awaited_once()
        assert adapter._api_post.await_args.args[1]["file_ids"] == ["file_id_1"]

    @pytest.mark.asyncio
    async def test_media_falls_back_to_standalone_when_no_runner(self, tmp_path):
        """With no live runner, media still flows through the standalone
        sender carrying the canonical tuple unchanged (the out-of-process
        cron path)."""
        from tools.send_message_tool import _send_via_adapter

        standalone = AsyncMock(return_value={"success": True, "message_id": "p3"})
        entry = SimpleNamespace(standalone_sender_fn=standalone, max_message_length=4000)
        pconfig = SimpleNamespace(token="tok", extra={})
        media = [("/tmp/doc.pdf", False)]

        import gateway.run as grun
        with patch.object(grun, "_gateway_runner_ref", lambda: None), \
             patch("gateway.platform_registry.platform_registry.get", return_value=entry):
            result = await _send_via_adapter(
                Platform.MATTERMOST, pconfig, "chan_1", "doc", media_files=media,
            )

        assert result.get("success") is True
        standalone.assert_awaited_once()
        assert standalone.await_args.kwargs.get("media_files") == media


# ---------------------------------------------------------------------------
# Cross-loop send dispatch — _await_on_adapter_loop marshaling
# ---------------------------------------------------------------------------

class TestSendViaAdapterLoopContext:
    """Regression for the live failure ``Timeout context manager should be used
    inside a task``.

    A live adapter's aiohttp ``ClientSession`` is created on, and bound to, the
    gateway event loop. The ``send_message`` tool, however, runs each send via
    ``model_tools._run_async`` which — when already inside the gateway loop —
    spins up a *fresh worker loop on a separate thread* and drives the send
    coroutine there. A plain ``await adapter.send(...)`` then enters the
    gateway-loop-bound session's timeout context manager while running on the
    worker loop, where ``asyncio.current_task()`` of the session's loop is
    ``None`` → aiohttp raises ``RuntimeError: Timeout context manager should be
    used inside a task``.

    These tests stand up a real second ('gateway') loop on its own thread,
    create a real ``aiohttp.ClientSession`` bound to it, and drive the REAL
    ``_send_via_adapter`` dispatch from a different worker loop — exactly the
    production topology. They do NOT mock the async/timeout layer away."""

    def _start_gateway_loop(self):
        loop = asyncio.new_event_loop()
        ready = threading.Event()

        def _run():
            asyncio.set_event_loop(loop)
            loop.call_soon(ready.set)
            loop.run_forever()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        ready.wait(timeout=5)
        return loop

    def _stop_gateway_loop(self, loop):
        loop.call_soon_threadsafe(loop.stop)

    def _make_session_on(self, loop):
        import aiohttp

        async def _mk():
            return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

        return asyncio.run_coroutine_threadsafe(_mk(), loop).result(timeout=5)

    def _close_session_on(self, session, loop):
        async def _close():
            await session.close()

        try:
            asyncio.run_coroutine_threadsafe(_close(), loop).result(timeout=5)
        except Exception:
            pass

    def _run_in_worker_loop(self, coro_factory):
        """Run ``coro_factory()`` on a fresh worker loop on a separate thread —
        mirroring ``model_tools._run_async``'s in-gateway-loop branch."""
        box = {}

        def _worker():
            wl = asyncio.new_event_loop()
            asyncio.set_event_loop(wl)
            try:
                box["result"] = wl.run_until_complete(coro_factory())
            except Exception as e:  # noqa: BLE001 — we assert on it
                box["exc"] = e
            finally:
                wl.close()

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=30)
        return box

    @pytest.mark.asyncio
    async def test_text_send_marshals_onto_gateway_loop(self):
        """Text-only channel send: the gateway-loop-bound session's timeout
        context must be entered inside a task ON the gateway loop."""
        import aiohttp
        import gateway.run as grun
        from tools import send_message_tool as smt

        gw_loop = self._start_gateway_loop()
        session = self._make_session_on(gw_loop)

        class _SessionBoundAdapter:
            platform = Platform.MATTERMOST

            async def send(self, chat_id, content, metadata=None):
                try:
                    async with session.post(
                        "http://127.0.0.1:1/unreachable",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        await resp.text()
                except aiohttp.ClientError:
                    return SendResult(success=True, message_id="text_ok")
                return SendResult(success=True, message_id="text_ok")

        runner = SimpleNamespace(
            adapters={Platform.MATTERMOST: _SessionBoundAdapter()},
            _gateway_loop=gw_loop,
        )

        try:
            with patch.object(grun, "_gateway_runner_ref", lambda: runner):
                box = self._run_in_worker_loop(
                    lambda: smt._send_via_adapter(
                        Platform.MATTERMOST,
                        SimpleNamespace(token="t", extra={}),
                        "chan_1",
                        "hello channel",
                    )
                )
        finally:
            self._close_session_on(session, gw_loop)
            self._stop_gateway_loop(gw_loop)

        assert "exc" not in box, f"dispatch raised: {box.get('exc')!r}"
        result = box.get("result")
        assert isinstance(result, dict), f"unexpected result: {result!r}"
        assert "Timeout context manager should be used inside a task" not in str(
            result.get("error", "")
        ), result
        assert result.get("success") is True, result
        assert result.get("message_id") == "text_ok"

    @pytest.mark.asyncio
    async def test_media_send_marshals_onto_gateway_loop(self, tmp_path):
        """Media channel send: the typed media method (``send_image_file``) also
        touches the gateway-loop-bound session and must be marshaled onto the
        gateway loop, not awaited directly on the worker loop."""
        import aiohttp
        import gateway.run as grun
        from tools import send_message_tool as smt

        img = tmp_path / "pic.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")

        gw_loop = self._start_gateway_loop()
        session = self._make_session_on(gw_loop)

        uploaded = []

        class _SessionBoundAdapter:
            platform = Platform.MATTERMOST

            async def send(self, chat_id, content, metadata=None):
                return SendResult(success=True, message_id="text_ok")

            async def send_image_file(self, chat_id, image_path, metadata=None):
                try:
                    async with session.post(
                        "http://127.0.0.1:1/unreachable",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        await resp.text()
                except aiohttp.ClientError:
                    uploaded.append(image_path)
                    return SendResult(success=True, message_id="media_ok")
                uploaded.append(image_path)
                return SendResult(success=True, message_id="media_ok")

        runner = SimpleNamespace(
            adapters={Platform.MATTERMOST: _SessionBoundAdapter()},
            _gateway_loop=gw_loop,
        )

        try:
            with patch.object(grun, "_gateway_runner_ref", lambda: runner):
                box = self._run_in_worker_loop(
                    lambda: smt._send_via_adapter(
                        Platform.MATTERMOST,
                        SimpleNamespace(token="t", extra={}),
                        "chan_1",
                        "see attached",
                        media_files=[(str(img), False)],
                    )
                )
        finally:
            self._close_session_on(session, gw_loop)
            self._stop_gateway_loop(gw_loop)

        assert "exc" not in box, f"dispatch raised: {box.get('exc')!r}"
        result = box.get("result")
        assert isinstance(result, dict), f"unexpected result: {result!r}"
        assert "Timeout context manager should be used inside a task" not in str(
            result.get("error", "")
        ), result
        assert result.get("success") is True, result
        assert uploaded == [str(img)], "media upload was not actually attempted"
