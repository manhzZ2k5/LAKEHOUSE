from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, text

from .settings import Settings


@dataclass(frozen=True)
class Dataset:
    df: pd.DataFrame
    source: str


def _build_select(columns: Iterable[str]) -> str:
    cols = ", ".join(columns)
    return cols


def load_covid_optimized_columns(
    settings: Settings,
    *,
    columns: list[str],
    table: str = "covid_optimized",
    country_level_only: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> Dataset:
    engine = create_engine(settings.postgres_connection_string)

    where = []
    if country_level_only:
        # Some ingestions infer wrong column types; comparing to '' may break.
        where.append("subregion1_name IS NULL")
        where.append("subregion2_name IS NULL")
    if start_date:
        where.append("date >= :start_date")
    if end_date:
        where.append("date <= :end_date")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""

    select_cols = _build_select(columns)
    query = text(f"SELECT {select_cols} FROM {table} {where_sql} {limit_sql}")
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    df = pd.read_sql(query, engine, params=params)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return Dataset(df=df, source=f"postgres:{settings.postgres_host}/{settings.postgres_db}.{table}")


def load_covid_optimized(
    settings: Settings,
    *,
    table: str = "covid_optimized",
    country_level_only: bool = True,
    limit: int | None = None,
) -> Dataset:
    """
    Loads the wide table produced by `load_covid_data_to_postgres.py`.

    Notes:
    - We prefer *country-level* rows to keep the ML tasks aligned with the Gold schema.
    - If you want subregion-level, set country_level_only=False.
    """
    engine = create_engine(settings.postgres_connection_string)

    where = []
    if country_level_only:
        # Google COVID data uses subregion1/subregion2 for admin levels.
        where.append("subregion1_name IS NULL")
        where.append("subregion2_name IS NULL")

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""

    query = text(f"SELECT * FROM {table} {where_sql} {limit_sql}")
    df = pd.read_sql(query, engine)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return Dataset(df=df, source=f"postgres:{settings.postgres_host}/{settings.postgres_db}.{table}")
