import base64
import json
from unittest.mock import Mock, patch
from urllib.request import Request

import pytest

from device.device_service import DeviceService
from models import BinReading


def test_publish_reading_posts_base64_json_to_gateway() -> None:
    response = Mock(status=201)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch.object(
        DeviceService, "_read_public_key", side_effect=RuntimeError
    ):
        with patch(
            "device.device_service.urlopen", return_value=response
        ) as urlopen:
            DeviceService("http://gateway:8001/").publish_reading(
                BinReading("bin-1", 42, "now")
            )

    request = urlopen.call_args.args[0]
    assert isinstance(request, Request)
    assert request.full_url == "http://gateway:8001/readings"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    envelope = json.loads(request.data)
    decoded_reading = base64.b64decode(envelope["payload_b64"], validate=True)
    assert json.loads(decoded_reading) == {"bin_id": "bin-1", "fill_level": 42}
    urlopen.assert_called_once_with(request, timeout=10)


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
            assert payload == b'{"bin_id": "bin-1", "fill_level": 42}'
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
            DeviceService("http://gateway:8001/ ").publish_reading(
                BinReading("bin-1", 42, "now")
            )

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


def test_publish_reading_rejects_unexpected_success_status() -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("device.device_service.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="unexpected status 200"):
            DeviceService("http://gateway:8001").publish_reading(
                BinReading("bin-1", 42, "now")
            )
