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


def test_generated_fill_level_increases_by_one_to_five_and_stops_at_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    increments = iter([1, 3, 5] + [5] * 20)

    def fake_randint(lower: int, upper: int) -> int:
        assert (lower, upper) == (1, 5)
        return next(increments)

    monkeypatch.setattr("device.simulator.random.randint", fake_randint)
    simulator = DeviceSimulator(waste_bin=WasteBin("a"))

    fill_levels = [simulator.generate_reading().fill_level for _ in range(23)]

    assert fill_levels[:3] == [1, 4, 9]
    assert fill_levels[-2:] == [100, 100]
    assert all(
        0 <= next_level - level <= 5
        for level, next_level in zip(fill_levels, fill_levels[1:])
    )
    assert all(0 <= level <= 100 for level in fill_levels)
