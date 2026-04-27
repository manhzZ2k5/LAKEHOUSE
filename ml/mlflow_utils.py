from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mlflow

from .settings import Settings


def configure_mlflow(settings: Settings) -> None:
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)


def write_model_pointer(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_model_pointer(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))

