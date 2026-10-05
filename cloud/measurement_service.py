"""Business logic for storing measurements received from bin devices."""

import logging

from models import Alert, BinReading
from cloud.repositories import (
    AlertRepository,
    BinReadingRepository,
    BinRepository,
)

ALERT_THRESHOLD = 80
logger = logging.getLogger(__name__)


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
