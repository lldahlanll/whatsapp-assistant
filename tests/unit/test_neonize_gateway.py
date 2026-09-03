"""Unit tests untuk NeonizeGateway.

Menguji perilaku NeonizeGateway dengan mock Neonize client —
tidak ada koneksi WhatsApp nyata yang dibutuhkan.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from whatsapp_platform.domain.events.session_events import (
    SessionConnected,
    SessionDisconnected,
)
from whatsapp_platform.domain.exceptions.exceptions import GatewayException
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import (
    MediaContent,
    MediaType,
)
from whatsapp_platform.infrastructure.neonize.gateway import NeonizeGateway

# ─── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_client() -> MagicMock:
    """Build a minimal Neonize NewClient mock."""
    client = MagicMock()
    client.event = MagicMock(return_value=lambda fn: fn)  # decorator mock
    client.connect = MagicMock()
    client.disconnect = MagicMock()
    client.send_message = MagicMock(return_value=MagicMock(ID="MSG-001"))
    client.send_image = MagicMock(return_value=MagicMock(ID="IMG-001"))
    client.send_audio = MagicMock(return_value=MagicMock(ID="AUD-001"))
    client.send_document = MagicMock(return_value=MagicMock(ID="DOC-001"))
    client.send_video = MagicMock(return_value=MagicMock(ID="VID-001"))
    client.PairPhone = MagicMock(return_value="12345678")
    return client


@pytest.fixture
def mock_client() -> MagicMock:
    return _make_mock_client()


@pytest.fixture
def gateway(mock_client: MagicMock) -> NeonizeGateway:
    return NeonizeGateway(session_name="test-session", client=mock_client)


# ─── Inisialisasi ──────────────────────────────────────────────────────────────


class TestNeonizeGatewayInit:
    def test_gateway_created_with_injected_client(self, gateway, mock_client):
        assert gateway.client is mock_client

    def test_gateway_session_name_stored(self, gateway):
        assert gateway.session_name == "test-session"

    def test_gateway_not_connected_initially(self, gateway):
        assert gateway._connected is False

    def test_gateway_registers_neonize_event_handlers_on_init(self, mock_client):
        """client.event() harus dipanggil 6x: Connected, Disconnected, LoggedOut, QR, PairStatus, Message."""
        _ = NeonizeGateway(session_name="sess", client=mock_client)
        assert mock_client.event.call_count == 6


# ─── subscribe_event ───────────────────────────────────────────────────────────


class TestSubscribeEvent:
    def test_subscribe_adds_handler_to_listeners(self, gateway):
        async def handler(ev):
            pass

        gateway.subscribe_event(SessionConnected, handler)
        assert handler in gateway._listeners[SessionConnected]

    def test_subscribe_multiple_handlers_same_event(self, gateway):
        async def h1(ev):
            pass

        async def h2(ev):
            pass

        gateway.subscribe_event(SessionConnected, h1)
        gateway.subscribe_event(SessionConnected, h2)

        assert len(gateway._listeners[SessionConnected]) == 2

    def test_subscribe_different_event_types_isolated(self, gateway):
        async def h1(ev):
            pass

        async def h2(ev):
            pass

        gateway.subscribe_event(SessionConnected, h1)
        gateway.subscribe_event(SessionDisconnected, h2)

        assert h1 not in gateway._listeners.get(SessionDisconnected, [])
        assert h2 not in gateway._listeners.get(SessionConnected, [])


# ─── connect / disconnect ──────────────────────────────────────────────────────


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_stores_event_loop(self, gateway):
        await gateway.connect()
        assert gateway._loop is not None

    @pytest.mark.asyncio
    async def test_connect_spawns_thread_with_client_connect(
        self, gateway, mock_client
    ):
        await gateway.connect()
        await asyncio.sleep(0.05)  # beri waktu thread jalan
        mock_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_calls_client_disconnect(self, gateway, mock_client):
        await gateway.disconnect()
        mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_sets_connected_false(self, gateway):
        gateway._connected = True
        await gateway.disconnect()
        assert gateway._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_exception_gracefully(self, gateway, mock_client):
        mock_client.disconnect.side_effect = RuntimeError("already down")
        # Tidak boleh raise ke caller
        await gateway.disconnect()

    @pytest.mark.asyncio
    async def test_is_connected_returns_false_initially(self, gateway):
        result = await gateway.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_connected_returns_true_after_flag_set(self, gateway):
        gateway._connected = True
        result = await gateway.is_connected()
        assert result is True


# ─── send_text ─────────────────────────────────────────────────────────────────


class TestSendText:
    @pytest.mark.asyncio
    async def test_send_text_returns_message_id(self, gateway, mock_client):
        jid = JID.create_user("628111000000")
        result = await gateway.send_text(jid, "Hello!")
        assert result == "MSG-001"

    @pytest.mark.asyncio
    async def test_send_text_calls_client_send_message(self, gateway, mock_client):
        jid = JID.create_user("628111000000")
        await gateway.send_text(jid, "hi")
        mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_text_raises_gateway_exception_on_error(
        self, gateway, mock_client
    ):
        mock_client.send_message.side_effect = Exception("network error")
        jid = JID.create_user("628111000000")
        with pytest.raises(GatewayException, match="Failed to send message"):
            await gateway.send_text(jid, "test")

    @pytest.mark.asyncio
    async def test_send_text_returns_empty_string_when_no_id(
        self, gateway, mock_client
    ):
        mock_client.send_message.return_value = None
        jid = JID.create_user("628111000000")
        result = await gateway.send_text(jid, "hey")
        assert result == ""


# ─── send_media ────────────────────────────────────────────────────────────────


class TestSendMedia:
    @pytest.mark.asyncio
    async def test_send_image_returns_id(self, gateway, mock_client):
        jid = JID.create_user("628111000000")
        media = MediaContent(media_type=MediaType.IMAGE, file_path="/tmp/img.jpg")
        result = await gateway.send_media(jid, media, caption="Look!")
        assert result == "IMG-001"
        mock_client.send_image.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_audio_returns_id(self, gateway, mock_client):
        jid = JID.create_user("628111000000")
        media = MediaContent(
            media_type=MediaType.AUDIO, file_path="/tmp/voice.ogg", is_ptt=True
        )
        result = await gateway.send_media(jid, media)
        assert result == "AUD-001"
        mock_client.send_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_document_returns_id(self, gateway, mock_client):
        jid = JID.create_user("628111000000")
        media = MediaContent(
            media_type=MediaType.DOCUMENT,
            file_path="/tmp/file.pdf",
            file_name="file.pdf",
        )
        result = await gateway.send_media(jid, media)
        assert result == "DOC-001"
        mock_client.send_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_video_returns_id(self, gateway, mock_client):
        jid = JID.create_user("628111000000")
        media = MediaContent(media_type=MediaType.VIDEO, file_path="/tmp/video.mp4")
        result = await gateway.send_media(jid, media)
        assert result == "VID-001"
        mock_client.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_raises_when_no_file_input(self, gateway):
        jid = JID.create_user("628111000000")
        media = MediaContent(media_type=MediaType.IMAGE)  # no file_path or file_bytes
        with pytest.raises(
            GatewayException, match="must provide file_path or file_bytes"
        ):
            await gateway.send_media(jid, media)

    @pytest.mark.asyncio
    async def test_send_media_raises_gateway_exception_on_client_error(
        self, gateway, mock_client
    ):
        mock_client.send_image.side_effect = Exception("upload failed")
        jid = JID.create_user("628111000000")
        media = MediaContent(media_type=MediaType.IMAGE, file_path="/tmp/img.jpg")
        with pytest.raises(GatewayException, match="Failed to send media"):
            await gateway.send_media(jid, media)


# ─── pair_phone ────────────────────────────────────────────────────────────────


class TestPairPhone:
    @pytest.mark.asyncio
    async def test_pair_phone_returns_code_string(self, gateway, mock_client):
        result = await gateway.pair_phone("+62811000000")
        assert result == "12345678"
        mock_client.PairPhone.assert_called_once_with("+62811000000")

    @pytest.mark.asyncio
    async def test_pair_phone_raises_gateway_exception_on_error(
        self, gateway, mock_client
    ):
        mock_client.PairPhone.side_effect = Exception("pairing failed")
        with pytest.raises(GatewayException, match="PairPhone failed"):
            await gateway.pair_phone("+62811000000")


# ─── _dispatch_domain_event ────────────────────────────────────────────────────


class TestDispatchDomainEvent:
    @pytest.mark.asyncio
    async def test_dispatch_does_nothing_when_no_loop(self, gateway):
        """Sebelum connect(), loop belum ada — dispatch tidak boleh crash."""
        gateway._loop = None
        event = SessionConnected(session_id="s")
        gateway._dispatch_domain_event(event)  # tidak ada exception

    @pytest.mark.asyncio
    async def test_dispatch_calls_async_handler(self, gateway):
        received: list = []

        async def handler(ev):
            received.append(ev)

        gateway.subscribe_event(SessionConnected, handler)
        await gateway.connect()
        await asyncio.sleep(0.05)

        event = SessionConnected(session_id="test")
        gateway._dispatch_domain_event(event)
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].session_id == "test"

    @pytest.mark.asyncio
    async def test_dispatch_ignores_unsubscribed_event_type(self, gateway):
        received: list = []

        async def handler(ev):
            received.append(ev)

        gateway.subscribe_event(SessionConnected, handler)
        await gateway.connect()

        # Kirim event BERBEDA dari yg disubscribe
        event = SessionDisconnected(session_id="test")
        gateway._dispatch_domain_event(event)
        await asyncio.sleep(0.05)

        assert len(received) == 0
