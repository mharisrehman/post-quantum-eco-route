import base64

import pytest

from device.sender import Base64Sender
from gateway import Gateway
from models import BinReading


def test_sender_and_gateway_round_trip_reading() -> None:
    forwarded: list[BinReading] = []
    gateway = Gateway(forward=forwarded.append)
    sender = Base64Sender(send=gateway.receive)
    reading = BinReading.create("bin-1", 42)

    sender.send_reading(reading)

    assert forwarded == [reading]


def test_sender_encodes_reading_as_base64() -> None:
    messages: list[str] = []
    sender = Base64Sender(send=messages.append)
    reading = BinReading.create("bin-1", 42)

    sender.send_reading(reading)

    assert len(messages) == 1
    assert base64.b64decode(messages[0], validate=True) == reading.to_bytes()


def test_gateway_rejects_invalid_base64() -> None:
    gateway = Gateway(forward=lambda _reading: None)

    with pytest.raises(ValueError, match="message must be valid Base64"):
        gateway.receive("not base64!")
