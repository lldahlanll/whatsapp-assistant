"""Unit tests for JID Value Object."""

import pytest

from whatsapp_platform.domain.exceptions.exceptions import InvalidJIDError
from whatsapp_platform.domain.value_objects.jid import JID


def test_parse_valid_user_jid():
    jid = JID.parse("628123456789@s.whatsapp.net")
    assert jid.user == "628123456789"
    assert jid.server == "s.whatsapp.net"
    assert jid.is_user is True
    assert jid.is_group is False
    assert str(jid) == "628123456789@s.whatsapp.net"


def test_parse_valid_group_jid():
    jid = JID.parse("1203630123456789@g.us")
    assert jid.user == "1203630123456789"
    assert jid.server == "g.us"
    assert jid.is_group is True


def test_parse_raw_phone_number():
    jid = JID.parse("+62 812-3456-789")
    assert jid.user == "628123456789"
    assert jid.server == "s.whatsapp.net"


def test_parse_invalid_jid_raises_error():
    with pytest.raises(InvalidJIDError):
        JID.parse("invalid_server@unknown.com")
