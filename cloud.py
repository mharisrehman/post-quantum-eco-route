"""Cloud processing for storage and collection alerts."""

from collections.abc import Callable

from models import BinReading


class CloudService:
    def __init__(self, save_reading: Callable[[BinReading], None]) -> None:
        self._save_reading = save_reading

    def process(self, reading: BinReading) -> str | None:
        self._save_reading(reading)
        if reading.fill_level > 80:
            return f"Pickup alert: {reading.bin_id} is {reading.fill_level}% full"
        return None
