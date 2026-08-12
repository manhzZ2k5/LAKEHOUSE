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

# Import luồng ML (Silver → MLflow Registry)
# Dagster lineage: batch_ingestion_asset → silver_covid_data → auto_train_*
# ML đọc từ Silver Lake (MinIO/Delta Lake) qua deltalake library, không cần Spark
from ml_assets import auto_train_healthcare_forecast, auto_train_policy_effectiveness
from dagster import ScheduleDefinition, define_asset_job

# Job quản lý tác vụ ML
ml_assets_job = define_asset_job(
    name="ml_training_job",
    selection=["auto_train_healthcare_forecast", "auto_train_policy_effectiveness"]
)

# Lịch trình tự động chạy 12h trưa mỗi ngày
ml_daily_schedule = ScheduleDefinition(
    job=ml_assets_job,
    cron_schedule="0 12 * * *", 
    execution_timezone="Asia/Ho_Chi_Minh" 
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
        auto_train_healthcare_forecast,
        auto_train_policy_effectiveness
    ],
    jobs=[ingestion_job, ml_assets_job],
    sensors=[rolling_playback_sensor],
    schedules=[ml_daily_schedule],
)
