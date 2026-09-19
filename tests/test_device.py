from device import DeviceSimulator, WasteBin


def test_simulator_emits_each_bin_for_each_cycle() -> None:
    simulator = DeviceSimulator([WasteBin("a"), WasteBin("b")], interval_seconds=0)

    readings = list(simulator.readings(cycles=2))

    assert len(readings) == 4
    assert {reading.bin_id for reading in readings} == {"a", "b"}
    assert all(0 <= reading.fill_level <= 100 for reading in readings)
