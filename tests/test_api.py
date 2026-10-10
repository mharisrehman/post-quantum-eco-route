import base64
import json
from unittest.mock import Mock
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from cloud import api
from cloud.services import BinService, MeasurementService
from cloud.database import Database
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


def test_flush_deletes_all_measurements_and_alerts(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services

    response = client.post("/flush")

    assert response.status_code == 200
    measurement_service.delete_all_alerts.assert_called_once_with()
    measurement_service.delete_all_measurements.assert_called_once_with()


def test_dashboard_serves_page_and_assets(client: TestClient) -> None:
    page = client.get("/dashboard")
    script = client.get("/dashboard/static/app.js")
    stylesheet = client.get("/dashboard/static/styles.css")

    assert page.status_code == 200
    assert "Bin network" in page.text
    assert "Device tier" in page.text
    assert "Gateway" in page.text
    assert "Cloud API" in page.text
    assert "ML-KEM-768" in page.text
    assert "Base64" not in page.text
    assert script.status_code == 200
    assert "refreshDashboard" in script.text
    assert stylesheet.status_code == 200
    assert ".pipeline-hop" in stylesheet.text


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


def test_create_reading_rejects_plain_json(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services

    response = client.post(
        "/readings",
        json={
            "bin_id": "bin-1",
            "fill_level": 75,
            "recorded_at": "2026-01-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 422
    measurement_service.save_measurement.assert_not_called()


def test_create_reading_decrypts_envelope_before_saving(
    client: TestClient,
    services: tuple[Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, measurement_service = services
    saved = BinReading("bin-1", 75, "2026-01-01T00:00:00+00:00", id=3)
    measurement_service.save_measurement.return_value = saved
    cloud_service = Mock()
    cloud_service.decrypt_reading.return_value = {
        "bin_id": "bin-1",
        "fill_level": 75,
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }
    monkeypatch.setattr(api, "_cloud_service", lambda request: cloud_service)

    response = client.post(
        "/readings",
        json={
            "session_id": "cloud-session",
            "kem_ciphertext_b64": "a2Vt",
            "nonce_b64": "bm9uY2U=",
            "ciphertext_b64": "Y2lwaGVydGV4dA==",
        },
    )

    assert response.status_code == 201
    assert response.json()["bin_id"] == "bin-1"
    cloud_service.decrypt_reading.assert_called_once_with(
        {
            "session_id": "cloud-session",
            "kem_ciphertext_b64": "a2Vt",
            "nonce_b64": "bm9uY2U=",
            "ciphertext_b64": "Y2lwaGVydGV4dA==",
        }
    )
    saved_reading = measurement_service.save_measurement.call_args.args[0]
    assert saved_reading.bin_id == "bin-1"
    assert saved_reading.fill_level == 75


def test_create_reading_rejects_base64_only_payload(
    client: TestClient,
    services: tuple[Mock, Mock],
) -> None:
    _, measurement_service = services

    response = client.post(
        "/readings",
        json={
            "payload_b64": base64.b64encode(
                json.dumps({"bin_id": "bin-1", "fill_level": 30}).encode()
            ).decode("ascii")
        },
    )

    assert response.status_code == 422
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, measurement_service = services
    measurement_service.save_measurement.side_effect = ValueError(
        "unknown bin device for bin_id 'missing'"
    )
    cloud_service = Mock()
    cloud_service.decrypt_reading.return_value = {
        "bin_id": "missing",
        "fill_level": 20,
    }
    monkeypatch.setattr(api, "_cloud_service", lambda request: cloud_service)

    response = client.post(
        "/readings",
        json={
            "session_id": "unknown-bin-session",
            "nonce_b64": "bm9uY2U=",
            "ciphertext_b64": "Y2lwaGVydGV4dA==",
            "kem_ciphertext_b64": "a2Vt",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "unknown bin device for bin_id 'missing'"
    }
