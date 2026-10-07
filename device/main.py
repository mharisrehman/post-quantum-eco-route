"""Runnable entrypoint for the simulated sensor device."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

if __package__:
    from .simulator import DeviceFleet
else:
    from simulator import DeviceFleet

DEFAULT_INTERVAL_SECONDS = 5
DEFAULT_BIN_IDS = ("bin-1", "bin-2", "bin-3")
ENV_INTERVAL_KEY = "DEVICE_INTERVAL_SECONDS"
ENV_BIN_ID_KEY = "DEVICE_BIN_ID"
ENV_BIN_IDS_KEY = "DEVICE_BIN_IDS"
DEFAULT_CLOUD_API_URL = "http://localhost:8000"
ENV_CLOUD_API_URL_KEY = "CLOUD_API_URL"


class ReadingPayload(Protocol):
    bin_id: str
    fill_level: int


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


def _publish_reading(reading: ReadingPayload, api_url: str) -> None:
    request = Request(
        f"{api_url.rstrip('/')}/readings",
        data=json.dumps(
            {"bin_id": reading.bin_id, "fill_level": reading.fill_level}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise RuntimeError(
                f"Cloud API returned unexpected status {response.status}"
            )


def main() -> None:
    device_dir = Path(__file__).parent
    _load_env_file(device_dir / ".env")
    interval_seconds = int(
        os.getenv(ENV_INTERVAL_KEY, str(DEFAULT_INTERVAL_SECONDS))
    )
    api_url = os.getenv(ENV_CLOUD_API_URL_KEY, DEFAULT_CLOUD_API_URL)
    DeviceFleet(
        bin_ids=_configured_bin_ids(), interval_seconds=interval_seconds
    ).run(lambda reading: _publish_reading(reading, api_url))


if __name__ == "__main__":
    main()
