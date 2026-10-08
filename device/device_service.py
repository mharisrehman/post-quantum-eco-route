"""Publish simulator readings using the gateway's Base64 JSON envelope."""

from __future__ import annotations

import base64
import json
from typing import Protocol
from urllib.request import Request, urlopen


class ReadingPayload(Protocol):
    bin_id: str
    fill_level: int


class DeviceService:
    def __init__(self, gateway_url: str) -> None:
        self._gateway_url = gateway_url.rstrip("/")

    def publish_reading(self, reading: ReadingPayload) -> None:
        reading_json = json.dumps(
            {"bin_id": reading.bin_id, "fill_level": reading.fill_level}
        ).encode("utf-8")
        envelope = json.dumps(
            {"payload_b64": base64.b64encode(reading_json).decode("ascii")}
        ).encode("utf-8")
        request = Request(
            f"{self._gateway_url}/readings",
            data=envelope,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            if response.status != 201:
                raise RuntimeError(
                    f"Gateway returned unexpected status {response.status}"
                )