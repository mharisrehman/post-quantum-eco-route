from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json


@dataclass(frozen=True)
class BinReading:
    bin_id: str
    fill_level: int
    recorded_at: str

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
        )
