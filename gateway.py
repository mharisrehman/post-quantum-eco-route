"""HTTP edge gateway for forwarding bin readings to the cloud API."""

import base64
import binascii
import json
import os
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

app = FastAPI(title="Eco Route Edge Gateway", version="0.1.0")


class ReadingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bin_id: str = Field(min_length=1)
    fill_level: int = Field(ge=0, le=100)
    recorded_at: str | None = None


def decode_base64_payload(payload: str) -> bytes:
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="payload_b64 must be valid Base64"
        ) from exc


def get_ml_kem_session() -> MlKemSession:
    session = getattr(app.state, "ml_kem_session", None)
    if session is None:
        session = MlKemSession()
        private_key_b64 = os.getenv("GATEWAY_ML_KEM_PRIVATE_KEY")
        if private_key_b64:
            try:
                session._private_key = base64.b64decode(
                    private_key_b64, validate=True
                )
            except (binascii.Error, ValueError) as exc:
                raise RuntimeError(
                    "GATEWAY_ML_KEM_PRIVATE_KEY must be valid Base64"
                ) from exc
        app.state.ml_kem_session = session
    return session


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
    payload = json.dumps(
        {"payload_b64": base64.b64encode(reading_json).decode("ascii")}
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


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/readings", status_code=201)
async def receive_reading(request: FastAPIRequest) -> JSONResponse:
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

    if "payload_b64" in body:
        if set(body) != {"payload_b64"} or not isinstance(
            body["payload_b64"], str
        ):
            raise HTTPException(
                status_code=400,
                detail="Base64 requests must contain only a string payload_b64 field",
            )
        decoded = decode_base64_payload(body["payload_b64"])
        try:
            body = json.loads(decoded.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=400,
                detail="payload_b64 must decode to a JSON object",
            ) from exc
    elif any(
        key in body for key in ("kem_ciphertext", "nonce", "aes_ciphertext")
    ):
        if set(body) != {"kem_ciphertext", "nonce", "aes_ciphertext"}:
            raise HTTPException(
                status_code=400,
                detail=(
                    "ML-KEM requests must contain only kem_ciphertext, "
                    "nonce and aes_ciphertext fields"
                ),
            )
        body = decode_ml_kem_payload(body)

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Reading payload must be a JSON object"
        )

    try:
        reading = ReadingPayload.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = forward_to_cloud(reading)
    return JSONResponse(content=result, status_code=201)
