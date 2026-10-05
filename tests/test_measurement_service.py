from unittest.mock import Mock, patch

import pytest

from cloud import MeasurementService
from cloud.repositories import BinReadingRepository
from models import BinReading


@pytest.fixture
def repository() -> Mock:
    repository = Mock(spec=BinReadingRepository)
    repository._database = Mock()
    return repository


def test_save_measurement_persists_known_reading(repository: Mock) -> None:
    reading = BinReading("bin-1", 50, "now")
    saved = BinReading("bin-1", 50, "now", id=7)
    repository.create.return_value = saved
    service = MeasurementService(repository)

    with patch(
        "cloud.measurement_service.BinRepository",
        autospec=True,
    ) as bin_repository:
        bin_repository.return_value.get.return_value = object()

        assert service.save_measurement(reading) == saved

    repository.create.assert_called_once_with(reading)


def test_save_measurement_rejects_unknown_device(repository: Mock) -> None:
    reading = BinReading("missing-bin", 50, "now")
    service = MeasurementService(repository)

    with patch(
        "cloud.measurement_service.BinRepository",
        autospec=True,
    ) as bin_repository:
        bin_repository.return_value.get.return_value = None

        with pytest.raises(ValueError, match="unknown bin device"):
            service.save_measurement(reading)

    repository.create.assert_not_called()


def test_is_known_device_queries_bin_repository(repository: Mock) -> None:
    reading = BinReading("bin-1", 50, "now")
    service = MeasurementService(repository)

    with patch(
        "cloud.measurement_service.BinRepository",
        autospec=True,
    ) as bin_repository:
        bin_repository.return_value.get.return_value = object()

        assert service.is_known_device(reading)

    bin_repository.assert_called_once_with(repository._database)
    bin_repository.return_value.get.assert_called_once_with("bin-1")


def test_get_measurements_reads_from_repository(repository: Mock) -> None:
    readings = [BinReading("bin-1", 50, "now", id=3)]
    repository.get_all.return_value = readings
    service = MeasurementService(repository)

    assert service.get_measurements() == readings
    repository.get_all.assert_called_once_with()
