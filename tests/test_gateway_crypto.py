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
