"""FastAPI application for the cloud bin-monitoring service."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cloud.database import Database
from cloud.services import BinService, CloudService, MeasurementService
from models import Alert, Bin, BinReading


def _database_dsn() -> str:
    dsn = os.getenv("DATABASE_URL") or os.getenv("CLOUD_DB_DSN")
    if dsn:
        return dsn

    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    values = {key: os.getenv(key) for key in required}
    if not all(values.values()):
        raise RuntimeError(
            "Set DATABASE_URL or CLOUD_DB_DSN, or all of "
            "POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD"
        )

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@{host}:{port}/{values['POSTGRES_DB']}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    database = Database(dsn=_database_dsn())
    database.initialize()
    app.state.database = database
    app.state.bin_service = BinService()
    app.state.cloud_service = CloudService()
    app.state.measurement_service = MeasurementService()
    try:
        yield
    finally:
        database.close()


app = FastAPI(
    title="Post-Quantum Eco Route API",
    version="0.1.0",
    lifespan=lifespan,
)

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard"
app.mount(
    "/dashboard/static",
    StaticFiles(directory=DASHBOARD_DIR),
    name="dashboard-static",
)


class BinInput(BaseModel):
    bin_id: str = Field(min_length=1)


class BinResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bin_id: str


class ReadingInput(BaseModel):
    bin_id: str = Field(min_length=1)
    fill_level: int = Field(ge=0, le=100)
    recorded_at: datetime | None = None


class ReadingEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_b64: str = Field(min_length=1)


class EncryptedReadingEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kem_ciphertext_b64: str = Field(min_length=1)
    nonce_b64: str = Field(min_length=1)
    ciphertext_b64: str = Field(min_length=1)


class ReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    bin_id: str
    fill_level: int
    recorded_at: str


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    bin_id: str
    fill_level: int
    raised_at: str


def _bin_service(request: Request) -> BinService:
    return request.app.state.bin_service


def _measurement_service(request: Request) -> MeasurementService:
    return request.app.state.measurement_service


def _cloud_service(request: Request) -> CloudService:
    return request.app.state.cloud_service


@app.get("/crypto/public-key")
def crypto_public_key(request: Request) -> dict[str, str]:
    import base64

    return {
        "public_key_b64": base64.b64encode(
            _cloud_service(request).public_key
        ).decode("ascii")
    }


@app.post("/flush")
def flush(request: Request) -> None:
    _measurement_service(request).delete_all_alerts()
    _measurement_service(request).delete_all_measurements()
    return


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/bins", response_model=list[BinResponse])
def list_bins(request: Request) -> list[Bin]:
    return _bin_service(request).get_bins()


@app.post(
    "/bins",
    response_model=BinResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_bin(payload: BinInput, request: Request) -> Bin:
    try:
        return _bin_service(request).create_bin(payload.bin_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@app.get("/bins/{bin_id}", response_model=BinResponse)
def get_bin(bin_id: str, request: Request) -> Bin:
    result = _bin_service(request).get_bin(bin_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return result


@app.delete("/bins/{bin_id}", response_model=BinResponse)
def delete_bin(bin_id: str, request: Request) -> Bin:
    result = _bin_service(request).delete_bin(bin_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return result


@app.get("/readings", response_model=list[ReadingResponse])
def list_readings(request: Request) -> list[BinReading]:
    return _measurement_service(request).get_measurements()


@app.get("/alerts", response_model=list[AlertResponse])
def list_alerts(request: Request) -> list[Alert]:
    return _measurement_service(request).get_alerts()


@app.post(
    "/readings",
    response_model=ReadingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reading(
    payload: ReadingInput | ReadingEnvelope | EncryptedReadingEnvelope,
    request: Request,
) -> BinReading:
    if isinstance(payload, EncryptedReadingEnvelope):
        try:
            payload = ReadingInput.model_validate(
                _cloud_service(request).decrypt_reading(payload.model_dump())
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    elif isinstance(payload, ReadingEnvelope):
        try:
            decoded_payload = _cloud_service(request).decode_reading(
                payload.payload_b64
            )
            payload = ReadingInput.model_validate(decoded_payload)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    reading = BinReading.create(payload.bin_id, payload.fill_level)
    if payload.recorded_at is not None:
        reading = replace(
            reading,
            recorded_at=payload.recorded_at.isoformat(),
        )

    try:
        return _measurement_service(request).save_measurement(reading)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
