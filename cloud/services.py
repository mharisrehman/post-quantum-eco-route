"""Business logic for cloud services."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from pathlib import Path
from typing import Any

from cloud.repositories import (
    AlertRepository,
    BinReadingRepository,
    BinRepository,
)
from ml_kem_crypto import (
    EncryptedMessage,
    MlKemSession,
    load_or_create_keypair,
)
from models import Alert, Bin, BinReading

ALERT_THRESHOLD = 80
logger = logging.getLogger(__name__)


class UnknownSessionError(ValueError):
    pass


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
    def __init__(
        self,
        key_file: str | Path | None = None,
        kem: Any | None = None,
    ) -> None:
        self._key_file = Path(
            key_file
            or os.getenv(
                "CLOUD_ML_KEM_KEY_FILE",
                Path(__file__).resolve().parents[1]
                / ".data"
                / "ml-kem-768.json",
            )
        )
        self._session = MlKemSession(kem)
        self._public_key: bytes | None = None
        self._sessions: dict[str, tuple[bytes, MlKemSession]] = {}

    def _ensure_keypair(self) -> None:
        if self._public_key is None:
            self._public_key = load_or_create_keypair(
                self._session, self._key_file
            )

    @property
    def public_key(self) -> bytes:
        self._ensure_keypair()
        assert self._public_key is not None
        return self._public_key

    def decrypt_reading(self, payload: dict[str, str]) -> dict[str, object]:
        try:
            self._ensure_keypair()
            session_id = payload["session_id"]
            if not session_id:
                raise ValueError("session_id must not be empty")
            nonce = base64.b64decode(payload["nonce_b64"], validate=True)
            ciphertext = base64.b64decode(
                payload["ciphertext_b64"], validate=True
            )
            kem_ciphertext = (
                base64.b64decode(payload["kem_ciphertext_b64"], validate=True)
                if "kem_ciphertext_b64" in payload
                else None
            )
            existing = self._sessions.get(session_id)
            if existing is None:
                if kem_ciphertext is None:
                    raise UnknownSessionError(
                        "Unknown ML-KEM session; restart the key exchange"
                    )
                shared_secret = self._session.decapsulate(kem_ciphertext)
                crypto = self._session.new_session(shared_secret)
            else:
                original_kem_ciphertext, crypto = existing
                if (
                    kem_ciphertext is not None
                    and kem_ciphertext != original_kem_ciphertext
                ):
                    raise ValueError("ML-KEM session ciphertext does not match")
            decoded = crypto.decrypt(
                EncryptedMessage(
                    kem_ciphertext if existing is None else existing[0],
                    nonce,
                    ciphertext,
                )
            )
            reading = json.loads(decoded.decode("utf-8"))
            if existing is None:
                assert kem_ciphertext is not None
                self._sessions[session_id] = (kem_ciphertext, crypto)
        except UnknownSessionError:
            raise
        except (
            TypeError,
            ValueError,
            KeyError,
            binascii.Error,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise ValueError("Invalid encrypted reading envelope") from exc
        if not isinstance(reading, dict):
            raise ValueError("Encrypted reading must decode to a JSON object")
        return reading


__all__ = ["BinService", "CloudService", "MeasurementService"]
