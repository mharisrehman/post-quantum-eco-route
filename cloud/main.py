"""Runnable entrypoint that initializes cloud database schema and exits."""

from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud.database import Database

ENV_DB_DSN_KEY = "CLOUD_DB_DSN"
ENV_DB_NAME_KEY = "POSTGRES_DB"
ENV_DB_USER_KEY = "POSTGRES_USER"
ENV_DB_PASSWORD_KEY = "POSTGRES_PASSWORD"
ENV_DB_HOST_KEY = "POSTGRES_HOST"
ENV_DB_PORT_KEY = "POSTGRES_PORT"
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = "5432"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        os.environ.setdefault(key.strip(), value.strip())


def _build_dsn_from_postgres_env() -> str:
    db_name = os.getenv(ENV_DB_NAME_KEY)
    db_user = os.getenv(ENV_DB_USER_KEY)
    db_password = os.getenv(ENV_DB_PASSWORD_KEY)
    db_host = os.getenv(ENV_DB_HOST_KEY, DEFAULT_DB_HOST)
    db_port = os.getenv(ENV_DB_PORT_KEY, DEFAULT_DB_PORT)

    if not db_name or not db_user or not db_password:
        raise RuntimeError(
            "Set CLOUD_DB_DSN or all of POSTGRES_DB, POSTGRES_USER, and "
            "POSTGRES_PASSWORD to initialize PostgreSQL"
        )

    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def main() -> None:
    cloud_dir = Path(__file__).parent
    _load_env_file(cloud_dir / ".env")

    dsn = os.getenv(ENV_DB_DSN_KEY) or _build_dsn_from_postgres_env()

    Database(dsn=dsn).initialize()


if __name__ == "__main__":
    main()
