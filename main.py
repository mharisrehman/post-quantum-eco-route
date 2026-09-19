"""Run the local device -> gateway -> cloud simulation."""

import os

from cloud import CloudService
from crypto import MlKemSession
from database import Database
from device import DeviceSimulator, WasteBin
from gateway import Gateway


def run() -> None:
    database = Database(
        os.getenv(
            "DATABASE_URL",
            "postgresql://eco_route:eco_route@localhost:5432/eco_route",
        )
    )
    database.initialize()
    cloud = CloudService(database.save_reading)
    gateway = Gateway(cloud.process, MlKemSession())
    device_session = MlKemSession()
    gateway.establish_session(device_session)

    def send(reading) -> None:
        alert = gateway.receive(device_session.encrypt(reading.to_bytes()))
        if alert:
            print(alert, flush=True)

    interval = float(os.getenv("BIN_INTERVAL_SECONDS", "10"))
    DeviceSimulator(
        [WasteBin("bin-001"), WasteBin("bin-002"), WasteBin("bin-003")],
        interval_seconds=interval,
    ).run(send)


if __name__ == "__main__":
    run()
