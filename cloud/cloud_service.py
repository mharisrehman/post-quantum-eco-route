"""Decode readings received in the gateway's Base64 JSON envelope."""

from __future__ import annotations

import base64
import binascii
import json


class CloudService:
    def decode_reading(self, payload_b64: str) -> dict[str, object]:
        try:
            decoded = base64.b64decode(payload_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("payload_b64 must be valid Base64") from exc

        try:
            reading = json.loads(decoded.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(
                "payload_b64 must decode to a JSON object"
            ) from exc

        if not isinstance(reading, dict):
            raise ValueError("payload_b64 must decode to a JSON object")
        return reading