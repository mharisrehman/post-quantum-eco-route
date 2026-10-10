"""ML-KEM-768 key exchange and AES-GCM message encryption."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class EncryptedMessage:
    kem_ciphertext: bytes
    nonce: bytes
    ciphertext: bytes


class MlKemSession:
    def __init__(self, kem: Any | None = None) -> None:
        if kem is None:
            try:
                from pqcrypto.kem import ml_kem_768 as kem
            except ImportError as exc:
                raise RuntimeError("Install pqcrypto to use ML-KEM") from exc
        self._kem = kem
        self._public_key: bytes | None = None
        self._private_key: bytes | None = None
        self._session_key: bytes | None = None

    def create_keypair(self) -> bytes:
        public_key, self._private_key = self._kem.keygen()
        self._public_key = public_key
        return public_key

    @property
    def private_key(self) -> bytes:
        if self._private_key is None:
            raise RuntimeError("create_keypair must be called first")
        return self._private_key

    def load_keypair(self, public_key: bytes, private_key: bytes) -> None:
        self._private_key = private_key
        self._public_key = public_key

    def encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
        return self._kem.encaps(public_key)

    def new_session(self, shared_secret: bytes) -> MlKemSession:
        session = MlKemSession(self._kem)
        session.set_session_key(shared_secret)
        return session

    def decapsulate(self, ciphertext: bytes) -> bytes:
        if self._private_key is None:
            raise RuntimeError("create_keypair must be called first")
        return self._kem.decaps(self._private_key, ciphertext)

    def set_session_key(self, shared_secret: bytes) -> None:
        self._session_key = shared_secret[:32]

    def encrypt(
        self, payload: bytes, kem_ciphertext: bytes
    ) -> EncryptedMessage:
        if self._session_key is None:
            raise RuntimeError("session key has not been established")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._session_key).encrypt(nonce, payload, None)
        return EncryptedMessage(kem_ciphertext, nonce, ciphertext)

    def decrypt(self, message: EncryptedMessage) -> bytes:
        if self._session_key is None:
            raise RuntimeError("session key has not been established")
        return AESGCM(self._session_key).decrypt(
            message.nonce, message.ciphertext, None
        )


def load_or_create_keypair(
    session: MlKemSession, key_file: str | Path
) -> bytes:
    path = Path(key_file)
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            public_key = base64.b64decode(
                stored["public_key_b64"], validate=True
            )
            private_key = base64.b64decode(
                stored["private_key_b64"], validate=True
            )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(f"ML-KEM key file is invalid: {path}") from exc
        session.load_keypair(public_key, private_key)
        if os.name != "nt":
            path.chmod(0o600)
        return public_key

    path.parent.mkdir(parents=True, exist_ok=True)
    public_key = session.create_keypair()
    serialized = json.dumps(
        {
            "public_key_b64": base64.b64encode(public_key).decode("ascii"),
            "private_key_b64": base64.b64encode(session.private_key).decode(
                "ascii"
            ),
        }
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return load_or_create_keypair(session, path)
    with os.fdopen(descriptor, "w", encoding="utf-8") as key_file_handle:
        key_file_handle.write(serialized)
        key_file_handle.flush()
        os.fsync(key_file_handle.fileno())
    return public_key


def encode_message(message: EncryptedMessage) -> dict[str, str]:
    return {
        "kem_ciphertext_b64": base64.b64encode(message.kem_ciphertext).decode(
            "ascii"
        ),
        "nonce_b64": base64.b64encode(message.nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(message.ciphertext).decode("ascii"),
    }


def decode_message(payload: dict[str, str]) -> EncryptedMessage:
    try:
        return EncryptedMessage(
            base64.b64decode(payload["kem_ciphertext_b64"], validate=True),
            base64.b64decode(payload["nonce_b64"], validate=True),
            base64.b64decode(payload["ciphertext_b64"], validate=True),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError("Invalid encrypted reading envelope") from exc
