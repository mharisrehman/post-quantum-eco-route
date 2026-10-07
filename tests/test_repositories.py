from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

from cloud.repositories import AlertRepository, BinReadingRepository


def test_bin_reading_repository_serializes_database_timestamp() -> None:
    recorded_at = datetime(2026, 10, 7, 20, 53, 8, tzinfo=timezone.utc)
    cursor = Mock()
    cursor.fetchall.return_value = [(1, "bin-1", 50, recorded_at)]
    database = Mock()
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    database.connection.return_value.cursor.return_value = cursor_context
    repository = BinReadingRepository(database)

    readings = repository.get_all()

    assert readings[0].recorded_at == recorded_at.isoformat()


def test_alert_repository_serializes_database_timestamp() -> None:
    raised_at = datetime(2026, 10, 7, 20, 53, 8, tzinfo=timezone.utc)
    cursor = Mock()
    cursor.fetchall.return_value = [(1, "bin-1", 90, raised_at)]
    database = Mock()
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    database.connection.return_value.cursor.return_value = cursor_context
    repository = AlertRepository(database)

    alerts = repository.get_all()

    assert alerts[0].raised_at == raised_at.isoformat()
