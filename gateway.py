"""Edge gateway for secure validation and forwarding."""

import base64
import binascii
from collections.abc import Callable

from models import BinReading


class Gateway:
    def __init__(self, forward: Callable[[BinReading], str | None]) -> None:
        self._forward = forward

    def receive(self, message: str) -> str | None:
        try:
            payload = base64.b64decode(message, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("message must be valid Base64") from exc
        reading = BinReading.from_bytes(payload)
        return self._forward(reading)
