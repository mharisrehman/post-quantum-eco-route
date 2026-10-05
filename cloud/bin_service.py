"""Business logic for managing known bin devices."""

from models import Bin
from cloud.repositories import BinRepository


class BinService:
    def __init__(
        self,
        repository: BinRepository | None = None,
    ) -> None:
        self._repository = repository or BinRepository()

    def create_bin(self, bin_id: str) -> Bin:
        if self.get_bin(bin_id) is not None:
            raise ValueError(f"bin already exists for bin_id '{bin_id}'")

        bin = Bin.create(bin_id=bin_id)
        return self._repository.create(bin)

    def get_bins(self) -> list[Bin]:
        return self._repository.get_all()

    def get_bin(self, bin_id: str) -> Bin | None:
        return self._repository.get(bin_id)

    def delete_bin(self, bin_id: str) -> Bin | None:
        return self._repository.delete(bin_id)
