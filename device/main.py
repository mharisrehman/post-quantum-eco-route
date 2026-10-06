"""Runnable entrypoint for the simulated sensor device."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from .simulator import DeviceFleet
except ImportError:
    from simulator import DeviceFleet

DEFAULT_INTERVAL_SECONDS = 5
DEFAULT_BIN_IDS = ("bin-1", "bin-2", "bin-3")
ENV_INTERVAL_KEY = "DEVICE_INTERVAL_SECONDS"
ENV_BIN_ID_KEY = "DEVICE_BIN_ID"
ENV_BIN_IDS_KEY = "DEVICE_BIN_IDS"


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


def _configured_bin_ids() -> list[str]:
    configured_bin_ids = os.getenv(ENV_BIN_IDS_KEY)
    if configured_bin_ids is not None:
        return [bin_id.strip() for bin_id in configured_bin_ids.split(",")]

    configured_bin_id = os.getenv(ENV_BIN_ID_KEY)
    if configured_bin_id is not None:
        return [configured_bin_id]
    return list(DEFAULT_BIN_IDS)


def main() -> None:
    device_dir = Path(__file__).parent
    _load_env_file(device_dir / ".env")
    interval_seconds = int(
        os.getenv(ENV_INTERVAL_KEY, str(DEFAULT_INTERVAL_SECONDS))
    )
    DeviceFleet(
        bin_ids=_configured_bin_ids(), interval_seconds=interval_seconds
    ).run(print)


if __name__ == "__main__":
    main()
