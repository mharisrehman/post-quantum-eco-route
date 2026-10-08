"""Singleton PostgreSQL connection and schema management."""

from typing import Any


DEFAULT_BIN_IDS = ("bin-1", "bin-2", "bin-3")


class Database:
    _instance: "Database | None" = None

    def __new__(cls, dsn: str, connector: Any | None = None) -> "Database":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, dsn: str, connector: Any | None = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self.dsn = dsn
        self._connector = connector
        self._connection: Any | None = None
        self._initialized = True

    @classmethod
    def instance(cls) -> "Database":
        if cls._instance is None:
            raise RuntimeError("Database has not been configured")
        return cls._instance

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

    def connection(self) -> Any:
        if self._connection is None or getattr(
            self._connection, "closed", False
        ):
            self._connection = self._connect()
        return self._connection

    def initialize(self) -> None:
        connection = self.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bins (
                    bin_id TEXT PRIMARY KEY
                )
                """
            )
            for bin_id in DEFAULT_BIN_IDS:
                cursor.execute(
                    """
                    INSERT INTO bins (bin_id) VALUES (%s)
                    ON CONFLICT (bin_id) DO NOTHING
                    """,
                    (bin_id,),
                )
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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id BIGSERIAL PRIMARY KEY,
                    bin_id TEXT NOT NULL,
                    fill_level INTEGER NOT NULL CHECK (fill_level BETWEEN 0 AND 100),
                    raised_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        connection.commit()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def reset(self) -> None:
        self.close()
        type(self)._instance = None
