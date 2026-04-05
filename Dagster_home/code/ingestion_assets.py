from datetime import datetime, timedelta

from dagster import (
    asset,
    define_asset_job,
    sensor,
    RunRequest,
    SkipReason,
    SensorEvaluationContext,
    DefaultSensorStatus,
)

from etl_pipeline.ingestion_logic import process_batch_data
from shared import covid_partitions

# --- 1. CẤU HÌNH ---
DB_CON_STR = "postgresql://covid_user:123456@host.docker.internal:5432/COVID-19"

MINIO_CONFIG = {
    "key": "minio_admin",
    "secret": "minio_secret_secure_password_123",
    "client_kwargs": {"endpoint_url": "http://minio:9000"},
}


# --- 2. ASSET (Ingestion) ---
@asset(
    partitions_def=covid_partitions,
    group_name="ingestion",
)
def batch_ingestion_asset(context):
    start_str = context.partition_time_window.start.strftime("%Y-%m-%d")
    end_str = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(f"Dagster đang gọi logic ETL cho ngày: {start_str}")

    result_message = process_batch_data(
        start_date=start_str,
        end_date=end_str,
        db_con_str=DB_CON_STR,
        minio_config=MINIO_CONFIG,
    )
    return result_message


# --- 3. JOB ---
# Chạy cả ingestion và silver trong cùng một job
ingestion_job = define_asset_job(
    name="batch_ingestion_asset_job",
    selection=["batch_ingestion_asset", "silver_covid_data"],
)


# --- 4. SENSOR "CUỐN CHIẾU" ---
@sensor(
    job_name="batch_ingestion_asset_job",
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.RUNNING,
)
def rolling_playback_sensor(context: SensorEvaluationContext):
    TARGET_HOUR = 12

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    cursor = context.cursor

    if not cursor:
        next_data_date_str = "2020-01-01"
        last_run_real_date = "1970-01-01"
    else:
        try:
            last_run_real_date, next_data_date_str = cursor.split("|")
        except ValueError:
            last_run_real_date = "1970-01-01"
            next_data_date_str = "2020-01-01"

    if now.hour < TARGET_HOUR:
        return SkipReason(f"Chưa đến {TARGET_HOUR}h trưa. Hiện tại là {now.hour}h.")

    if last_run_real_date == today_str:
        return SkipReason(
            f"Hôm nay ({today_str}) đã chạy data ngày {next_data_date_str} rồi. Hẹn mai gặp lại!"
        )

    current_data_date = datetime.strptime(next_data_date_str, "%Y-%m-%d")
    next_cycle_data_date = current_data_date + timedelta(days=1)
    next_cycle_data_date_str = next_cycle_data_date.strftime("%Y-%m-%d")

    new_cursor = f"{today_str}|{next_cycle_data_date_str}"
    context.update_cursor(new_cursor)

    run_key = f"daily_rolling_{today_str}_{next_data_date_str}"
    context.log.info(f"Triggering run for data date: {next_data_date_str}")

    yield RunRequest(
        run_key=run_key,
        partition_key=next_data_date_str,
    )
