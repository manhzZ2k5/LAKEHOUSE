"""
Data Layer cho ML Pipeline — Chiến lược Hybrid Source:

  Bài toán Y tế  → Silver Lake (MinIO/Delta) — features theo Gold schema
  Bài toán Chính sách → PostgreSQL (covid_optimized đã fix OJM)

Gold Schema mapping:
  fact_covid_cases      → new_confirmed, new_confirmed_7d_avg (xu hướng)
  fact_vaccination      → vaccination_rate = cumulative_fully_vacc / population
  fact_healthcare_system → icu_rate_per_1m, testing_rate
  fact_social_behavior  → search_trends_anosmia (early COVID signal)
  dim_location          → elderly_pct = (age_70_79 + age_80+) / population
  fact_policy_impact    → school_closing, workplace_closing, stringency_index, stay_at_home

Lưu ý kỹ thuật:
  - Silver fillna(0) toàn bộ numeric → population có thể = 0 → dùng replace(0, np.nan) trước chia
  - COVID data lịch sử: 2020-01-01 → 2022-09-16 (đã kết thúc)
    → KHÔNG dùng today - 730 ngày (sẽ ra năm 2024, không có data)
  - Sắp xếp theo [location_key, date] TRƯỚC KHI tính rolling average
  - new_confirmed_7d_avg tại T dùng data T-6→T → predict incidence_rate tại T+14 ✅ (không leakage)

Dagster Lineage:
  silver_covid_data (Silver/MinIO/Delta Lake)
        ↓  [deps=["silver_covid_data"]]
  auto_train_healthcare_forecast  → Silver Lake  ✅
  auto_train_policy_effectiveness → PostgreSQL   ✅ (school_closing đúng, OJM đã fix)
"""
import os
import logging
import numpy as np
import pandas as pd
from datetime import datetime

logger = logging.getLogger("ml_data_silver")

# ── Cấu hình MinIO ─────────────────────────────────────────────────────────────
SILVER_PATH    = "s3://silver-lake/covid_cleaned/"
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "minio_admin")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "minio_secret_secure_password_123")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT",   "http://minio:9000")

# ── Cấu hình PostgreSQL ────────────────────────────────────────────────────────
PG_HOST = "postgres"
PG_PORT = "5432"


def _storage_options() -> dict:
    return {
        "AWS_ACCESS_KEY_ID":          MINIO_ACCESS,
        "AWS_SECRET_ACCESS_KEY":      MINIO_SECRET,
        "AWS_ENDPOINT_URL":           MINIO_ENDPOINT,
        "AWS_ALLOW_HTTP":             "true",
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
        "AWS_REGION":                 "us-east-1",
    }


def _pg_engine():
    from sqlalchemy import create_engine
    pg_user = os.getenv("POSTGRES_USER", "admin")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "admin123")
    pg_db   = os.getenv("POSTGRES_DB", "lakehouse_db")
    return create_engine(f"postgresql://{pg_user}:{pg_pass}@{PG_HOST}:{PG_PORT}/{pg_db}")


# ═══════════════════════════════════════════════════════════════════════════════
# BÀI TOÁN 1: DỰ BÁO Y TẾ — nguồn: Silver Lake
#
# Target: incidence_rate_14d = new_confirmed_future / population * 100,000
# (ca / 100,000 dân — so sánh được giữa các quốc gia)
#
# Features theo Gold schema:
#   fact_vaccination      → vaccination_rate
#   fact_covid_cases      → new_confirmed_7d_avg (xu hướng 7 ngày)
#   fact_healthcare_system → testing_rate, new_intensive_care_patients
#   fact_social_behavior  → search_trends_anosmia
#   dim_location          → elderly_pct
# ═══════════════════════════════════════════════════════════════════════════════

HEALTHCARE_COLUMNS = [
    "date", "location_key",
    # fact_covid_cases group
    "new_confirmed",
    # fact_healthcare_system group
    "new_tested",
    "new_intensive_care_patients",
    # fact_vaccination group
    "cumulative_persons_fully_vaccinated",
    # dim_location group
    "population",
    "population_age_70_79",
    "population_age_80_and_older",
    # fact_social_behavior group
    "search_trends_anosmia",
]


def load_healthcare_data() -> pd.DataFrame:
    """
    Đọc dữ liệu Healthcare từ Silver Lake, tính các derived features theo Gold schema.

    Derived features:
      vaccination_rate      = cumulative_fully_vaccinated / population  [0-1]
      new_confirmed_7d_avg  = rolling(7).mean() của new_confirmed        [ca/ngày]
      testing_rate          = new_tested / population                    [0-1]
      elderly_pct           = (age_70_79 + age_80+) / population        [0-1]
      icu_rate_per_1m       = new_intensive_care_patients / population * 1_000_000  [ca ICU/1M dân]
      search_trends_anosmia                                              [trực tiếp]
      incidence_rate        = new_confirmed / population * 100_000       [ca/100k — base target]

    Lưu ý quan trọng:
      - Silver fillna(0) → population CÓ THỂ = 0 → dùng replace(0, np.nan) trước khi chia
      - COVID data lịch sử (2020-2022), không phải realtime
      - sort_values([location_key, date]) TRƯỚC rolling để tránh data leakage
    """
    from deltalake import DeltaTable

    # COVID data lịch sử: 2020-01-01 → 2022-09-16
    # Không dùng today - 730 ngày (sẽ ra 2024, không có data!)
    COVID_DATA_START = datetime(2020, 1, 1).date()
    logger.info(f"[Healthcare/Silver] Đọc từ {COVID_DATA_START} | Columns: {HEALTHCARE_COLUMNS}")

    dt = DeltaTable(SILVER_PATH, storage_options=_storage_options())
    table = dt.to_pyarrow_table(
        filters=[("date", ">=", COVID_DATA_START)],
        columns=HEALTHCARE_COLUMNS,
    )

    df = table.to_pandas()
    logger.info(f"[Healthcare/Silver] Raw: {len(df):,} rows")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["location_key"].str.len() <= 2].copy()   # Cấp Quốc gia
    df = df[df["new_confirmed"] > 0].copy()              # Chỉ rows có dịch thực tế
    df = df.dropna(subset=["date", "location_key"]).reset_index(drop=True)

    n_ctry = df["location_key"].nunique()
    rng    = f"{df['date'].min().date()} → {df['date'].max().date()}" if not df.empty else "N/A"
    logger.info(f"[Healthcare/Silver] Sau filter: {len(df):,} rows | {n_ctry} quốc gia | {rng}")

    # ── Feature Engineering (theo Gold Schema groups) ──────────────────────────
    # QUAN TRỌNG: sort trước khi tính rolling để tránh data leakage
    df = df.sort_values(["location_key", "date"]).reset_index(drop=True)

    # Silver fillna(0) → population có thể = 0 → tránh ZeroDivision
    pop = df["population"].replace(0, np.nan)

    # Nhóm fact_vaccination: vaccination_rate ∈ [0, 1]
    df["vaccination_rate"] = (
        df["cumulative_persons_fully_vaccinated"] / pop
    ).clip(0, 1).fillna(0).astype(float)

    # Nhóm fact_covid_cases: 7-day rolling average của new_confirmed
    # (xu hướng hiện tại — predictor quan trọng nhất cho 14-day forecast)
    df["new_confirmed_7d_avg"] = (
        df.groupby("location_key")["new_confirmed"]
        .transform(lambda x: x.rolling(7, min_periods=1).mean())
    )

    # Nhóm fact_healthcare_system: testing_rate ∈ [0, 1]
    df["testing_rate"] = (
        df["new_tested"] / pop
    ).fillna(0).astype(float)

    # Nhóm dim_location: elderly_pct ∈ [0, 1]
    df["elderly_pct"] = (
        (df["population_age_70_79"].fillna(0) + df["population_age_80_and_older"].fillna(0))
        / pop
    ).clip(0, 1).fillna(0).astype(float)

    # Nhóm fact_healthcare_system: ICU rate per 1M dân
    # Normalize để so sánh công bằng giữa quốc gia (Mỹ=50k vs VN=800 → tỷ lệ tương đương)
    df["icu_rate_per_1m"] = (
        df["new_intensive_care_patients"].fillna(0) / pop * 1_000_000
    ).fillna(0).astype(float)

    # Nhóm fact_social_behavior: anosmia signal — leading indicator COVID
    df["search_trends_anosmia"] = df["search_trends_anosmia"].fillna(0).astype(float)

    # Target base: incidence_rate = ca / 100,000 dân
    # make_supervised_shift sẽ shift cột này đi 14 ngày để tạo target thực sự
    df["incidence_rate"] = (df["new_confirmed"] / pop * 100_000).fillna(0)

    # Log variance để debug feature quality
    derived_cols = [
        "vaccination_rate", "new_confirmed_7d_avg", "testing_rate",
        "elderly_pct", "icu_rate_per_1m", "search_trends_anosmia",
        "incidence_rate",
    ]
    for c in derived_cols:
        std  = df[c].std()
        mean = df[c].mean()
        nz   = (df[c] != 0).mean() * 100
        logger.info(f"[Healthcare]   {c}: mean={mean:.4f}, std={std:.4f}, non-zero={nz:.1f}%")

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# BÀI TOÁN 2: ĐÁNH GIÁ CHÍNH SÁCH — nguồn: PostgreSQL
#
# Target: growth_rate = (new_confirmed[t+14] - new_confirmed[t]) / new_confirmed[t]
#   growth_rate < 0 → dịch giảm → chính sách hiệu quả
#   growth_rate > 0 → dịch tăng → chính sách chưa đủ
#
# Features theo Gold schema:
#   fact_policy_impact → school_closing, workplace_closing,
#                         stay_at_home_requirements, stringency_index (MỚI)
#   fact_vaccination   → vaccination_rate (MỚI — context tiêm vaccine)
#   mobility_retail    → ĐÃ XÓA (outcome của policy, không phải input)
#
# Tại sao PostgreSQL thay vì Silver?
#   Silver Bronze được ingest TRƯỚC khi fix_policy_merge.py chạy
#   → school_closing = NULL trong Bronze → fillna(0) trong Silver → zero variance
#   PostgreSQL đã fix: 169,652 rows có school_closing + new_confirmed đúng
# ═══════════════════════════════════════════════════════════════════════════════

def load_policy_data() -> pd.DataFrame:
    """
    Đọc dữ liệu Policy từ PostgreSQL (đã fix OJM), tính vaccination_rate.

    Features:
      school_closing             (0-3) Oxford Index — giữ nguyên
      workplace_closing          (0-3) Oxford Index — giữ nguyên
      stay_at_home_requirements  (0-3) Oxford Index — MỚI
      stringency_index           (0-100) Oxford composite — MỚI
      vaccination_rate           (0-1) = cumulative_fully_vacc / population — MỚI
      [REMOVED] mobility_retail_and_recreation — đây là outcome của policy, không phải input

    Lưu ý:
      - stringency_index có thể NULL → fillna(0)
      - stay_at_home_requirements có thể NULL → fillna(0)
      - population có thể NULL → fillna(0) sau khi tính vaccination_rate
    """
    from sqlalchemy import text

    logger.info("[Policy/PostgreSQL] Đọc dữ liệu policy từ covid_optimized (đã fix OJM)")
    engine = _pg_engine()

    with engine.connect() as conn:
        max_date = conn.execute(
            text("SELECT MAX(date) FROM covid_optimized WHERE date IS NOT NULL")
        ).scalar()

    if not max_date:
        raise ValueError("Bảng covid_optimized rỗng! Kiểm tra PostgreSQL.")

    if isinstance(max_date, str):
        max_date = datetime.strptime(max_date[:10], "%Y-%m-%d").date()
    elif isinstance(max_date, datetime):
        max_date = max_date.date()

    query = text("""
        SELECT
            date,
            location_key,
            new_confirmed,
            school_closing,
            workplace_closing,
            stay_at_home_requirements,
            stringency_index,
            cumulative_persons_fully_vaccinated,
            population
        FROM covid_optimized
        WHERE date IS NOT NULL
          AND LENGTH(location_key) <= 2
          AND new_confirmed IS NOT NULL
          AND new_confirmed > 0
          AND (
              school_closing IS NOT NULL
              OR workplace_closing IS NOT NULL
          )
        ORDER BY location_key, date
    """)

    df = pd.read_sql(query, engine)

    if df.empty:
        raise ValueError(
            "PostgreSQL không có dữ liệu policy hợp lệ! "
            "Hãy chắc chắn fix_policy_merge.py đã được chạy."
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "location_key"]).reset_index(drop=True)

    # ── Feature Engineering ────────────────────────────────────────────────────
    # fillna cho các cột policy mới (có thể NULL trong PostgreSQL) và ép kiểu về float64
    df["stay_at_home_requirements"] = df["stay_at_home_requirements"].fillna(0).astype(float)
    df["stringency_index"]          = df["stringency_index"].fillna(0).astype(float)
    
    # Ép các cột policy có sẵn về float
    df["school_closing"] = df["school_closing"].fillna(0).astype(float)
    df["workplace_closing"] = df["workplace_closing"].fillna(0).astype(float)

    # vaccination_rate — tránh ZeroDivision
    pop = df["population"].replace(0, np.nan)
    df["vaccination_rate"] = (
        df["cumulative_persons_fully_vaccinated"] / pop
    ).clip(0, 1).fillna(0).astype(float)

    n_ctry = df["location_key"].nunique()
    rng    = f"{df['date'].min().date()} → {df['date'].max().date()}"
    logger.info(f"[Policy/PostgreSQL] {len(df):,} rows | {n_ctry} quốc gia | {rng}")

    # Log variance để debug — kiểm tra zero-variance trước khi train
    for col in ["school_closing", "workplace_closing", "stay_at_home_requirements",
                "stringency_index", "vaccination_rate"]:
        if col in df.columns:
            non_null = df[col].notna().sum()
            std = df[col].std() if df[col].notna().any() else 0
            nz  = (df[col] != 0).mean() * 100 if df[col].notna().any() else 0
            logger.info(f"  {col}: {non_null:,} non-null, std={std:.4f}, non-zero={nz:.1f}%")

    return df
