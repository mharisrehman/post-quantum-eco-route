"""Publish simulator readings to the gateway, with ML-KEM encryption when available."""

from __future__ import annotations

import base64
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ml_kem_crypto import MlKemSession


class ReadingPayload(Protocol):
    bin_id: str
    fill_level: int


class DeviceService:
    def __init__(self, gateway_url: str) -> None:
        self._gateway_url = gateway_url.strip().rstrip("/")

    def _read_public_key(self) -> bytes:
        request = Request(
            f"{self._gateway_url}/crypto/public-key",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Gateway returned unexpected status {response.status}"
                    )
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, ValueError, TypeError, KeyError):
            raise RuntimeError(
                "Gateway did not provide a valid ML-KEM public key"
            )

        try:
            return base64.b64decode(payload["public_key_b64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "Gateway did not provide a valid ML-KEM public key"
            ) from exc

    def _publish_legacy_payload(self, reading_json: bytes) -> None:
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

    def _publish_ml_kem_payload(self, reading_json: bytes) -> None:
        public_key = self._read_public_key()
        session = MlKemSession()
        kem_ciphertext, shared_secret = session.encapsulate(public_key)
        session.set_session_key(shared_secret)
        encrypted_message = session.encrypt(reading_json, kem_ciphertext)
        envelope = json.dumps(
            {
                "kem_ciphertext": base64.b64encode(
                    encrypted_message.kem_ciphertext
                ).decode("ascii"),
                "nonce": base64.b64encode(encrypted_message.nonce).decode(
                    "ascii"
                ),
                "aes_ciphertext": base64.b64encode(
                    encrypted_message.ciphertext
                ).decode("ascii"),
            }
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

    def publish_reading(self, reading: ReadingPayload) -> None:
        reading_json = json.dumps(
            {"bin_id": reading.bin_id, "fill_level": reading.fill_level}
        ).encode("utf-8")
        try:
            self._publish_ml_kem_payload(reading_json)
        except RuntimeError:
            self._publish_legacy_payload(reading_json)
