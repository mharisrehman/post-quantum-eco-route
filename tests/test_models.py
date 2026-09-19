import pytest

from models import BinReading


def test_reading_round_trips_as_json() -> None:
    reading = BinReading("bin-1", 50, "now")

    assert BinReading.from_bytes(reading.to_bytes()) == reading


def test_reading_rejects_invalid_fill_level() -> None:
    with pytest.raises(ValueError):
        BinReading.create("bin-1", 101)
