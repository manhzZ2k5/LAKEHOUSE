from dagster import asset
from etl_pipeline.spark_logic import process_bronze_to_silver

from shared import covid_partitions


@asset(
    partitions_def=covid_partitions,
    deps=["batch_ingestion_asset"],
    group_name="transformation",
)
def silver_covid_data(context):
    target_date = context.partition_time_window.start.strftime("%Y-%m-%d")
    context.log.info(f"Bắt đầu quy trình Spark Bronze -> Silver cho ngày {target_date}")

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    result = process_bronze_to_silver(
        target_date=target_date,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )

    return result
