"""Edge gateway for secure validation and forwarding."""

from collections.abc import Callable

from models import BinReading


class Gateway:
    def __init__(
        self, forward: Callable[[BinReading], str | None], session: None
    ) -> None:
        self._forward = forward
        self._session = session

    def establish_session(self, device_session: None) -> None:
        return
        # public_key = self._session.create_keypair()
        # ciphertext, gateway_secret = device_session.encapsulate(public_key)
        # self._session.set_session_key(gateway_secret)
        # device_session.set_session_key(gateway_secret)

    def receive(self, message: None) -> str | None:
        return

        reading = BinReading.from_bytes(self._session.decrypt(message))
        return self._forward(reading)
