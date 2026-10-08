"""Business logic for cloud services."""

from __future__ import annotations

import base64
import binascii
import json
import logging

from cloud.repositories import (
    AlertRepository,
    BinReadingRepository,
    BinRepository,
)
from ml_kem_crypto import MlKemSession, decode_message
from models import Alert, Bin, BinReading

ALERT_THRESHOLD = 80
logger = logging.getLogger(__name__)


class BinService:
    def __init__(
        self,
        repository: BinRepository | None = None,
    ) -> None:
        self._repository = repository or BinRepository()

    def create_bin(self, bin_id: str) -> Bin:
        if self.get_bin(bin_id) is not None:
            raise ValueError(f"bin already exists for bin_id '{bin_id}'")

        bin = Bin.create(bin_id=bin_id)
        return self._repository.create(bin)

    def get_bins(self) -> list[Bin]:
        return self._repository.get_all()

    def get_bin(self, bin_id: str) -> Bin | None:
        return self._repository.get(bin_id)

    def delete_bin(self, bin_id: str) -> Bin | None:
        return self._repository.delete(bin_id)


class MeasurementService:
    def __init__(
        self,
        repository: BinReadingRepository | None = None,
        alert_repository: AlertRepository | None = None,
    ) -> None:
        self._repository = repository or BinReadingRepository()
        self._alert_repository = alert_repository or AlertRepository(
            self._repository._database
        )

    def is_known_device(self, reading: BinReading) -> bool:
        return (
            BinRepository(self._repository._database).get(reading.bin_id)
            is not None
        )

    def save_measurement(self, reading: BinReading) -> BinReading:
        if not self.is_known_device(reading):
            raise ValueError(
                f"unknown bin device for bin_id '{reading.bin_id}'"
            )

        saved_reading = self._repository.create(reading)
        if reading.fill_level > ALERT_THRESHOLD:
            alert = Alert.create(reading.bin_id, reading.fill_level)
            self._alert_repository.create(alert)
            logger.warning(
                "Alert raised for bin '%s': fill level is %d%%",
                alert.bin_id,
                alert.fill_level,
            )
        return saved_reading

    def get_measurements(self) -> list[BinReading]:
        return self._repository.get_all()

    def get_alerts(self) -> list[Alert]:
        return self._alert_repository.get_all()

    def delete_all_alerts(self) -> None:
        self._alert_repository.delete_all()

    def delete_all_measurements(self) -> None:
        self._repository.delete_all()


class CloudService:
    def __init__(self) -> None:
        self._session = MlKemSession()
        self._public_key: bytes | None = None

    def _ensure_keypair(self) -> None:
        if self._public_key is None:
            self._public_key = self._session.create_keypair()

    @property
    def public_key(self) -> bytes:
        self._ensure_keypair()
        assert self._public_key is not None
        return self._public_key

    def decrypt_reading(self, payload: dict[str, str]) -> dict[str, object]:
        try:
            self._ensure_keypair()
            message = decode_message(payload)
            shared_secret = self._session.decapsulate(message.kem_ciphertext)
            self._session.set_session_key(shared_secret)
            decoded = self._session.decrypt(message)
            reading = json.loads(decoded.decode("utf-8"))
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid encrypted reading envelope") from exc
        if not isinstance(reading, dict):
            raise ValueError("Encrypted reading must decode to a JSON object")
        return reading

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


__all__ = ["BinService", "CloudService", "MeasurementService"]
