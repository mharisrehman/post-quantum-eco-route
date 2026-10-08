# post-quantum-eco-route

A simple Edge-Cloud simulation for municipal waste-bin monitoring and pickup optimization.

## Components

- `device/`: sensor-device folder that generates periodic readings for multiple bins and sends them to the cloud API.
- `gateway.py`: HTTP edge gateway that accepts JSON or Base64-encoded readings and forwards them to the cloud API.
- `cloud/cloud_service.py`: decodes Base64 JSON envelopes received from the gateway.
- `ml-kem_crypto.py`: ML-KEM-768 key exchange and AES-GCM session encryption primitives.
- `cloud/`: PostgreSQL-backed cloud CRUD services and FastAPI REST API.
- `cloud/api.py`: HTTP API for bin registration and measurement ingestion.
- `cloud/database.py`: singleton PostgreSQL connection and schema adapter.
- `cloud/repositories.py`: persistence repositories used by cloud services.

## Local development

```powershell
python -m pip install -r requirements-dev.txt
pytest
```

Set `device/.env` from `device/.env.example` to configure
`DEVICE_INTERVAL_SECONDS` (default `5`; the example sets `15`),
`DEVICE_BIN_IDS` (comma-separated
bin IDs; defaults to `bin-1,bin-2,bin-3`), and `CLOUD_API_URL` (the device's
gateway URL; default `http://localhost:8001`). If `DEVICE_BIN_IDS` is unset,
`DEVICE_BIN_ID` can select a single device.
Database initialization creates `bin-1`, `bin-2`, and `bin-3` by default.

## REST API

Start PostgreSQL and the API using the project Compose configuration:

```powershell
docker compose up --build postgres api
```

The API exposes OpenAPI documentation at `http://localhost:8000/docs`.
With the API running, start the simulator in another terminal:

```powershell
python -m device.main
```

The gateway listens at `http://localhost:8001`. The device service posts
readings as a Base64 JSON envelope:

```json
{"payload_b64":"eyJiaW5faWQiOiJiaW4tMSIsImZpbGxfbGV2ZWwiOjQyfQ=="}
```

The Base64 value must decode to a JSON reading (for example,
`{"bin_id":"bin-1","fill_level":42}`). The gateway decodes and validates the
device reading, then sends a Base64 JSON envelope to the cloud API. The cloud
service decodes it before validation and storage. Base64 is an encoding, not
encryption; the gateway does not currently establish an ML-KEM session.

- `GET /healthz`
- `GET|POST /bins`
- `GET|DELETE /bins/{bin_id}`
- `GET|POST /readings`
- `GET /alerts` (fill levels above 80%)

For cloud deployment, set `DATABASE_URL` to the provider's PostgreSQL
connection string. The container listens on the provider's `PORT` value
(defaulting to `8000` locally).

### Format & Lint

After finishing a task / feature / addition, run the following commands from project root to catch bad conventions and errors. Formatter then adjusts whitespace and line breaks so that style is consistent between contributors.

As a good convention, it's recommended to setup the formatter as an automatic code-action that is ran on save within your editor.

```powershell
ruff check .
ruff format .
```

## Docker Compose

```powershell
docker compose up --build
```

Compose starts PostgreSQL, the cloud API, the gateway, and the device
simulator. The device service Base64-encodes readings for the gateway, which
decodes them, then Base64-encodes them for the cloud service to decode. View
stored readings at
`GET /readings` and alerts at `GET /alerts`.

Production deployment should still add device identity, replay protection,
authenticated transport, secret management, and operational routing logic.
