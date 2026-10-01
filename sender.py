"""Encode device readings and pass them to an injected transport."""

import base64
from collections.abc import Callable

from models import BinReading


class Base64Sender:
    def __init__(self, send: Callable[[str], str | None]) -> None:
        self._send = send

    def send_reading(self, reading: BinReading) -> None:
        encoded_message = base64.b64encode(reading.to_bytes()).decode("ascii")
        self._send(encoded_message)