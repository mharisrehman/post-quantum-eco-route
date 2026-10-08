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

    with patch("device.device_service.urlopen", return_value=response) as urlopen:
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


def test_publish_reading_rejects_unexpected_success_status() -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("device.device_service.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="unexpected status 200"):
            DeviceService("http://gateway:8001").publish_reading(
                BinReading("bin-1", 42, "now")
            )
