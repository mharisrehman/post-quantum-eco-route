"""Database repositories used by cloud services."""

from typing import Any

from models import Alert, Bin, BinReading

from cloud.database import Database


class BinRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._database = database or Database.instance()

    def create(self, bin: Bin) -> Bin:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO bins (bin_id) VALUES (%s) RETURNING bin_id",
                (bin.bin_id,),
            )
            row = cursor.fetchone()
        connection.commit()
        return Bin(bin_id=row[0])

    def get_all(self) -> list[Bin]:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT bin_id FROM bins ORDER BY bin_id")
            rows = cursor.fetchall()
        return [Bin(bin_id=row[0]) for row in rows]

    def get(self, bin_id: str) -> Bin | None:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT bin_id FROM bins WHERE bin_id = %s", (bin_id,)
            )
            row = cursor.fetchone()
        return Bin(bin_id=row[0]) if row else None

    def delete(self, bin_id: str) -> Bin | None:
        existing = self.get(bin_id)
        if existing is None:
            return None
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM bins WHERE bin_id = %s", (bin_id,))
        connection.commit()
        return existing


class BinReadingRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._database = database or Database.instance()

    def create(self, reading: BinReading) -> BinReading:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO bin_readings (bin_id, fill_level, recorded_at)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (reading.bin_id, reading.fill_level, reading.recorded_at),
            )
            row: Any = cursor.fetchone()
        connection.commit()
        return BinReading(
            bin_id=reading.bin_id,
            fill_level=reading.fill_level,
            recorded_at=reading.recorded_at,
            id=row[0],
        )

    def get_all(self) -> list[BinReading]:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bin_id, fill_level, recorded_at
                FROM bin_readings ORDER BY recorded_at, id
                """
            )
            rows = cursor.fetchall()
        return [
            BinReading(
                id=row[0],
                bin_id=row[1],
                fill_level=row[2],
                recorded_at=row[3].isoformat(),
            )
            for row in rows
        ]


class AlertRepository:
    def __init__(self, database: Database | None = None) -> None:
        self._database = database or Database.instance()

    def create(self, alert: Alert) -> Alert:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO alerts (bin_id, fill_level, raised_at)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (alert.bin_id, alert.fill_level, alert.raised_at),
            )
            row: Any = cursor.fetchone()
        connection.commit()
        return Alert(
            bin_id=alert.bin_id,
            fill_level=alert.fill_level,
            raised_at=alert.raised_at,
            id=row[0],
        )

    def get_all(self) -> list[Alert]:
        connection = self._database.connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bin_id, fill_level, raised_at
                FROM alerts ORDER BY raised_at, id
                """
            )
            rows = cursor.fetchall()
        return [
            Alert(
                id=row[0],
                bin_id=row[1],
                fill_level=row[2],
                raised_at=row[3].isoformat(),
            )
            for row in rows
        ]
