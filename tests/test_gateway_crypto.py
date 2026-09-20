from crypto import MlKemSession
from gateway import Gateway
from models import BinReading


class FakeKem:
    @staticmethod
    def keygen():
        return b"public", b"private"

    @staticmethod
    def encaps(public_key):
        assert public_key == b"public"
        return b"kem-ciphertext", b"shared-secret" * 4

    @staticmethod
    def decaps(private_key, ciphertext):
        assert private_key == b"private"
        assert ciphertext == b"kem-ciphertext"
        return b"shared-secret" * 4


def test_gateway_establishes_session_and_forwards_reading() -> None:
    device = MlKemSession(FakeKem)
    gateway_session = MlKemSession(FakeKem)
    forwarded = []
    gateway = Gateway(
        lambda reading: forwarded.append(reading) or None, gateway_session
    )

    gateway.establish_session(device)
    gateway.receive(device.encrypt(BinReading("bin-1", 42, "now").to_bytes()))

    assert forwarded == [BinReading("bin-1", 42, "now")]
