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

# Đăng ký vào Dagster
defs = Definitions(
    assets=[
        batch_ingestion_asset,
        silver_covid_data,
    ],
    jobs=[ingestion_job],
    sensors=[rolling_playback_sensor],
)
