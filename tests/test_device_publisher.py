import base64
import json
from unittest.mock import Mock, patch
from urllib.request import Request

import pytest

from device.device_service import DeviceService
from models import BinReading


def test_publish_reading_uses_ml_kem_encrypted_envelope() -> None:
    public_key_response = Mock(status=200)
    public_key_response.read.return_value = (
        b'{"public_key_b64": "cHVibGljLWtleQ=="}'
    )
    public_key_response.__enter__ = Mock(return_value=public_key_response)
    public_key_response.__exit__ = Mock(return_value=None)

    encrypted_response = Mock(status=201)
    encrypted_response.__enter__ = Mock(return_value=encrypted_response)
    encrypted_response.__exit__ = Mock(return_value=None)

    class FakeSession:
        def __init__(self) -> None:
            self.key = b""

        def encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
            assert public_key == b"public-key"
            return b"kem-ciphertext", b"shared-secret" * 4

        def set_session_key(self, shared_secret: bytes) -> None:
            assert shared_secret == b"shared-secret" * 4
            self.key = shared_secret

        def encrypt(self, payload: bytes, kem_ciphertext: bytes) -> object:
            reading = json.loads(payload)
            assert reading == {
                "bin_id": "bin-1",
                "fill_level": 42,
                "recorded_at": "now",
            }
            assert kem_ciphertext == b"kem-ciphertext"
            return type(
                "Encrypted",
                (),
                {
                    "kem_ciphertext": kem_ciphertext,
                    "nonce": b"123456789012",
                    "ciphertext": b"aes-ciphertext",
                },
            )()

    with patch("device.device_service.urlopen") as urlopen:
        urlopen.side_effect = [public_key_response, encrypted_response]
        with patch(
            "device.device_service.MlKemSession", return_value=FakeSession()
        ):
            DeviceService(
                "http://gateway:8001/ ", {"bin-1": "secret"}
            ).publish_reading(BinReading("bin-1", 42, "now"))

    request = urlopen.call_args.args[0]
    assert isinstance(request, Request)
    assert request.full_url == "http://gateway:8001/readings"
    assert urlopen.call_count == 2
    envelope = json.loads(request.data)
    assert envelope["kem_ciphertext"] == base64.b64encode(
        b"kem-ciphertext"
    ).decode("ascii")
    assert envelope["nonce"] == base64.b64encode(b"123456789012").decode(
        "ascii"
    )
    assert envelope["aes_ciphertext"] == base64.b64encode(
        b"aes-ciphertext"
    ).decode("ascii")
    assert request.get_header("X-device-id") == "bin-1"
    assert request.get_header("X-api-key") == "secret"


def test_publish_reading_does_not_fall_back_to_base64() -> None:
    service = DeviceService("http://gateway:8001", {"bin-1": "secret"})
    with (
        patch.object(
            DeviceService,
            "_read_public_key",
            side_effect=RuntimeError("key unavailable"),
        ),
        patch("device.device_service.urlopen") as urlopen,
        pytest.raises(RuntimeError, match="key unavailable"),
    ):
        service.publish_reading(BinReading("bin-1", 42, "now"))
    urlopen.assert_not_called()


def test_publish_reading_rejects_unexpected_success_status() -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    public_key_response = Mock(status=200)
    public_key_response.read.return_value = (
        b'{"public_key_b64": "cHVibGljLWtleQ=="}'
    )
    public_key_response.__enter__ = Mock(return_value=public_key_response)
    public_key_response.__exit__ = Mock(return_value=None)
    with patch(
        "device.device_service.urlopen",
        side_effect=[public_key_response, response],
    ):
        with pytest.raises(RuntimeError, match="unexpected status 200"):
            with patch("device.device_service.MlKemSession") as session_type:
                session = session_type.return_value
                session.encapsulate.return_value = (b"kem", b"secret")
                session.encrypt.return_value = type(
                    "Encrypted",
                    (),
                    {
                        "kem_ciphertext": b"kem",
                        "nonce": b"123456789012",
                        "ciphertext": b"ciphertext",
                    },
                )()
                DeviceService(
                    "http://gateway:8001", {"bin-1": "secret"}
                ).publish_reading(BinReading("bin-1", 42, "now"))
