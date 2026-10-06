import pytest

from device.main import ENV_BIN_ID_KEY, ENV_BIN_IDS_KEY, _configured_bin_ids
from device.simulator import DeviceFleet, DeviceSimulator, WasteBin


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


def test_generated_fill_level_does_not_exceed_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("device.simulator.random.randint", lambda *_args: 5)
    simulator = DeviceSimulator(waste_bin=WasteBin("a"))

    fill_levels = [simulator.generate_reading().fill_level for _ in range(21)]

    assert all(level <= 100 for level in fill_levels)


def test_fleet_emits_independent_readings_once_per_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("device.simulator.random.randint", lambda *_args: 1)
    elapsed_seconds = 0.0
    emitted_at: list[float] = []
    readings = []

    def fake_sleep(seconds: float) -> None:
        nonlocal elapsed_seconds
        elapsed_seconds += seconds

    def emit(reading) -> None:
        readings.append(reading)
        emitted_at.append(elapsed_seconds)
        if len(readings) == 4:
            raise StopSimulationError

    fleet = DeviceFleet(
        bin_ids=["a", "b"],
        interval_seconds=3,
        sleep=fake_sleep,
    )

    with pytest.raises(StopSimulationError):
        fleet.run(emit)

    assert emitted_at == [1.5, 3, 4.5, 6]
    assert [reading.bin_id for reading in readings] == ["a", "b", "a", "b"]
    assert [reading.fill_level for reading in readings] == [1, 1, 2, 2]


def test_entrypoint_defaults_to_multiple_bins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_BIN_IDS_KEY, raising=False)
    monkeypatch.delenv(ENV_BIN_ID_KEY, raising=False)

    assert _configured_bin_ids() == ["bin-1", "bin-2", "bin-3"]


def test_single_bin_environment_setting_remains_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_BIN_IDS_KEY, raising=False)
    monkeypatch.setenv(ENV_BIN_ID_KEY, "custom-bin")

    assert _configured_bin_ids() == ["custom-bin"]
