import os
import logging
from datetime import datetime

from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    to_date,
    date_format,
    year,
    month,
    quarter,
    lit,
    md5,
    coalesce,
)
from pyspark.sql.types import IntegerType, DoubleType, StringType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Spark_Gold_Worker")

DEFAULT_SPARK_PACKAGES = ",".join(
    [
        "io.delta:delta-spark_2.12:3.2.0",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
    ]
)


def _configure_dependencies(builder: SparkSession.Builder) -> SparkSession.Builder:
    packages = os.environ.get("SPARK_JARS_PACKAGES", DEFAULT_SPARK_PACKAGES).strip()
    if packages:
        builder = builder.config("spark.jars.packages", packages)
        builder = builder.config(
            "spark.jars.ivy", os.environ.get("SPARK_IVY_DIR", "/tmp/.ivy2")
        )
        logger.info("Spark deps via spark.jars.packages: %s", packages)
    return builder


def _reset_spark_context():
    try:
        active_sc = SparkContext._active_spark_context
        if active_sc is not None:
            try:
                stopped = active_sc._jsc is None or active_sc._jsc.sc().isStopped()
            except Exception:
                stopped = True
            if stopped:
                SparkContext._active_spark_context = None
                SparkSession._instantiatedSession = None
                SparkSession._activeSession = None
                SparkContext._gateway = None
                SparkContext._jvm = None
            else:
                active_sc.stop()
                SparkContext._active_spark_context = None
                SparkSession._instantiatedSession = None
                SparkSession._activeSession = None
                SparkContext._gateway = None
                SparkContext._jvm = None
    except Exception:
        SparkContext._active_spark_context = None
        SparkSession._instantiatedSession = None
        SparkSession._activeSession = None
        SparkContext._gateway = None
        SparkContext._jvm = None


def _build_spark(minio_endpoint, minio_access_key, minio_secret_key):
    spark_master = os.environ.get("SPARK_MASTER_URL", "local[*]")
    driver_host = os.environ.get("SPARK_DRIVER_HOST")
    driver_bind = os.environ.get("SPARK_DRIVER_BIND_ADDRESS", "0.0.0.0")

    builder = (
        SparkSession.builder.appName("Covid_Silver_To_Gold")
        .master(spark_master)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", minio_access_key)
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    )

    builder = _configure_dependencies(builder)

    if driver_host:
        builder = builder.config("spark.driver.host", driver_host)
    if driver_bind:
        builder = builder.config("spark.driver.bindAddress", driver_bind)

    spark = builder.getOrCreate()

    log_level = os.environ.get("SPARK_LOG_LEVEL", "ERROR").upper()
    if log_level not in {"ALL", "DEBUG", "ERROR", "FATAL", "INFO", "OFF", "TRACE", "WARN"}:
        log_level = "ERROR"
    # Allow switching Spark log verbosity for debugging without code changes.
    spark.sparkContext.setLogLevel(log_level)
    logging.getLogger("Spark_Gold_Worker").info("Spark log level: %s", log_level)

    extensions = spark.conf.get("spark.sql.extensions", "")
    if "io.delta.sql.DeltaSparkSessionExtension" not in extensions:
        raise RuntimeError(f"Delta Spark extension chua duoc load. spark.sql.extensions={extensions}")

    catalog = spark.conf.get("spark.sql.catalog.spark_catalog", "")
    if "org.apache.spark.sql.delta.catalog.DeltaCatalog" not in catalog:
        raise RuntimeError(f"Delta catalog chua duoc load. spark.sql.catalog.spark_catalog={catalog}")

    return spark


def _ensure_bucket_exists(spark, bucket_name):
    try:
        hconf = spark._jsc.hadoopConfiguration()
        bucket_path = spark._jvm.org.apache.hadoop.fs.Path(f"s3a://{bucket_name}/")
        fs = bucket_path.getFileSystem(hconf)
        if not fs.exists(bucket_path):
            raise RuntimeError(f"Bucket {bucket_name} chua ton tai trong MinIO.")
    except Exception as e:
        raise RuntimeError(
            f"Khong the kiem tra/truy cap bucket {bucket_name}. Loi: {repr(e)}"
        ) from e


def _write_monthly_delta(df, path, month_key):
    if df.rdd.isEmpty():
        logger.warning(f"Khong co du lieu de ghi vao {path} cho thang {month_key}.")
        return
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"month_key = '{month_key}'")
        .partitionBy("month_key")
        .save(path)
    )


def _prepare_month_df(spark, month_start, month_end):
    silver_path = "s3a://silver-lake/covid_cleaned/"
    month_key = datetime.strptime(month_start, "%Y-%m-%d").strftime("%Y-%m")

    logger.info(f"Doc Silver theo thang {month_key} tu: {silver_path}")
    df = (
        spark.read.format("delta")
        .load(silver_path)
        .withColumn("date", to_date(col("date")))
        .where((col("date") >= lit(month_start)) & (col("date") < lit(month_end)))
    )

    if df.rdd.isEmpty():
        logger.warning(f"Khong co du lieu Silver cho thang {month_key}")
        return None, month_key

    required_cols = [
        "date",
        "location_key",
        "country_name",
        "population",
        "gdp_per_capita_usd",
        "new_confirmed",
        "new_deceased",
        "stringency_index",
        "school_closing",
        "workplace_closing",
        "new_persons_vaccinated",
        "cumulative_persons_fully_vaccinated",
        "mobility_retail_and_recreation",
        "mobility_residential",
        "search_trends_fever",
        "search_trends_cough",
        "search_trends_shortness_of_breath",
        "search_trends_anosmia",
        "search_trends_pneumonia",
        "new_intensive_care_patients",
        "new_hospitalized_patients",
        "new_tested",
    ]
    for c in required_cols:
        if c not in df.columns:
            df = df.withColumn(c, lit(None))

    df = df.withColumn("date_key", date_format(col("date"), "yyyyMMdd").cast(IntegerType()))
    df = df.withColumn("month_key", date_format(col("date"), "yyyy-MM"))
    # location_key trong Gold duoc chuan hoa thanh chuoi MD5 de on dinh va ngan gon
    df = df.withColumn(
        "location_key",
        md5(col("location_key").cast(StringType())),
    )
    return df, month_key


def _build_dim_date(df):
    return (
        df.select(
            col("date_key").cast(IntegerType()).alias("date_key"),
            col("date").alias("full_date"),
            year(col("date")).cast(IntegerType()).alias("year"),
            month(col("date")).cast(IntegerType()).alias("month"),
            quarter(col("date")).cast(IntegerType()).alias("quarter"),
            col("month_key"),
        )
        .dropDuplicates(["date_key"])
    )


def _build_dim_location(df):
    return (
        df.select(
            col("location_key").cast(StringType()).alias("location_key"),
            col("country_name").cast(StringType()).alias("country_name"),
            col("population").cast(DoubleType()).alias("population"),
            col("gdp_per_capita_usd").cast(DoubleType()).alias("gdp_per_capita_usd"),
            col("month_key"),
        )
        .dropDuplicates(["location_key"])
    )


def _build_fact_covid_cases(df):
    return df.select(
        col("date_key").cast(IntegerType()).alias("date_key"),
        col("location_key").cast(StringType()).alias("location_key"),
        col("new_confirmed").cast(IntegerType()).alias("new_confirmed"),
        col("new_deceased").cast(IntegerType()).alias("new_deaths"),
        col("month_key"),
    )


def _build_fact_policy_impact(df):
    return df.select(
        col("date_key").cast(IntegerType()).alias("date_key"),
        col("location_key").cast(StringType()).alias("location_key"),
        col("stringency_index").cast(DoubleType()).alias("stringency_index"),
        col("school_closing").cast(IntegerType()).alias("school_closing"),
        col("workplace_closing").cast(IntegerType()).alias("workplace_closing"),
        col("month_key"),
    )


def _build_fact_vaccination(df):
    return df.select(
        col("date_key").cast(IntegerType()).alias("date_key"),
        col("location_key").cast(StringType()).alias("location_key"),
        col("new_persons_vaccinated").cast(IntegerType()).alias("new_persons_vaccinated"),
        col("cumulative_persons_fully_vaccinated").cast(IntegerType()).alias(
            "cumulative_persons_fully_vaccinated"
        ),
        col("month_key"),
    )


def _build_fact_social_behavior(df):
    search_trends_symptoms = (
        coalesce(col("search_trends_fever"), lit(0))
        + coalesce(col("search_trends_cough"), lit(0))
        + coalesce(col("search_trends_shortness_of_breath"), lit(0))
        + coalesce(col("search_trends_anosmia"), lit(0))
        + coalesce(col("search_trends_pneumonia"), lit(0))
    ) / lit(5)

    return df.select(
        col("date_key").cast(IntegerType()).alias("date_key"),
        col("location_key").cast(StringType()).alias("location_key"),
        col("mobility_retail_and_recreation")
        .cast(DoubleType())
        .alias("mobility_retail_and_recreation"),
        col("mobility_residential").cast(DoubleType()).alias("mobility_residential"),
        search_trends_symptoms.cast(DoubleType()).alias("search_trends_symptoms"),
        col("month_key"),
    )


def _build_fact_healthcare_system(df):
    return df.select(
        col("date_key").cast(IntegerType()).alias("date_key"),
        col("location_key").cast(StringType()).alias("location_key"),
        col("new_intensive_care_patients").cast(IntegerType()).alias("icu_patients"),
        col("new_hospitalized_patients").cast(IntegerType()).alias("hosp_patients"),
        col("new_tested").cast(IntegerType()).alias("new_tests"),
        col("month_key"),
    )


def _process_gold_table(table_name, build_fn, month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    logger.info(f"Khoi dong Spark de xu ly Gold table {table_name} tu {month_start} den {month_end}")

    _reset_spark_context()
    spark = _build_spark(minio_endpoint, minio_access_key, minio_secret_key)

    try:
        _ensure_bucket_exists(spark, "silver-lake")
        _ensure_bucket_exists(spark, "gold-lake")

        df, month_key = _prepare_month_df(spark, month_start, month_end)
        if df is None:
            return f"Empty: no data for {month_key}"

        gold_root = "s3a://gold-lake/"
        table_df = build_fn(df)
        _write_monthly_delta(table_df, f"{gold_root}{table_name}/", month_key)

        logger.info(f"{table_name} da duoc ghi thanh cong cho thang {month_key}")
        return f"Success: {table_name} updated for {month_key}"
    finally:
        spark.stop()
        SparkContext._active_spark_context = None
        SparkSession._instantiatedSession = None
        SparkSession._activeSession = None
        SparkContext._gateway = None
        SparkContext._jvm = None


def process_dim_date(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="dim_date",
        build_fn=_build_dim_date,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_dim_location(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="dim_location",
        build_fn=_build_dim_location,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_fact_covid_cases(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="fact_covid_cases",
        build_fn=_build_fact_covid_cases,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_fact_policy_impact(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="fact_policy_impact",
        build_fn=_build_fact_policy_impact,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_fact_vaccination(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="fact_vaccination",
        build_fn=_build_fact_vaccination,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_fact_social_behavior(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="fact_social_behavior",
        build_fn=_build_fact_social_behavior,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_fact_healthcare_system(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    return _process_gold_table(
        table_name="fact_healthcare_system",
        build_fn=_build_fact_healthcare_system,
        month_start=month_start,
        month_end=month_end,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def process_silver_to_gold(month_start, month_end, minio_endpoint, minio_access_key, minio_secret_key):
    # Ham tong hop (giu lai de tien dung / backward-compatible)
    logger.info(f"Khoi dong Spark de xu ly Gold tong hop tu {month_start} den {month_end}")

    _reset_spark_context()
    spark = _build_spark(minio_endpoint, minio_access_key, minio_secret_key)

    try:
        _ensure_bucket_exists(spark, "silver-lake")
        _ensure_bucket_exists(spark, "gold-lake")

        df, month_key = _prepare_month_df(spark, month_start, month_end)
        if df is None:
            return f"Empty: no data for {month_key}"

        gold_root = "s3a://gold-lake/"
        _write_monthly_delta(_build_dim_date(df), f"{gold_root}dim_date/", month_key)
        _write_monthly_delta(_build_dim_location(df), f"{gold_root}dim_location/", month_key)
        _write_monthly_delta(_build_fact_covid_cases(df), f"{gold_root}fact_covid_cases/", month_key)
        _write_monthly_delta(_build_fact_policy_impact(df), f"{gold_root}fact_policy_impact/", month_key)
        _write_monthly_delta(_build_fact_vaccination(df), f"{gold_root}fact_vaccination/", month_key)
        _write_monthly_delta(_build_fact_social_behavior(df), f"{gold_root}fact_social_behavior/", month_key)
        _write_monthly_delta(_build_fact_healthcare_system(df), f"{gold_root}fact_healthcare_system/", month_key)

        logger.info(f"Gold da duoc ghi thanh cong cho thang {month_key}")
        return f"Success: Gold updated for {month_key}"
    finally:
        spark.stop()
        SparkContext._active_spark_context = None
        SparkSession._instantiatedSession = None
        SparkSession._activeSession = None
        SparkContext._gateway = None
        SparkContext._jvm = None
