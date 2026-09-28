"""Business logic for managing known bin devices."""

from models import Bin


class BinService:
    def __init__(self, bins: list[Bin] | None = None) -> None:
        self._bins = bins if bins is not None else []

    def create_bin(self, bin_id: str) -> Bin:
        if any(bin.bin_id == bin_id for bin in self._bins):
            raise ValueError(f"bin already exists for bin_id '{bin_id}'")

        bin = Bin.create(bin_id=bin_id)
        self._bins.append(bin)
        return bin

    def get_bins(self) -> list[Bin]:
        return self._bins

    def get_bin(self, bin_id: str) -> Bin | None:
        return next((bin for bin in self._bins if bin.bin_id == bin_id), None)

    def delete_bin(self, bin_id: str) -> Bin | None:
        bin = self.get_bin(bin_id)
        if bin:
            self._bins.remove(bin)
        return bin
