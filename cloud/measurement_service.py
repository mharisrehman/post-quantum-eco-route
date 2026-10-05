"""Business logic for storing measurements received from bin devices."""

from models import BinReading
from cloud.repositories import BinReadingRepository, BinRepository


class MeasurementService:
    def __init__(
        self,
        repository: BinReadingRepository | None = None,
    ) -> None:
        self._repository = repository or BinReadingRepository()

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

        return self._repository.create(reading)

    def get_measurements(self) -> list[BinReading]:
        return self._repository.get_all()
