"""Runnable entrypoint for the simulated sensor device."""

from __future__ import annotations

import os
from pathlib import Path

from simulator import DeviceSimulator, WasteBin
from gateway import Gateway
from sender import Base64Sender

DEFAULT_INTERVAL_SECONDS = 5
ENV_INTERVAL_KEY = "DEVICE_INTERVAL_SECONDS"
ENV_BIN_ID_KEY = "DEVICE_BIN_ID"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    device_dir = Path(__file__).parent
    _load_env_file(device_dir / ".env")
    interval_seconds = int(
        os.getenv(ENV_INTERVAL_KEY, str(DEFAULT_INTERVAL_SECONDS))
    )
    bin_id = os.getenv(ENV_BIN_ID_KEY, "bin-1")
    gateway = Gateway(forward=print)
    sender = Base64Sender(send=gateway.receive)
    simulator = DeviceSimulator(
        waste_bin=WasteBin(bin_id), interval_seconds=interval_seconds
    )
    simulator.run(sender.send_reading)


if __name__ == "__main__":
    main()
