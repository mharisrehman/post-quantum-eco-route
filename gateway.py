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


def forward_to_cloud(reading: ReadingPayload) -> dict[str, object]:
    request = Request(
        f"{CLOUD_API_URL}/readings",
        data=reading.model_dump_json(exclude_none=True).encode("utf-8"),
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
