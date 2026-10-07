import base64
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import gateway


@pytest.fixture
def client() -> TestClient:
    return TestClient(gateway.app)


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "payload",
    [
        {"bin_id": "bin-1", "fill_level": 42},
        {
            "payload_b64": base64.b64encode(
                json.dumps({"bin_id": "bin-1", "fill_level": 42}).encode(
                    "utf-8"
                )
            ).decode("ascii")
        },
    ],
)
def test_readings_accepts_plain_and_base64_json(
    client: TestClient, payload: dict[str, str | int]
) -> None:
    cloud_response = {"id": 1, "bin_id": "bin-1", "fill_level": 42}
    with patch.object(
        gateway, "forward_to_cloud", return_value=cloud_response
    ) as forward:
        response = client.post("/readings", json=payload)

    assert response.status_code == 201
    assert response.json() == cloud_response
    forwarded_reading = forward.call_args.args[0]
    assert forwarded_reading.bin_id == "bin-1"
    assert forwarded_reading.fill_level == 42


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        ({"payload_b64": "not-base64!"}, 400),
        (
            {"payload_b64": base64.b64encode(b"not json").decode("ascii")},
            400,
        ),
        ({"bin_id": "", "fill_level": 42}, 422),
        ({"bin_id": "bin-1", "fill_level": 101}, 422),
    ],
)
def test_readings_rejects_invalid_payloads(
    client: TestClient,
    payload: dict[str, str | int],
    status_code: int,
) -> None:
    response = client.post("/readings", json=payload)

    assert response.status_code == status_code
