import base64
import json
from unittest.mock import Mock
from unittest.mock import patch
from urllib.request import Request

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


def test_forward_to_cloud_posts_base64_json_envelope() -> None:
    response = Mock(status=201)
    response.read.return_value = b'{"id":1,"bin_id":"bin-1"}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("gateway.urlopen", return_value=response) as urlopen:
        gateway.forward_to_cloud(
            gateway.ReadingPayload(bin_id="bin-1", fill_level=42)
        )

    request = urlopen.call_args.args[0]
    assert isinstance(request, Request)
    envelope = json.loads(request.data)
    decoded = base64.b64decode(envelope["payload_b64"], validate=True)
    assert json.loads(decoded) == {"bin_id": "bin-1", "fill_level": 42}


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


def test_readings_accepts_mlkem_encrypted_json(client: TestClient) -> None:
    class FakeSession:
        def decapsulate(self, ciphertext: bytes) -> bytes:
            assert ciphertext == b"kem-ciphertext"
            return b"shared-secret" * 4

        def set_session_key(self, shared_secret: bytes) -> None:
            assert shared_secret == b"shared-secret" * 4

        def decrypt(self, message: object) -> bytes:
            assert getattr(message, "nonce") == b"123456789012"
            assert getattr(message, "ciphertext") == b"aes-ciphertext"
            return json.dumps({"bin_id": "bin-1", "fill_level": 42}).encode(
                "utf-8"
            )

    payload = {
        "kem_ciphertext": base64.b64encode(b"kem-ciphertext").decode("ascii"),
        "nonce": base64.b64encode(b"123456789012").decode("ascii"),
        "aes_ciphertext": base64.b64encode(b"aes-ciphertext").decode("ascii"),
    }

    with patch.object(gateway, "get_ml_kem_session", return_value=FakeSession()):
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
