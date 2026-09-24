import pytest

from device.simulator import DeviceSimulator, WasteBin


class StopSimulationError(Exception):
    pass


def test_simulator_sleeps_then_emits_reading_in_loop() -> None:
    intervals: list[float] = []
    readings = []

    def fake_sleep(seconds: float) -> None:
        intervals.append(seconds)

    def emit(reading) -> None:
        readings.append(reading)
        if len(readings) == 2:
            raise StopSimulationError

    simulator = DeviceSimulator(
        waste_bin=WasteBin("a"), interval_seconds=7, sleep=fake_sleep
    )

    with pytest.raises(StopSimulationError):
        simulator.run(emit)

    assert intervals == [7, 7]
    assert len(readings) == 2
    assert all(reading.bin_id == "a" for reading in readings)
    assert all(0 <= reading.fill_level <= 100 for reading in readings)
