"""Edge gateway for secure validation and forwarding."""

from collections.abc import Callable

from crypto import EncryptedMessage, MlKemSession
from models import BinReading


class Gateway:
    def __init__(
        self, forward: Callable[[BinReading], str | None], session: MlKemSession
    ) -> None:
        self._forward = forward
        self._session = session

    def establish_session(self, device_session: MlKemSession) -> None:
        public_key = self._session.create_keypair()
        ciphertext, gateway_secret = device_session.encapsulate(public_key)
        self._session.set_session_key(gateway_secret)
        device_session.set_session_key(gateway_secret)

    def receive(self, message: EncryptedMessage) -> str | None:
        reading = BinReading.from_bytes(self._session.decrypt(message))
        return self._forward(reading)
