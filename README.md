# post-quantum-eco-route

A simple Edge-Cloud simulation for municipal waste-bin monitoring and pickup optimization.

## Components

- `device/`: sensor-device folder that generates periodic readings for multiple bins and sends them to the cloud API.
- `gateway.py`: HTTP edge gateway that authenticates devices, decrypts ML-KEM readings, and re-encrypts them for the cloud API.
- `cloud/cloud_service.py`: decrypts ML-KEM/AES-GCM readings received from the gateway.
- `dashboard/`: live admin dashboard for bin readings, alerts, and the system pipeline.
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
`DEVICE_INTERVAL_SECONDS`, `DEVICE_BIN_IDS`, `CLOUD_API_URL`, and
`DEVICE_API_KEYS`. The API key list uses comma-separated `device-id=key`
pairs; each configured device ID must match a bin ID. Configure the same key
map for the gateway. If `DEVICE_BIN_IDS` is unset, `DEVICE_BIN_ID` can select
a single device.
Database initialization creates `bin-1`, `bin-2`, and `bin-3` by default.

## REST API

Start PostgreSQL and the API using the project Compose configuration:

```powershell
docker compose up --build postgres api
```

The API exposes OpenAPI documentation at `http://localhost:8000/docs`.
Start the gateway with the API, then start the simulator in another terminal:

```powershell
docker compose up --build gateway
python -m device.main
```

The gateway listens at `http://localhost:8001`. Readings must use the ML-KEM
encrypted envelope and include valid `X-Device-ID` and `X-API-Key` headers.
The authenticated device ID must match the decrypted reading's `bin_id`, and
the reading timestamp must be within 60 seconds of gateway time. The gateway
rejects plain JSON, Base64-only payloads, stale readings, and duplicate
encrypted envelopes. It re-encrypts accepted readings with the cloud's public
key before forwarding them.

- `GET /healthz`
- `GET|POST /bins`
- `GET|DELETE /bins/{bin_id}`
- `GET|POST /readings`
- `GET /alerts` (fill levels above 80%)
- `GET /crypto/public-key`

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

Start the system and open the dashboard in your browser with PowerShell:

```powershell
.\dashboard\start_dashboard.ps1
```

The dashboard is served at `http://localhost:8000/dashboard`. It refreshes
readings, bin status, and alerts every five seconds. The pipeline diagram shows
the configured component path; detailed per-stage live progress is not yet
instrumented.

```powershell
docker compose up --build
```

Compose starts PostgreSQL, the cloud API, the gateway, and the device
simulator. For local testing, Compose supplies development-only device keys
for `bin-1`, `bin-2`, and `bin-3`. Set `DEVICE_API_KEYS` in the root `.env`
file to override them; use unique, secret values outside local testing. View
stored readings at `GET /readings` and alerts at `GET /alerts`.

HTTPS remains deferred as requested, so use this setup only on a trusted
network. Production deployments should configure durable gateway ML-KEM keys
with `GATEWAY_ML_KEM_PUBLIC_KEY` and `GATEWAY_ML_KEM_PRIVATE_KEY`, provision
strong device API keys, and enable HTTPS.
