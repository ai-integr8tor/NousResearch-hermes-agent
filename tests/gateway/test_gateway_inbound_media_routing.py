from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType, SessionSource
from gateway.run import GatewayRunner


@pytest.mark.asyncio
async def test_photo_album_does_not_promote_text_attachment_to_native_image():
    """Mixed Telegram media groups keep per-attachment MIME boundaries.

    Telegram can deliver an album whose first item is a photo and later items are
    documents.  The merged MessageEvent may therefore be typed PHOTO while still
    carrying non-image attachments.  Native image routing must attach only the
    image MIME entries; otherwise providers reject text bytes as invalid image
    data.
    """
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = SimpleNamespace(
        group_sessions_per_user=True,
        thread_sessions_per_user=False,
    )
    runner._pending_native_image_paths_by_session = {}
    runner._session_key_for_source = lambda source: "telegram:dm:123"
    runner._decide_image_input_mode = lambda: "native"

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="123",
        chat_type="dm",
        user_id="u1",
        user_name="Pedro",
    )
    event = MessageEvent(
        text="check these attachments",
        message_type=MessageType.PHOTO,
        source=source,
        media_urls=["/cache/screenshot.png", "/cache/snippet.txt"],
        media_types=["image/png", "text/plain"],
    )

    prepared = await runner._prepare_inbound_message_text(
        event=event,
        source=source,
        history=[],
    )

    assert prepared == "check these attachments"
    assert runner._pending_native_image_paths_by_session["telegram:dm:123"] == [
        "/cache/screenshot.png"
    ]


@pytest.mark.asyncio
async def test_photo_without_mime_still_routes_as_native_image():
    """Keep the legacy fallback for photo updates that lack a MIME type."""
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = SimpleNamespace(
        group_sessions_per_user=True,
        thread_sessions_per_user=False,
    )
    runner._pending_native_image_paths_by_session = {}
    runner._session_key_for_source = lambda source: "telegram:dm:123"
    runner._decide_image_input_mode = lambda: "native"

    source = SessionSource(platform=Platform.TELEGRAM, chat_id="123", chat_type="dm")
    event = MessageEvent(
        text="photo",
        message_type=MessageType.PHOTO,
        source=source,
        media_urls=["/cache/photo-without-mime.jpg"],
        media_types=[""],
    )

    await runner._prepare_inbound_message_text(event=event, source=source, history=[])

    assert runner._pending_native_image_paths_by_session["telegram:dm:123"] == [
        "/cache/photo-without-mime.jpg"
    ]
