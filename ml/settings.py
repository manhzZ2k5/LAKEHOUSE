from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}
    env: dict[str, str] = {}
    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _get_env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is not None and value != "":
        return value
    return default


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    postgres_db: str
    mlflow_tracking_uri: str

    @property
    def postgres_connection_string(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def load_settings(dotenv_path: str | Path = ".env") -> Settings:
    dotenv_path = Path(dotenv_path)
    env = {**_load_dotenv(dotenv_path), **os.environ}

    postgres_host = str(env.get("POSTGRES_HOST", "localhost"))
    postgres_port = int(env.get("POSTGRES_PORT", "5432"))
    postgres_user = str(env.get("POSTGRES_USER", "postgres"))
    postgres_password = str(env.get("POSTGRES_PASSWORD", "postgres"))
    postgres_db = str(env.get("POSTGRES_DB", "postgres"))

    tracking_uri = str(
        env.get("MLFLOW_TRACKING_URI")
        or _get_env("MLFLOW_TRACKING_URI")
        or "file:./mlruns"
    )

    # When running on host, people often expose the MLflow container on localhost:5000
    # but keep MLFLOW_TRACKING_URI=http://mlflow:5000 for intra-docker networking.
    if tracking_uri.startswith("http://mlflow:"):
        tracking_uri = tracking_uri.replace("http://mlflow:", "http://localhost:", 1)

    return Settings(
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        postgres_db=postgres_db,
        mlflow_tracking_uri=tracking_uri,
    )

