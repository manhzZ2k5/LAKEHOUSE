import os
import sys


from dagster import Definitions

# Ép Python nhận diện thư mục 'code' (nơi chứa file này) để import các file kế bên
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import luồng Ingestion (Postgres -> MinIO Bronze)
from ingestion_assets import (
    batch_ingestion_asset,
    ingestion_job,
    rolling_playback_sensor,
)

# Import luồng Transformation (Spark Bronze -> Silver)
from silver_assets import silver_covid_data
# Import luồng Gold (Silver -> Gold)
from gold_assets import (
    dim_date,
    dim_location,
    fact_covid_cases,
    fact_policy_impact,
    fact_vaccination,
    fact_social_behavior,
    fact_healthcare_system,
    covid_analytic_cube,
)

# Đăng ký vào Dagster
defs = Definitions(
    assets=[
        batch_ingestion_asset,
        silver_covid_data,
        dim_date,
        dim_location,
        fact_covid_cases,
        fact_policy_impact,
        fact_vaccination,
        fact_social_behavior,
        fact_healthcare_system,
        covid_analytic_cube,
    ],
    jobs=[ingestion_job],
    sensors=[rolling_playback_sensor],
)
