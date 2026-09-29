"""Business logic for storing measurements received from bin devices."""

from models import Bin, BinReading


class MeasurementService:
    def __init__(
        self,
        known_bins: list[Bin] | None = None,
        measurements: list[BinReading] | None = None,
    ) -> None:
        self._known_bins = known_bins if known_bins is not None else []
        self._measurements = measurements if measurements is not None else []

    def is_known_device(self, reading: BinReading) -> bool:
        return any(bin.bin_id == reading.bin_id for bin in self._known_bins)

    def save_measurement(self, reading: BinReading) -> BinReading:
        if not self.is_known_device(reading):
            raise ValueError(
                f"unknown bin device for bin_id '{reading.bin_id}'"
            )

        self._measurements.append(reading)
        return reading

    def get_measurements(self) -> list[BinReading]:
        return self._measurements
