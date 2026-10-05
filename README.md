# post-quantum-eco-route

A simple Edge-Cloud simulation for municipal waste-bin monitoring and pickup optimization.

## Components

- `device/`: sensor-device folder that generates and prints periodic random
  bin-fill readings.
- `gateway.py`: establishes an ML-KEM session, decrypts, validates, and forwards readings.
- `crypto.py`: ML-KEM-768 key exchange and AES-GCM session encryption.
- `cloud/`: PostgreSQL-backed cloud CRUD services and FastAPI REST API.
- `cloud/api.py`: HTTP API for bin registration and measurement ingestion.
- `cloud/database.py`: singleton PostgreSQL connection and schema adapter.
- `cloud/repositories.py`: persistence repositories used by cloud services.

## Local development

```powershell
python -m pip install -r requirements-dev.txt
pytest
python device/main.py
```

Set `device/.env` from `device/.env.example` to configure
`DEVICE_INTERVAL_SECONDS` (default `15`).
Set `cloud/.env` from `cloud/.env.example` to configure database values.

## REST API

Run the API locally after starting PostgreSQL:

```powershell
uvicorn cloud.api:app --reload
```

The API exposes OpenAPI documentation at `http://localhost:8000/docs`.

- `GET /healthz`
- `GET|POST /bins`
- `GET|DELETE /bins/{bin_id}`
- `GET|POST /readings`

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

Production deployment should still add device identity, replay protection,
authenticated transport, secret management, and operational routing logic.
