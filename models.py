from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import base64
import binascii
import json


@dataclass(frozen=True)
class Bin:
    bin_id: str

    @classmethod
    def create(cls, bin_id: str) -> "Bin":
        if not bin_id:
            raise ValueError("bin_id is required")
        return cls(bin_id=bin_id)


@dataclass(frozen=True)
class BinReading:
    bin_id: str
    fill_level: int
    recorded_at: str
    id: int | None = None

    @classmethod
    def create(cls, bin_id: str, fill_level: int) -> "BinReading":
        if not bin_id:
            raise ValueError("bin_id is required")
        if not 0 <= fill_level <= 100:
            raise ValueError("fill_level must be between 0 and 100")
        return cls(bin_id, fill_level, datetime.now(timezone.utc).isoformat())

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self), separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, payload: bytes) -> "BinReading":
        data = json.loads(payload.decode("utf-8"))
        validated = cls.create(data["bin_id"], int(data["fill_level"]))
        return cls(
            bin_id=validated.bin_id,
            fill_level=validated.fill_level,
            recorded_at=data["recorded_at"],
            id=data.get("id"),
        )

    @classmethod
    def from_legacy_b64(cls, payload_b64: str) -> "BinReading":
        """Decode a legacy Base64-encoded JSON payload into a BinReading.

        Legacy devices send Base64(JSON) with no encryption or timestamp.
        A recorded_at is injected at ingestion time if absent.
        """
        try:
            decoded = base64.b64decode(payload_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("payload_b64 must be valid Base64") from exc

        try:
            data = json.loads(decoded.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("payload_b64 must decode to a JSON object") from exc

        if not isinstance(data, dict):
            raise ValueError("payload_b64 must decode to a JSON object")

        validated = cls.create(data["bin_id"], int(data["fill_level"]))
        recorded_at = data.get("recorded_at") or validated.recorded_at
        return cls(
            bin_id=validated.bin_id,
            fill_level=validated.fill_level,
            recorded_at=recorded_at,
        )


@dataclass(frozen=True)
class Alert:
    bin_id: str
    fill_level: int
    raised_at: str
    id: int | None = None

    @classmethod
    def create(cls, bin_id: str, fill_level: int) -> "Alert":
        if not bin_id:
            raise ValueError("bin_id is required")
        if not 0 <= fill_level <= 100:
            raise ValueError("fill_level must be between 0 and 100")
        return cls(bin_id, fill_level, datetime.now(timezone.utc).isoformat())
