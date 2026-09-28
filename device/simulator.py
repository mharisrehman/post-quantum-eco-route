"""Sensor device simulator that generates random bin measurements."""

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

    def generate_reading(self) -> BinReading:
        return BinReading.create(
            bin_id=self._waste_bin.bin_id,
            fill_level=random.randint(0, 100),
        )

    def run(self, emit: Callable[[BinReading], None]) -> None:
        while True:
            self._sleep(self._interval_seconds)
            emit(self.generate_reading())


class Device:
    """Single-unit device facade for main loop execution."""

    def __init__(self, bin_id: str, interval_seconds: int) -> None:
        self._simulator = DeviceSimulator(
            waste_bin=WasteBin(bin_id), interval_seconds=interval_seconds
        )

    def run(self) -> None:
        self._simulator.run(print)
