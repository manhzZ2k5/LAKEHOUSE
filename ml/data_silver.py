from __future__ import annotations

import os
from dataclasses import dataclass
import numpy as np
import pandas as pd
from deltalake import DeltaTable
from .settings import Settings

@dataclass(frozen=True)
class Dataset:
    df: pd.DataFrame
    source: str


def _storage_options(settings: Settings) -> dict:
    return {
        "AWS_ACCESS_KEY_ID":          os.getenv("MINIO_ROOT_USER", "minio_admin"),
        "AWS_SECRET_ACCESS_KEY":      os.getenv("MINIO_ROOT_PASSWORD", "minio_secret_secure_password_123"),
        "AWS_ENDPOINT_URL":           "http://minio:9000",
        "AWS_ALLOW_HTTP":             "true",
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
        "AWS_REGION":                 "us-east-1",
    }


def load_healthcare_silver(
    settings: Settings,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Dataset:
    """
    Load Silver Data and perform feature engineering for Healthcare Forecast.
    Returns: df with computed features & target base (`incidence_rate`).

    Features:
      vaccination_rate      — cumulative_fully_vaccinated / population  [0-1]
      new_confirmed_7d_avg  — rolling 7-day average of new_confirmed
      testing_rate          — new_tested / population  [0-1]
      elderly_pct           — (age_70_79 + age_80+) / population  [0-1]
      icu_rate_per_1m       — new_intensive_care_patients / population * 1_000_000  [normalized]
      search_trends_anosmia — Google Trends mất khứu giác  [0-100]
    """
    silver_path = "s3://silver-lake/covid_cleaned/"
    
    # Load Delta table
    dt = DeltaTable(silver_path, storage_options=_storage_options(settings))
    
    columns_to_read = [
        "date", "location_key", "subregion1_name", "new_confirmed", "new_tested", 
        "new_intensive_care_patients", "cumulative_persons_fully_vaccinated", 
        "population", "population_age_70_79", "population_age_80_and_older", 
        "search_trends_anosmia"
    ]
    
    table = dt.to_pyarrow_table(columns=columns_to_read)
    df = table.to_pandas()
    
    # Filtering country level and dates
    df = df[df["subregion1_name"].isna()].copy()
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date).date()]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date).date()]

    df = df[df["new_confirmed"] > 0].copy()
    df = df.dropna(subset=["date", "location_key"]).reset_index(drop=True)

    # Sort to avoid leakage before rolling computations
    df = df.sort_values(["location_key", "date"]).reset_index(drop=True)

    # Population denominator (avoid ZeroDivisionError)
    pop = df["population"].replace(0, np.nan)

    # ── Feature Engineering ──
    # 1. vaccination_rate
    df["vaccination_rate"] = (df["cumulative_persons_fully_vaccinated"] / pop).clip(0, 1).fillna(0)
    
    # 2. new_confirmed_7d_avg
    df["new_confirmed_7d_avg"] = (
        df.groupby("location_key")["new_confirmed"]
        .transform(lambda x: x.rolling(7, min_periods=1).mean())
        .fillna(0)
    )
    
    # 3. testing_rate
    df["testing_rate"] = (df["new_tested"] / pop).fillna(0)
    
    # 4. elderly_pct
    df["elderly_pct"] = (
        (df["population_age_70_79"].fillna(0) + df["population_age_80_and_older"].fillna(0)) / pop
    ).clip(0, 1).fillna(0)
    
    # 5. icu_rate_per_1m — normalize ICU patients theo dân số để so sánh công bằng giữa quốc gia
    #    (Dùng tỷ lệ / 1 triệu dân thay vì số tuyệt đối: Mỹ=50k vs VN=800 → không bias)
    df["icu_rate_per_1m"] = (df["new_intensive_care_patients"].fillna(0) / pop * 1_000_000).fillna(0)

    # 6. search_trends_anosmia (Raw input — đã normalize sẵn 0-100)
    df["search_trends_anosmia"] = df["search_trends_anosmia"].fillna(0)

    # ── Target Base ──
    # target base column to be shifted by `make_supervised_shift`
    df["incidence_rate"] = (df["new_confirmed"] / pop * 100_000).fillna(0)

    return Dataset(df=df, source=f"minio:{silver_path} (Healthcare Features)")


def load_policy_silver(
    settings: Settings,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Dataset:
    """
    Load Silver Data and perform feature engineering for Policy Effectiveness.
    """
    silver_path = "s3://silver-lake/covid_cleaned/"
    dt = DeltaTable(silver_path, storage_options=_storage_options(settings))
    
    columns_to_read = [
        "date", "location_key", "subregion1_name", "new_confirmed", 
        "cumulative_persons_fully_vaccinated", "population",
        "school_closing", "workplace_closing", "stay_at_home_requirements", 
        "stringency_index"
    ]
    
    table = dt.to_pyarrow_table(columns=columns_to_read)
    df = table.to_pandas()
    
    # Filter country level
    df = df[df["subregion1_name"].isna()].copy()
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date).date()]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date).date()]

    df = df.dropna(subset=["date", "location_key"]).reset_index(drop=True)
    df = df.sort_values(["location_key", "date"]).reset_index(drop=True)

    # Base filtering
    df = df[df["new_confirmed"] > 0]
    
    # Fill NAs for policy indices
    for col in ["school_closing", "workplace_closing", "stay_at_home_requirements", "stringency_index"]:
        df[col] = df[col].fillna(0)

    # Vaccination Rate Context
    pop = df["population"].replace(0, np.nan)
    df["vaccination_rate"] = (df["cumulative_persons_fully_vaccinated"] / pop).clip(0, 1).fillna(0)

    return Dataset(df=df, source=f"minio:{silver_path} (Policy Features)")
