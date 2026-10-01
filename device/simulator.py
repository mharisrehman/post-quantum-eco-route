"""Sensor device simulator that generates increasing bin measurements."""

from __future__ import annotations

import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    from models import BinReading
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from models import BinReading


@dataclass(frozen=True)
class WasteBin:
    bin_id: str

    def __post_init__(self) -> None:
        if not self.bin_id:
            raise ValueError("bin_id is required")


class DeviceSimulator:
    def __init__(
        self,
        waste_bin: WasteBin,
        interval_seconds: int = 15,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be zero or positive")
        self._waste_bin = waste_bin
        self._interval_seconds = interval_seconds
        self._sleep = sleep
        self._fill_level = 0

    def generate_reading(self) -> BinReading:
        self._fill_level = min(self._fill_level + random.randint(1, 5), 100)
        return BinReading.create(
            bin_id=self._waste_bin.bin_id,
            fill_level=self._fill_level,
        )

    def run(self, emit: Callable[[BinReading], None]) -> None:
        while True:
            self._sleep(self._interval_seconds)
            emit(self.generate_reading())


class DeviceFleet:
    """Run multiple independent bin simulators on a shared interval."""

    def __init__(
        self,
        bin_ids: list[str],
        interval_seconds: int = 15,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not bin_ids:
            raise ValueError("at least one bin_id is required")
        if len(set(bin_ids)) != len(bin_ids):
            raise ValueError("bin_ids must be unique")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be zero or positive")
        self._simulators = [
            DeviceSimulator(WasteBin(bin_id)) for bin_id in bin_ids
        ]
        self._interval_seconds = interval_seconds
        self._sleep = sleep

    def run(self, emit: Callable[[BinReading], None]) -> None:
        interval_per_device = self._interval_seconds / len(self._simulators)
        while True:
            for simulator in self._simulators:
                self._sleep(interval_per_device)
                emit(simulator.generate_reading())


class Device:
    """Single-unit device facade for main loop execution."""

    def __init__(self, bin_id: str, interval_seconds: int) -> None:
        self._simulator = DeviceSimulator(
            waste_bin=WasteBin(bin_id), interval_seconds=interval_seconds
        )

    def run(self) -> None:
        self._simulator.run(print)
