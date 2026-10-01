import pytest

from cloud import MeasurementService
from models import Bin, BinReading


def test_save_measurement_adds_reading_to_in_memory_list() -> None:
    service = MeasurementService(known_bins=[Bin(bin_id="bin-1")])
    reading = BinReading("bin-1", 50, "now")

    saved = service.save_measurement(reading)

    assert saved == reading
    assert service.get_measurements() == [reading]


def test_is_known_device_matches_reading_bin_id() -> None:
    service = MeasurementService(known_bins=[Bin(bin_id="bin-1")])

    assert service.is_known_device(BinReading("bin-1", 50, "now"))
    assert not service.is_known_device(BinReading("bin-missing", 50, "now"))


def test_save_measurement_rejects_unknown_device() -> None:
    service = MeasurementService(known_bins=[Bin(bin_id="bin-1")])
    reading = BinReading("bin-missing", 50, "now")

    with pytest.raises(ValueError, match="unknown bin device"):
        service.save_measurement(reading)

    assert service.get_measurements() == []
