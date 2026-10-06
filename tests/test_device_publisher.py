import json
from unittest.mock import Mock, patch
from urllib.request import Request

import pytest

from device.main import _publish_reading
from models import BinReading


def test_publish_reading_posts_to_cloud_api() -> None:
    response = Mock(status=201)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("device.main.urlopen", return_value=response) as urlopen:
        _publish_reading(BinReading("bin-1", 42, "now"), "http://cloud:8000/")

    request = urlopen.call_args.args[0]
    assert isinstance(request, Request)
    assert request.full_url == "http://cloud:8000/readings"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {"bin_id": "bin-1", "fill_level": 42}
    urlopen.assert_called_once_with(request, timeout=10)


def test_publish_reading_rejects_unexpected_success_status() -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("device.main.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="unexpected status 200"):
            _publish_reading(
                BinReading("bin-1", 42, "now"), "http://cloud:8000"
            )
