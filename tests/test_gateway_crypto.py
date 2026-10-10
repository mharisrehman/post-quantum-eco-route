import base64
import json

from cloud.services import CloudService
from ml_kem_crypto import MlKemSession


class FakeKem:
    keygen_calls = 0
    decaps_calls = 0

    @staticmethod
    def keygen():
        FakeKem.keygen_calls += 1
        return b"public", b"private"

    @staticmethod
    def encaps(public_key):
        assert public_key == b"public"
        return b"kem-ciphertext", b"shared-secret" * 4

    @staticmethod
    def decaps(private_key, ciphertext):
        FakeKem.decaps_calls += 1
        assert private_key == b"private"
        assert ciphertext == b"kem-ciphertext"
        return b"shared-secret" * 4


def test_cloud_decrypts_multiple_readings_per_session_and_persists_keys(
    tmp_path,
) -> None:
    key_file = tmp_path / "cloud-ml-kem.json"
    cloud = CloudService(key_file, FakeKem)
    public_key = cloud.public_key
    sender = MlKemSession(FakeKem)
    kem_ciphertext, shared_secret = sender.encapsulate(public_key)
    sender.set_session_key(shared_secret)

    for index in range(2):
        encrypted = sender.encrypt(
            json.dumps({"bin_id": "bin-1", "fill_level": 40 + index}).encode(),
            kem_ciphertext,
        )
        envelope = {
            "session_id": "test-session",
            "nonce_b64": base64.b64encode(encrypted.nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(encrypted.ciphertext).decode(
                "ascii"
            ),
        }
        if index == 0:
            envelope["kem_ciphertext_b64"] = base64.b64encode(
                kem_ciphertext
            ).decode("ascii")

        assert cloud.decrypt_reading(envelope) == {
            "bin_id": "bin-1",
            "fill_level": 40 + index,
        }

    assert FakeKem.decaps_calls == 1
    restored_cloud = CloudService(key_file, FakeKem)
    assert restored_cloud.public_key == public_key
    assert FakeKem.keygen_calls == 1
