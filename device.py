"""Simulated municipal waste bins."""

from dataclasses import dataclass
import random
import time
from collections.abc import Callable, Iterator

from models import BinReading


@dataclass
class WasteBin:
    bin_id: str
    fill_level: int = 0

    def reading(self, rng: random.Random | None = None) -> BinReading:
        rng = rng or random.Random()
        self.fill_level = min(100, self.fill_level + rng.randint(1, 12))
        return BinReading.create(self.bin_id, self.fill_level)


class DeviceSimulator:
    def __init__(
        self, bins: list[WasteBin], interval_seconds: float = 10.0
    ) -> None:
        self.bins = bins
        self.interval_seconds = interval_seconds

    def readings(self, cycles: int | None = None) -> Iterator[BinReading]:
        cycle = 0
        while cycles is None or cycle < cycles:
            yield from (waste_bin.reading() for waste_bin in self.bins)
            cycle += 1
            if cycles is None:
                time.sleep(self.interval_seconds)

    def run(
        self, send: Callable[[BinReading], None], cycles: int | None = None
    ) -> None:
        for reading in self.readings(cycles):
            send(reading)


if __name__ == "__main__":
    DeviceSimulator([WasteBin("bin-001"), WasteBin("bin-002")]).run(print)
