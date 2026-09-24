# post-quantum-eco-route

A simple Edge-Cloud simulation for municipal waste-bin monitoring and pickup optimization.

## Components

- `device/`: sensor-device folder that generates and prints periodic random
  bin-fill readings.
- `gateway.py`: establishes an ML-KEM session, decrypts, validates, and forwards readings.
- `crypto.py`: ML-KEM-768 key exchange and AES-GCM session encryption.
- `cloud.py`: stores readings through a callback and alerts above 80%.
- `database.py`: PostgreSQL schema and insert adapter.

## Local development

```powershell
python -m pip install -r requirements-dev.txt
pytest
python device/main.py
```

Set `device/.env` from `device/.env.example` to configure
`DEVICE_INTERVAL_SECONDS` (default `15`).

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

The project is intentionally a simulation without network servers. Production deployment should add device identity, replay protection, authenticated transport, secret management, and operational routing logic.
