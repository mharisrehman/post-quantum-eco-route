"""PostgreSQL persistence adapter."""

from contextlib import closing
from typing import Any

from models import BinReading


class Database:
    def __init__(self, dsn: str, connector: Any | None = None) -> None:
        self.dsn = dsn
        self._connector = connector

    def _connect(self) -> Any:
        if self._connector is not None:
            return self._connector(self.dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Install psycopg[binary] to use PostgreSQL"
            ) from exc
        return psycopg.connect(self.dsn)

    def initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bin_readings (
                        id BIGSERIAL PRIMARY KEY,
                        bin_id TEXT NOT NULL,
                        fill_level INTEGER NOT NULL CHECK (fill_level BETWEEN 0 AND 100),
                        recorded_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            connection.commit()

    def save_reading(self, reading: BinReading) -> None:
        with closing(self._connect()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO bin_readings (bin_id, fill_level, recorded_at) VALUES (%s, %s, %s)",
                    (reading.bin_id, reading.fill_level, reading.recorded_at),
                )
            connection.commit()
