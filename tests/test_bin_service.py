import pytest

from cloud import BinService
from models import Bin


def test_create_bin_adds_bin_to_in_memory_list() -> None:
    service = BinService()

    created = service.create_bin("bin-1")

    assert created == Bin(bin_id="bin-1")
    assert service.get_bins() == [Bin(bin_id="bin-1")]


def test_create_bin_rejects_missing_bin_id() -> None:
    service = BinService()

    with pytest.raises(ValueError, match="bin_id is required"):
        service.create_bin("")


def test_get_bin_returns_matching_bin_or_none() -> None:
    service = BinService([Bin(bin_id="bin-1")])

    assert service.get_bin("bin-1") == Bin(bin_id="bin-1")
    assert service.get_bin("bin-missing") is None


def test_delete_bin_removes_existing_bin() -> None:
    service = BinService([Bin(bin_id="bin-1"), Bin(bin_id="bin-2")])

    deleted = service.delete_bin("bin-1")

    assert deleted == Bin(bin_id="bin-1")
    assert service.get_bins() == [Bin(bin_id="bin-2")]


def test_delete_bin_returns_none_when_missing() -> None:
    service = BinService([Bin(bin_id="bin-1")])

    deleted = service.delete_bin("bin-missing")

    assert deleted is None
    assert service.get_bins() == [Bin(bin_id="bin-1")]
