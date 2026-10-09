from unittest.mock import Mock

import pytest

from cloud.repositories import BinRepository
from cloud.services import BinService
from models import Bin


@pytest.fixture
def repository() -> Mock:
    return Mock(spec=BinRepository)


def test_create_bin_persists_bin(repository: Mock) -> None:
    bin = Bin(bin_id="bin-1")
    repository.get.return_value = None
    repository.create.return_value = bin
    service = BinService(repository)

    created = service.create_bin("bin-1")

    assert created == bin
    repository.get.assert_called_once_with("bin-1")
    repository.create.assert_called_once_with(bin)


def test_create_bin_rejects_duplicate(repository: Mock) -> None:
    repository.get.return_value = Bin(bin_id="bin-1")
    service = BinService(repository)

    with pytest.raises(ValueError, match="bin already exists"):
        service.create_bin("bin-1")

    repository.create.assert_not_called()


def test_get_bins_reads_from_repository(repository: Mock) -> None:
    bins = [Bin(bin_id="bin-1"), Bin(bin_id="bin-2")]
    repository.get_all.return_value = bins
    service = BinService(repository)

    assert service.get_bins() == bins
    repository.get_all.assert_called_once_with()


def test_get_bin_reads_from_repository(repository: Mock) -> None:
    bin = Bin(bin_id="bin-1")
    repository.get.return_value = bin
    service = BinService(repository)

    assert service.get_bin("bin-1") == bin
    repository.get.assert_called_once_with("bin-1")


def test_delete_bin_deletes_from_repository(repository: Mock) -> None:
    bin = Bin(bin_id="bin-1")
    repository.delete.return_value = bin
    service = BinService(repository)

    assert service.delete_bin("bin-1") == bin
    repository.delete.assert_called_once_with("bin-1")
