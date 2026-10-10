import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from unittest.mock import patch
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

import gateway


@pytest.fixture
def client() -> TestClient:
    gateway.app.state.seen_envelopes = {}
    gateway.app.state.device_sessions = {}
    return TestClient(gateway.app)


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_forward_to_cloud_posts_mlkem_envelope() -> None:
    gateway.app.state.cloud_session = None
    responses = []
    for _ in range(2):
        response = Mock(status=201)
        response.read.return_value = b'{"id":1,"bin_id":"bin-1"}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        responses.append(response)

    class FakeSession:
        encapsulate_calls = 0

        def encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
            self.encapsulate_calls += 1
            assert public_key == b"cloud-public-key"
            return b"kem-ciphertext", b"shared-secret"

        def set_session_key(self, shared_secret: bytes) -> None:
            assert shared_secret == b"shared-secret"

        def encrypt(self, payload: bytes, kem_ciphertext: bytes) -> object:
            assert json.loads(payload)["bin_id"] == "bin-1"
            return type(
                "Encrypted",
                (),
                {
                    "kem_ciphertext": kem_ciphertext,
                    "nonce": b"123456789012",
                    "ciphertext": b"encrypted-reading",
                },
            )()

    with (
        patch(
            "gateway.read_cloud_public_key", return_value=b"cloud-public-key"
        ) as read_key,
        patch(
            "gateway.MlKemSession", return_value=FakeSession()
        ) as session_type,
        patch("gateway.urlopen", side_effect=responses) as urlopen,
    ):
        reading = gateway.ReadingPayload(
            bin_id="bin-1",
            fill_level=42,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        gateway.forward_to_cloud(reading)
        gateway.forward_to_cloud(reading)

    request = urlopen.call_args.args[0]
    assert isinstance(request, Request)
    first_request = urlopen.call_args_list[0].args[0]
    first_envelope = json.loads(first_request.data)
    assert set(first_envelope) == {
        "session_id",
        "kem_ciphertext_b64",
        "nonce_b64",
        "ciphertext_b64",
    }
    envelope = json.loads(request.data)
    assert set(envelope) == {"session_id", "nonce_b64", "ciphertext_b64"}
    assert envelope["session_id"] == first_envelope["session_id"]
    assert (
        base64.b64decode(first_envelope["kem_ciphertext_b64"])
        == b"kem-ciphertext"
    )
    assert base64.b64decode(first_envelope["nonce_b64"]) == b"123456789012"
    assert base64.b64decode(envelope["ciphertext_b64"]) == b"encrypted-reading"
    read_key.assert_called_once_with()
    assert session_type.return_value.encapsulate_calls == 1


def test_readings_accepts_authenticated_mlkem_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")
    recorded_at = datetime.now(timezone.utc).isoformat()

    class FakeSession:
        def decapsulate(self, ciphertext: bytes) -> bytes:
            assert ciphertext == b"kem-ciphertext"
            return b"shared-secret"

        def new_session(self, shared_secret: bytes) -> object:
            assert shared_secret == b"shared-secret"
            return self

        def decrypt(self, message: object) -> bytes:
            return json.dumps(
                {
                    "bin_id": "bin-1",
                    "fill_level": 42,
                    "recorded_at": recorded_at,
                }
            ).encode("utf-8")

    payload = {
        "session_id": "device-session",
        "kem_ciphertext": base64.b64encode(b"kem-ciphertext").decode("ascii"),
        "nonce": base64.b64encode(b"123456789012").decode("ascii"),
        "aes_ciphertext": base64.b64encode(b"aes-ciphertext").decode("ascii"),
    }
    cloud_response = {"id": 1, "bin_id": "bin-1", "fill_level": 42}
    with (
        patch.object(gateway, "get_ml_kem_session", return_value=FakeSession()),
        patch.object(
            gateway, "forward_to_cloud", return_value=cloud_response
        ) as forward,
    ):
        response = client.post(
            "/readings",
            json=payload,
            headers={"X-Device-ID": "bin-1", "X-API-Key": "secret"},
        )

    assert response.status_code == 201
    assert response.json() == cloud_response
    forwarded_reading = forward.call_args.args[0]
    assert forwarded_reading.bin_id == "bin-1"
    assert forwarded_reading.fill_level == 42


def test_readings_rejects_plain_and_base64_payloads(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")
    payloads = [
        {"bin_id": "bin-1", "fill_level": 42},
        {"payload_b64": base64.b64encode(b"reading").decode("ascii")},
    ]
    for payload in payloads:
        response = client.post(
            "/readings",
            json=payload,
            headers={"X-Device-ID": "bin-1", "X-API-Key": "secret"},
        )
        assert response.status_code == 400


def test_readings_require_valid_device_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")
    response = client.post("/readings", json={})
    assert response.status_code == 401


def test_readings_bind_bin_id_to_authenticated_device(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")

    class FakeSession:
        def decapsulate(self, ciphertext: bytes) -> bytes:
            return b"shared-secret"

        def new_session(self, shared_secret: bytes) -> object:
            assert shared_secret == b"shared-secret"
            return self

        def set_session_key(self, shared_secret: bytes) -> None:
            pass

        def decrypt(self, message: object) -> bytes:
            return json.dumps(
                {
                    "bin_id": "bin-2",
                    "fill_level": 42,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            ).encode("utf-8")

    payload = {
        "session_id": "binding-session",
        "kem_ciphertext": base64.b64encode(b"kem-ciphertext").decode("ascii"),
        "nonce": base64.b64encode(b"123456789012").decode("ascii"),
        "aes_ciphertext": base64.b64encode(b"aes-ciphertext").decode("ascii"),
    }
    with (
        patch.object(gateway, "get_ml_kem_session", return_value=FakeSession()),
        patch.object(gateway, "forward_to_cloud") as forward,
    ):
        response = client.post(
            "/readings",
            json=payload,
            headers={"X-Device-ID": "bin-1", "X-API-Key": "secret"},
        )

    assert response.status_code == 403
    forward.assert_not_called()


def test_readings_reject_stale_timestamp(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")
    stale_timestamp = (
        datetime.now(timezone.utc) - timedelta(seconds=61)
    ).isoformat()

    class FakeSession:
        def decapsulate(self, ciphertext: bytes) -> bytes:
            assert ciphertext == b"kem-ciphertext"
            return b"shared-secret" * 4

        def new_session(self, shared_secret: bytes) -> object:
            assert shared_secret == b"shared-secret" * 4
            return self

        def set_session_key(self, shared_secret: bytes) -> None:
            assert shared_secret == b"shared-secret" * 4

        def decrypt(self, message: object) -> bytes:
            return json.dumps(
                {
                    "bin_id": "bin-1",
                    "fill_level": 42,
                    "recorded_at": stale_timestamp,
                }
            ).encode("utf-8")

    payload = {
        "session_id": "stale-session",
        "kem_ciphertext": base64.b64encode(b"kem-ciphertext").decode("ascii"),
        "nonce": base64.b64encode(b"123456789012").decode("ascii"),
        "aes_ciphertext": base64.b64encode(b"aes-ciphertext").decode("ascii"),
    }

    with patch.object(
        gateway, "get_ml_kem_session", return_value=FakeSession()
    ):
        with patch.object(gateway, "forward_to_cloud") as forward:
            response = client.post(
                "/readings",
                json=payload,
                headers={"X-Device-ID": "bin-1", "X-API-Key": "secret"},
            )

    assert response.status_code == 400
    forward.assert_not_called()


def test_readings_reject_replayed_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")
    recorded_at = datetime.now(timezone.utc).isoformat()

    class FakeSession:
        def decapsulate(self, ciphertext: bytes) -> bytes:
            return b"shared-secret"

        def new_session(self, shared_secret: bytes) -> object:
            assert shared_secret == b"shared-secret"
            return self

        def set_session_key(self, shared_secret: bytes) -> None:
            pass

        def decrypt(self, message: object) -> bytes:
            return json.dumps(
                {
                    "bin_id": "bin-1",
                    "fill_level": 42,
                    "recorded_at": recorded_at,
                }
            ).encode("utf-8")

    payload = {
        "session_id": "replay-session",
        "kem_ciphertext": base64.b64encode(b"kem-ciphertext").decode("ascii"),
        "nonce": base64.b64encode(b"123456789012").decode("ascii"),
        "aes_ciphertext": base64.b64encode(b"aes-ciphertext").decode("ascii"),
    }
    headers = {"X-Device-ID": "bin-1", "X-API-Key": "secret"}
    with (
        patch.object(gateway, "get_ml_kem_session", return_value=FakeSession()),
        patch.object(gateway, "forward_to_cloud", return_value={"id": 1}),
    ):
        first_response = client.post("/readings", json=payload, headers=headers)
        second_response = client.post(
            "/readings", json=payload, headers=headers
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_crypto_public_key_returns_gateway_key(client: TestClient) -> None:
    gateway.app.state.gateway_public_key = b"gateway-public-key"
    response_obj = client.get("/crypto/public-key")
    assert response_obj.status_code == 200
    assert response_obj.json() == {
        "public_key_b64": base64.b64encode(b"gateway-public-key").decode(
            "ascii"
        )
    }


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        ({"kem_ciphertext": "!", "nonce": "", "aes_ciphertext": ""}, 400),
    ],
)
def test_readings_rejects_invalid_payloads(
    client: TestClient,
    payload: dict[str, str | int],
    status_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVICE_API_KEYS", "bin-1=secret")
    response = client.post(
        "/readings",
        json=payload,
        headers={"X-Device-ID": "bin-1", "X-API-Key": "secret"},
    )

    assert response.status_code == status_code
