from dagster import (
    AssetDep,
    AutoMaterializePolicy,
    TimeWindowPartitionMapping,
    asset,
)

from etl_pipeline.gold_logic import (
    process_dim_date,
    process_dim_location,
    process_fact_covid_cases,
    process_fact_policy_impact,
    process_fact_vaccination,
    process_fact_social_behavior,
    process_fact_healthcare_system,
)
from shared import covid_monthly_partitions


# Silver la daily, Gold la monthly.
# TimeWindowPartitionMapping giup Dagster hieu: moi daily partition thuoc ve thang nao,
# thi thang do se duoc auto-materialize khi daily partition thay doi.
SILVER_TO_GOLD_MAPPING = TimeWindowPartitionMapping()
SILVER_DEP = AssetDep("silver_covid_data", partition_mapping=SILVER_TO_GOLD_MAPPING)

# Silver la daily, Gold la monthly.
# TimeWindowPartitionMapping giup Dagster hieu: moi daily partition thuoc ve thang nao,
# thi thang do se duoc auto-materialize khi daily partition thay doi.
SILVER_TO_GOLD_MAPPING = TimeWindowPartitionMapping()
SILVER_DEP = AssetDep("silver_covid_data", partition_mapping=SILVER_TO_GOLD_MAPPING)


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def dim_date(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly dim_date cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_dim_date(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def dim_location(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly dim_location cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_dim_location(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def fact_policy_impact(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly fact_policy_impact cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_fact_policy_impact(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def fact_covid_cases(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly fact_covid_cases cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_fact_covid_cases(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def fact_vaccination(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly fact_vaccination cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_fact_vaccination(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def fact_social_behavior(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly fact_social_behavior cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_fact_social_behavior(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    deps=[SILVER_DEP],
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
)
def fact_healthcare_system(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")

    context.log.info(
        f"Bat dau xu ly fact_healthcare_system cho thang tu {month_start} den {month_end}"
    )

    minio_endpoint = "http://minio:9000"
    minio_access_key = "minio_admin"
    minio_secret_key = "minio_secret_secure_password_123"

    return process_fact_healthcare_system(
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


@asset(
    partitions_def=covid_monthly_partitions,
    group_name="gold",
    auto_materialize_policy=AutoMaterializePolicy.eager(),
    deps=[
        dim_date,
        dim_location,
        fact_covid_cases,
        fact_policy_impact,
        fact_vaccination,
        fact_social_behavior,
        fact_healthcare_system,
    ],
)
def covid_analytic_cube(context):
    month_start = context.partition_time_window.start.strftime("%Y-%m-%d")
    month_end = context.partition_time_window.end.strftime("%Y-%m-%d")
    context.log.info(
        f"Gold cube hoan tat cho thang tu {month_start} den {month_end}"
    )
    return f"Gold cube ready for {month_start} to {month_end}"
