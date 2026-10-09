"""HTTP edge gateway for forwarding bin readings to the cloud API."""

import base64
import binascii
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    from ml_kem_crypto import EncryptedMessage, MlKemSession
except ModuleNotFoundError:
    import importlib.util
    from pathlib import Path

    module_path = Path(__file__).with_name("ml-kem_crypto.py")
    spec = importlib.util.spec_from_file_location("ml_kem_crypto", module_path)
    if spec is None or spec.loader is None:
        raise
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    EncryptedMessage = module.EncryptedMessage
    MlKemSession = module.MlKemSession

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
                session._private_key = base64.b64decode(
                    private_key_b64, validate=True
                )
                app.state.gateway_public_key = base64.b64decode(
                    public_key_b64, validate=True
                )
            except (binascii.Error, ValueError) as exc:
                raise RuntimeError(
                    "Gateway ML-KEM keys must be valid Base64"
                ) from exc
        else:
            app.state.gateway_public_key = session.create_keypair()
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


def decode_ml_kem_payload(payload: dict[str, object]) -> dict[str, object]:
    allowed_keys = {"kem_ciphertext", "nonce", "aes_ciphertext"}
    if set(payload) != allowed_keys:
        raise HTTPException(
            status_code=400,
            detail=(
                "ML-KEM requests must contain only kem_ciphertext, "
                "nonce and aes_ciphertext fields"
            ),
        )

    try:
        kem_ciphertext = base64.b64decode(
            payload["kem_ciphertext"], validate=True
        )
        nonce = base64.b64decode(payload["nonce"], validate=True)
        aes_ciphertext = base64.b64decode(
            payload["aes_ciphertext"], validate=True
        )
    except (TypeError, ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=400,
            detail="ML-KEM payload fields must be valid Base64",
        ) from exc

    session = get_ml_kem_session()
    if (
        isinstance(session, MlKemSession)
        and getattr(session, "_private_key", None) is None
    ):
        raise HTTPException(
            status_code=500,
            detail="Gateway ML-KEM private key is not configured",
        )

    try:
        shared_secret = session.decapsulate(kem_ciphertext)
        session.set_session_key(shared_secret)
        plaintext = session.decrypt(
            EncryptedMessage(kem_ciphertext, nonce, aes_ciphertext)
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - defensive; real pqcrypto errors vary
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
    cloud_public_key = read_cloud_public_key()
    session = MlKemSession()
    kem_ciphertext, shared_secret = session.encapsulate(cloud_public_key)
    session.set_session_key(shared_secret)
    encrypted_message = session.encrypt(reading_json, kem_ciphertext)
    payload = json.dumps(
        {
            "kem_ciphertext_b64": base64.b64encode(
                encrypted_message.kem_ciphertext
            ).decode("ascii"),
            "nonce_b64": base64.b64encode(encrypted_message.nonce).decode(
                "ascii"
            ),
            "ciphertext_b64": base64.b64encode(
                encrypted_message.ciphertext
            ).decode("ascii"),
        }
    ).encode("utf-8")
    request = Request(
        f"{CLOUD_API_URL}/readings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if response.status != 201:
                raise HTTPException(
                    status_code=502,
                    detail=f"Cloud API returned unexpected status {response.status}",
                )
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cloud API rejected the reading with status {exc.code}",
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=502, detail="Cloud API could not be reached"
        ) from exc


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

    if set(body) != {"kem_ciphertext", "nonce", "aes_ciphertext"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "Requests must contain only kem_ciphertext, nonce and "
                "aes_ciphertext fields"
            ),
        )
    encrypted_body = body
    body = decode_ml_kem_payload(body)

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
