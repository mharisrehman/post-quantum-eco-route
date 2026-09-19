# post-quantum-eco-route

A simple Edge-Cloud simulation for municipal waste-bin monitoring and pickup optimization.

## Components

- `device.py`: simulates bins and periodically emits fill readings.
- `gateway.py`: establishes an ML-KEM session, decrypts, validates, and forwards readings.
- `crypto.py`: ML-KEM-768 key exchange and AES-GCM session encryption.
- `cloud.py`: stores readings through a callback and alerts above 80%.
- `database.py`: PostgreSQL schema and insert adapter.

## Local development

```powershell
python -m pip install -r requirements.txt
pytest
python main.py
```

## Docker Compose

```powershell
docker compose up --build
```

The project is intentionally a simulation without network servers. Production deployment should add device identity, replay protection, authenticated transport, secret management, and operational routing logic.
