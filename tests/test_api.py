import base64
import json
from unittest.mock import Mock
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from cloud import api
from cloud.bin_service import BinService
from cloud.database import Database
from cloud.measurement_service import MeasurementService
from models import Bin, BinReading


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    database = Mock(spec=Database)
    bin_service = Mock(spec=BinService)
    measurement_service = Mock(spec=MeasurementService)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")
    monkeypatch.setattr(api, "Database", Mock(return_value=database))
    monkeypatch.setattr(api, "BinService", Mock(return_value=bin_service))
    monkeypatch.setattr(
        api,
        "MeasurementService",
        Mock(return_value=measurement_service),
    )

    return bin_service, measurement_service


@pytest.fixture
def client(services: tuple[Mock, Mock]) -> Generator[TestClient, None, None]:
    _ = services
    with TestClient(api.app) as test_client:
        yield test_client


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_bins(client: TestClient, services: tuple[Mock, Mock]) -> None:
    bin_service, _ = services
    bin_service.get_bins.return_value = [Bin("bin-1")]

    response = client.get("/bins")

    assert response.status_code == 200
    assert response.json() == [{"bin_id": "bin-1"}]
    bin_service.get_bins.assert_called_once_with()


def test_create_bin_returns_created_bin(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    bin_service, _ = services
    bin_service.create_bin.return_value = Bin("bin-1")

    response = client.post("/bins", json={"bin_id": "bin-1"})

    assert response.status_code == 201
    assert response.json() == {"bin_id": "bin-1"}
    bin_service.create_bin.assert_called_once_with("bin-1")


def test_create_bin_maps_duplicate_to_conflict(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    bin_service, _ = services
    bin_service.create_bin.side_effect = ValueError(
        "bin already exists for bin_id 'bin-1'"
    )

    response = client.post("/bins", json={"bin_id": "bin-1"})

    assert response.status_code == 409
    assert response.json() == {
        "detail": "bin already exists for bin_id 'bin-1'"
    }


def test_get_missing_bin_returns_not_found(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    bin_service, _ = services
    bin_service.get_bin.return_value = None

    response = client.get("/bins/missing")

    assert response.status_code == 404
    bin_service.get_bin.assert_called_once_with("missing")


def test_delete_bin_returns_deleted_bin(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    bin_service, _ = services
    bin_service.delete_bin.return_value = Bin("bin-1")

    response = client.delete("/bins/bin-1")

    assert response.status_code == 200
    assert response.json() == {"bin_id": "bin-1"}
    bin_service.delete_bin.assert_called_once_with("bin-1")


def test_list_readings(client: TestClient, services: tuple[Mock, Mock]) -> None:
    _, measurement_service = services
    measurement_service.get_measurements.return_value = [
        BinReading("bin-1", 50, "2026-01-01T00:00:00+00:00", id=1)
    ]

    response = client.get("/readings")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "bin_id": "bin-1",
            "fill_level": 50,
            "recorded_at": "2026-01-01T00:00:00+00:00",
        }
    ]


def test_create_reading_passes_payload_to_service(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services
    saved = BinReading("bin-1", 75, "2026-01-01T00:00:00+00:00", id=2)
    measurement_service.save_measurement.return_value = saved

    response = client.post(
        "/readings",
        json={
            "bin_id": "bin-1",
            "fill_level": 75,
            "recorded_at": "2026-01-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 2,
        "bin_id": "bin-1",
        "fill_level": 75,
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }
    measurement_service.save_measurement.assert_called_once_with(
        BinReading("bin-1", 75, "2026-01-01T00:00:00+00:00")
    )


def test_create_reading_accepts_base64_json_envelope(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services
    saved = BinReading("bin-1", 75, "2026-01-01T00:00:00+00:00", id=3)
    measurement_service.save_measurement.return_value = saved
    reading_json = json.dumps(
        {"bin_id": "bin-1", "fill_level": 75}
    ).encode("utf-8")

    response = client.post(
        "/readings",
        json={
            "payload_b64": base64.b64encode(reading_json).decode("ascii")
        },
    )

    assert response.status_code == 201
    assert response.json()["bin_id"] == "bin-1"
    saved_reading = measurement_service.save_measurement.call_args.args[0]
    assert saved_reading.bin_id == "bin-1"
    assert saved_reading.fill_level == 75


@pytest.mark.parametrize(
    "payload_b64",
    [
        "not-base64!",
        base64.b64encode(b"not json").decode("ascii"),
    ],
)
def test_create_reading_rejects_invalid_base64_envelope(
    client: TestClient,
    services: tuple[Mock, Mock],
    payload_b64: str,
) -> None:
    _, measurement_service = services

    response = client.post("/readings", json={"payload_b64": payload_b64})

    assert response.status_code == 400
    measurement_service.save_measurement.assert_not_called()


def test_create_reading_rejects_invalid_fill_level(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services

    response = client.post(
        "/readings",
        json={"bin_id": "bin-1", "fill_level": 101},
    )

    assert response.status_code == 422
    measurement_service.save_measurement.assert_not_called()


def test_create_reading_maps_unknown_bin_to_not_found(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services
    measurement_service.save_measurement.side_effect = ValueError(
        "unknown bin device for bin_id 'missing'"
    )

    response = client.post(
        "/readings",
        json={"bin_id": "missing", "fill_level": 20},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "unknown bin device for bin_id 'missing'"
    }
