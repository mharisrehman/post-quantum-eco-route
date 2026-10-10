"""HTTP edge gateway for forwarding bin readings to the cloud API."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ml_kem_crypto import (
    EncryptedMessage,
    MlKemSession,
    load_or_create_keypair,
)

DEFAULT_CLOUD_API_URL = "http://localhost:8000"
CLOUD_API_URL = os.getenv("CLOUD_API_URL", DEFAULT_CLOUD_API_URL).rstrip("/")
HTTP_TIMEOUT_SECONDS = 10
MAX_READING_AGE_SECONDS = 60

app = FastAPI(title="Eco Route Edge Gateway", version="0.1.0")


class ReadingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bin_id: str = Field(min_length=1)
    fill_level: int = Field(ge=0, le=100)
    recorded_at: str


@dataclass
class _ReadingSession:
    session_id: str
    crypto: MlKemSession
    kem_ciphertext: bytes
    device_id: str | None = None
    initialized: bool = False


def get_ml_kem_session() -> Any:
    session = getattr(app.state, "ml_kem_session", None)
    if session is None:
        session = MlKemSession()
        private_key_b64 = os.getenv("GATEWAY_ML_KEM_PRIVATE_KEY")
        public_key_b64 = os.getenv("GATEWAY_ML_KEM_PUBLIC_KEY")
        if bool(private_key_b64) != bool(public_key_b64):
            raise RuntimeError(
                "Gateway ML-KEM public and private keys must both be configured"
            )
        if private_key_b64 and public_key_b64:
            try:
                private_key = base64.b64decode(private_key_b64, validate=True)
                public_key = base64.b64decode(public_key_b64, validate=True)
                session.load_keypair(public_key, private_key)
                app.state.gateway_public_key = public_key
            except (binascii.Error, ValueError) as exc:
                raise RuntimeError(
                    "Gateway ML-KEM keys must be valid Base64"
                ) from exc
        else:
            key_file = Path(
                os.getenv(
                    "GATEWAY_ML_KEM_KEY_FILE",
                    Path(__file__).resolve().parent
                    / ".data"
                    / "gateway-ml-kem-768.json",
                )
            )
            app.state.gateway_public_key = load_or_create_keypair(
                session, key_file
            )
        app.state.ml_kem_session = session
    return session


def configured_device_keys() -> dict[str, str]:
    configured = os.getenv("DEVICE_API_KEYS", "")
    device_keys: dict[str, str] = {}
    for entry in configured.split(","):
        device_id, separator, api_key = entry.strip().partition("=")
        if separator and device_id and api_key:
            device_keys[device_id] = api_key
    return device_keys


def authenticate_device(request: FastAPIRequest) -> str:
    device_id = request.headers.get("X-Device-ID", "")
    api_key = request.headers.get("X-API-Key", "")
    device_keys = configured_device_keys()
    expected_key = device_keys.get(device_id)
    if expected_key is None:
        if not device_keys:
            raise HTTPException(
                status_code=500, detail="Device API keys are not configured"
            )
        raise HTTPException(
            status_code=401, detail="Invalid device credentials"
        )
    if not hmac.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=401, detail="Invalid device credentials"
        )
    return device_id


def decode_ml_kem_payload(
    payload: dict[str, object], device_id: str
) -> dict[str, object]:
    required_keys = {"session_id", "nonce", "aes_ciphertext"}
    if not required_keys.issubset(payload) or set(payload) not in (
        required_keys,
        required_keys | {"kem_ciphertext"},
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Encrypted readings require session_id, nonce and "
                "aes_ciphertext, with kem_ciphertext only when starting "
                "a session"
            ),
        )

    try:
        nonce = base64.b64decode(payload["nonce"], validate=True)
        aes_ciphertext = base64.b64decode(
            payload["aes_ciphertext"], validate=True
        )
        kem_ciphertext = (
            base64.b64decode(payload["kem_ciphertext"], validate=True)
            if "kem_ciphertext" in payload
            else None
        )
    except (TypeError, ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=400,
            detail="ML-KEM payload fields must be valid Base64",
        ) from exc

    session_id = payload["session_id"]
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(
            status_code=400, detail="session_id must be a non-empty string"
        )

    sessions: dict[str, _ReadingSession] = getattr(
        app.state, "device_sessions", {}
    )
    reading_session = sessions.get(session_id)
    if reading_session is None:
        if kem_ciphertext is None:
            raise HTTPException(
                status_code=410,
                detail="Unknown ML-KEM session; restart the key exchange",
            )
        key_session = get_ml_kem_session()
        if (
            isinstance(key_session, MlKemSession)
            and getattr(key_session, "_private_key", None) is None
        ):
            raise HTTPException(
                status_code=500,
                detail="Gateway ML-KEM private key is not configured",
            )
        try:
            shared_secret = key_session.decapsulate(kem_ciphertext)
            reading_session = _ReadingSession(
                session_id=session_id,
                crypto=key_session.new_session(shared_secret),
                kem_ciphertext=kem_ciphertext,
                device_id=device_id,
            )
            sessions[session_id] = reading_session
            app.state.device_sessions = sessions
        except Exception as exc:  # pragma: no cover - pqcrypto errors vary
            raise HTTPException(
                status_code=400,
                detail="ML-KEM payload could not be decrypted",
            ) from exc
    elif reading_session.device_id != device_id or (
        kem_ciphertext is not None
        and kem_ciphertext != reading_session.kem_ciphertext
    ):
        raise HTTPException(
            status_code=400, detail="ML-KEM session does not match the device"
        )

    try:
        plaintext = reading_session.crypto.decrypt(
            EncryptedMessage(
                reading_session.kem_ciphertext, nonce, aes_ciphertext
            )
        )
    except Exception as exc:  # pragma: no cover - AES-GCM errors vary
        raise HTTPException(
            status_code=400,
            detail="ML-KEM payload could not be decrypted",
        ) from exc

    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="ML-KEM decrypted payload must decode to a JSON object",
        ) from exc

    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400,
            detail="ML-KEM decrypted payload must decode to a JSON object",
        )
    return decoded


def forward_to_cloud(reading: ReadingPayload) -> dict[str, object]:
    reading_json = reading.model_dump_json(exclude_none=True).encode("utf-8")
    cloud_session: _ReadingSession | None = getattr(
        app.state, "cloud_session", None
    )
    if cloud_session is None:
        cloud_public_key = read_cloud_public_key()
        crypto = MlKemSession()
        kem_ciphertext, shared_secret = crypto.encapsulate(cloud_public_key)
        crypto.set_session_key(shared_secret)
        cloud_session = _ReadingSession(
            session_id=str(uuid.uuid4()),
            crypto=crypto,
            kem_ciphertext=kem_ciphertext,
        )
        app.state.cloud_session = cloud_session

    for attempt in range(2):
        encrypted_message = cloud_session.crypto.encrypt(
            reading_json, cloud_session.kem_ciphertext
        )
        envelope: dict[str, str] = {
            "session_id": cloud_session.session_id,
            "nonce_b64": base64.b64encode(encrypted_message.nonce).decode(
                "ascii"
            ),
            "ciphertext_b64": base64.b64encode(
                encrypted_message.ciphertext
            ).decode("ascii"),
        }
        if not cloud_session.initialized:
            envelope["kem_ciphertext_b64"] = base64.b64encode(
                cloud_session.kem_ciphertext
            ).decode("ascii")
        request = Request(
            f"{CLOUD_API_URL}/readings",
            data=json.dumps(envelope).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                if response.status != 201:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "Cloud API returned unexpected status "
                            f"{response.status}"
                        ),
                    )
                cloud_session.initialized = True
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 409 and cloud_session.initialized and attempt == 0:
                cloud_session = None
                app.state.cloud_session = None
                cloud_public_key = read_cloud_public_key()
                crypto = MlKemSession()
                kem_ciphertext, shared_secret = crypto.encapsulate(
                    cloud_public_key
                )
                crypto.set_session_key(shared_secret)
                cloud_session = _ReadingSession(
                    session_id=str(uuid.uuid4()),
                    crypto=crypto,
                    kem_ciphertext=kem_ciphertext,
                )
                app.state.cloud_session = cloud_session
                continue
            raise HTTPException(
                status_code=502,
                detail=f"Cloud API rejected the reading with status {exc.code}",
            ) from exc
        except URLError as exc:
            raise HTTPException(
                status_code=502, detail="Cloud API could not be reached"
            ) from exc
    raise HTTPException(
        status_code=502, detail="Cloud API session could not be established"
    )


def read_cloud_public_key() -> bytes:
    request = Request(
        f"{CLOUD_API_URL}/crypto/public-key",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Cloud API returned unexpected status "
                        f"{response.status}"
                    ),
                )
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cloud API rejected the public key request with status {exc.code}",
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=502, detail="Cloud API could not be reached"
        ) from exc
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail="Cloud API did not return a valid public key",
        ) from exc

    if not isinstance(payload, dict) or not isinstance(
        payload.get("public_key_b64"), str
    ):
        raise HTTPException(
            status_code=502,
            detail="Cloud API did not return a valid public key",
        )
    try:
        return base64.b64decode(payload["public_key_b64"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Cloud API did not return a valid public key",
        ) from exc


@app.get("/crypto/public-key")
def crypto_public_key() -> dict[str, str]:
    public_key = getattr(app.state, "gateway_public_key", None)
    if public_key is None:
        get_ml_kem_session()
        public_key = app.state.gateway_public_key
    return {"public_key_b64": base64.b64encode(public_key).decode("ascii")}


def validate_reading_timestamp(recorded_at: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="recorded_at must be an ISO-8601 timestamp"
        ) from exc
    if timestamp.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="recorded_at must include a timezone",
        )
    now = datetime.now(timezone.utc)
    if abs(now - timestamp.astimezone(timezone.utc)) > timedelta(
        seconds=MAX_READING_AGE_SECONDS
    ):
        raise HTTPException(
            status_code=400,
            detail="Reading timestamp is outside the allowed 60-second window",
        )
    return now


def reject_replayed_envelope(payload: dict[str, object], now: datetime) -> None:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cutoff = now - timedelta(seconds=MAX_READING_AGE_SECONDS)
    seen = getattr(app.state, "seen_envelopes", {})
    seen = {
        previous_digest: seen_at
        for previous_digest, seen_at in seen.items()
        if seen_at >= cutoff
    }
    if digest in seen:
        raise HTTPException(status_code=409, detail="Reading replay rejected")
    seen[digest] = now
    app.state.seen_envelopes = seen


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/readings", status_code=201)
async def receive_reading(request: FastAPIRequest) -> JSONResponse:
    device_id = authenticate_device(request)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail="Request body must be JSON"
        ) from exc

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Request body must be a JSON object"
        )

    if set(body) not in (
        {"session_id", "kem_ciphertext", "nonce", "aes_ciphertext"},
        {"session_id", "nonce", "aes_ciphertext"},
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Requests must contain only kem_ciphertext, nonce and "
                "aes_ciphertext fields"
            ),
        )
    encrypted_body = body
    body = decode_ml_kem_payload(body, device_id)

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Reading payload must be a JSON object"
        )

    try:
        reading = ReadingPayload.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if reading.bin_id != device_id:
        raise HTTPException(
            status_code=403,
            detail="Authenticated device cannot submit readings for this bin",
        )

    now = validate_reading_timestamp(reading.recorded_at)
    reject_replayed_envelope(encrypted_body, now)

    result = forward_to_cloud(reading)
    return JSONResponse(content=result, status_code=201)
