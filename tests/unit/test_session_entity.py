"""Unit tests for WhatsAppSession entity state machine."""

from whatsapp_platform.domain.entities.session import WhatsAppSession
from whatsapp_platform.domain.value_objects.session_status import SessionStatus


def test_initial_session_status():
    session = WhatsAppSession(id="sess-001")
    assert session.status == SessionStatus.INITIALIZING
    assert session.is_active is False
    assert session.reconnect_attempts == 0


def test_session_connect_sets_status():
    session = WhatsAppSession(id="sess-001")
    session.connect()
    assert session.status == SessionStatus.CONNECTED
    assert session.is_active is True
    assert session.reconnect_attempts == 0
    assert session.last_connected_at is not None


def test_session_disconnect_sets_status():
    session = WhatsAppSession(id="sess-001")
    session.connect()
    session.disconnect()
    assert session.status == SessionStatus.DISCONNECTED
    assert session.is_active is False


def test_session_reconnect_increments_attempts():
    session = WhatsAppSession(id="sess-001", max_reconnect_attempts=3)
    session.start_reconnect()
    assert session.reconnect_attempts == 1
    assert session.status == SessionStatus.RECONNECTING

    session.start_reconnect()
    assert session.reconnect_attempts == 2


def test_session_fail_after_max_reconnect_attempts():
    session = WhatsAppSession(id="sess-001", max_reconnect_attempts=2)
    session.start_reconnect()  # attempt 1
    session.start_reconnect()  # attempt 2
    session.start_reconnect()  # attempt 3 → triggers fail (max=2)
    assert session.status == SessionStatus.FAILED


def test_session_connect_resets_reconnect_attempts():
    session = WhatsAppSession(id="sess-001")
    session.start_reconnect()
    assert session.reconnect_attempts == 1
    session.connect()
    assert session.reconnect_attempts == 0
