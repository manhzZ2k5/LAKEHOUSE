import os
import re
from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, DoubleType, IntegerType, DateType
from pyspark.sql.functions import col, to_date, trim, lit
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Spark_Silver_Worker")

def process_bronze_to_silver(target_date, minio_endpoint, minio_access_key, minio_secret_key):
    logger.info(f"Khởi động Spark để xử lý dữ liệu ngày: {target_date}")

    # Đảm bảo không dùng lại SparkContext đã bị stop
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
    
    # 1. Khởi tạo Spark Session với cấu hình Delta và MinIO
    spark_master = os.environ.get("SPARK_MASTER_URL", "local[*]")
    driver_host = os.environ.get("SPARK_DRIVER_HOST")
    driver_bind = os.environ.get("SPARK_DRIVER_BIND_ADDRESS", "0.0.0.0")

    builder = SparkSession.builder.appName("Covid_Bronze_To_Silver") \
        .master(spark_master) \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint) \
        .config("spark.hadoop.fs.s3a.access.key", minio_access_key) \
        .config("spark.hadoop.fs.s3a.secret.key", minio_secret_key) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

    if driver_host:
        builder = builder.config("spark.driver.host", driver_host)
    if driver_bind:
        builder = builder.config("spark.driver.bindAddress", driver_bind)
    extra_jars = os.environ.get("SPARK_EXTRA_JARS")
    if extra_jars:
        builder = builder.config("spark.jars", extra_jars)

    # Tải thư viện giao tiếp với S3 (MinIO) và Delta Lake
    spark = builder.getOrCreate()
    
    spark.sparkContext.setLogLevel("ERROR")

    # Preflight Checks
    extensions = spark.conf.get("spark.sql.extensions", "")
    if "io.delta.sql.DeltaSparkSessionExtension" not in extensions:
        raise RuntimeError(f"Delta Spark extension chưa được load. spark.sql.extensions={extensions}")
        
    catalog = spark.conf.get("spark.sql.catalog.spark_catalog", "")
    if "org.apache.spark.sql.delta.catalog.DeltaCatalog" not in catalog:
        raise RuntimeError(f"Delta catalog chưa được load. spark.sql.catalog.spark_catalog={catalog}")

    try:
        hconf = spark._jsc.hadoopConfiguration()
        silver_root = spark._jvm.org.apache.hadoop.fs.Path("s3a://silver-lake/")
        fs = silver_root.getFileSystem(hconf)
        if not fs.exists(silver_root):
            raise RuntimeError("Bucket silver-lake chưa tồn tại trong MinIO.")
    except Exception as e:
        raise RuntimeError(
            f"Không thể kiểm tra/truy cập bucket silver-lake. Lỗi: {repr(e)}"
        ) from e

    # BẮT ĐẦU KHỐI TRY...EXCEPT...FINALLY CHÍNH ĐỂ XỬ LÝ DỮ LIỆU
    try:
        # 2. Đọc dữ liệu từ tầng Bronze
        bronze_path = f"s3a://bronze-lake/date={target_date}/batch_data.parquet"
        logger.info(f"Đọc dữ liệu Bronze từ: {bronze_path}")
        df = spark.read.parquet(bronze_path)
        logger.info(f"Schema Bronze gốc: {df.dtypes}")
        
        # 3. LÀM SẠCH DỮ LIỆU CHUYÊN SÂU
        if "date" not in df.columns:
            raise ValueError(f"Thiếu cột 'date' trong dữ liệu Bronze. Columns hiện có: {df.columns}")

        clean_df = df

        # 3.1. Chuẩn hóa tên cột thành snake_case
        def to_snake_case(name):
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name).lower()
            clean_name = re.sub(r'_+', '_', clean_name).strip('_')
            return clean_name

        for col_name in clean_df.columns:
            new_col_name = to_snake_case(col_name)
            if col_name != new_col_name:
                clean_df = clean_df.withColumnRenamed(col_name, new_col_name)

        date_col = to_snake_case("date")

        # 3.1.1 Kiểm tra trùng tên cột sau khi chuẩn hóa
        seen = set()
        dupes = set()
        for c in clean_df.columns:
            if c in seen:
                dupes.add(c)
            else:
                seen.add(c)
        if dupes:
            raise ValueError(f"Trùng tên cột sau khi snake_case: {sorted(list(dupes))}")

        # 3.2. Ép kiểu thời gian
        clean_df = clean_df.withColumn(date_col, to_date(col(date_col)))

        # 3.3. Chuẩn hóa schema cố định cho Silver
        expected_schema = {
            "date": DateType(),
            "location_key": StringType(),
            "country_name": StringType(),
            "subregion1_name": StringType(),
            "subregion2_name": StringType(),
            "aggregation_level": IntegerType(),
            "new_confirmed": DoubleType(),
            "cumulative_confirmed": DoubleType(),
            "new_deceased": DoubleType(),
            "cumulative_deceased": DoubleType(),
            "new_tested": DoubleType(),
            "cumulative_tested": DoubleType(),
            "new_recovered": DoubleType(),
            "cumulative_recovered": DoubleType(),
            "new_persons_vaccinated": DoubleType(),
            "cumulative_persons_vaccinated": DoubleType(),
            "new_persons_fully_vaccinated": DoubleType(),
            "cumulative_persons_fully_vaccinated": DoubleType(),
            "new_vaccine_doses_administered": DoubleType(),
            "cumulative_vaccine_doses_administered": DoubleType(),
            "hospital_beds_per_1000": DoubleType(),
            "new_hospitalized_patients": DoubleType(),
            "cumulative_hospitalized_patients": DoubleType(),
            "new_intensive_care_patients": DoubleType(),
            "cumulative_intensive_care_patients": DoubleType(),
            "population": DoubleType(),
            "population_density": DoubleType(),
            "population_male": DoubleType(),
            "population_female": DoubleType(),
            "population_age_60_69": DoubleType(),
            "population_age_70_79": DoubleType(),
            "population_age_80_and_older": DoubleType(),
            "gdp_per_capita_usd": DoubleType(),
            "human_development_index": DoubleType(),
            "life_expectancy": DoubleType(),
            "smoking_prevalence": DoubleType(),
            "diabetes_prevalence": DoubleType(),
            "stringency_index": DoubleType(),
            "school_closing": DoubleType(),
            "workplace_closing": DoubleType(),
            "stay_at_home_requirements": DoubleType(),
            "vaccination_policy": DoubleType(),
            "mobility_retail_and_recreation": DoubleType(),
            "mobility_grocery_and_pharmacy": DoubleType(),
            "mobility_parks": DoubleType(),
            "mobility_transit_stations": DoubleType(),
            "mobility_workplaces": DoubleType(),
            "mobility_residential": DoubleType(),
            "average_temperature_celsius": DoubleType(),
            "search_trends_fever": DoubleType(),
            "search_trends_cough": DoubleType(),
            "search_trends_shortness_of_breath": DoubleType(),
            "search_trends_anosmia": DoubleType(),
            "search_trends_pneumonia": DoubleType(),
        }

        # Đảm bảo đủ cột và đúng kiểu
        for col_name, dtype in expected_schema.items():
            if col_name in clean_df.columns:
                clean_df = clean_df.withColumn(col_name, col(col_name).cast(dtype))
            else:
                clean_df = clean_df.withColumn(col_name, lit(None).cast(dtype))

        # Chỉ giữ đúng schema chuẩn (loại bỏ cột thừa)
        clean_df = clean_df.select(list(expected_schema.keys()))

        # 3.4. Cắt khoảng trắng (Trim) cho các cột string
        string_cols = [f.name for f in clean_df.schema.fields if isinstance(f.dataType, StringType)]
        for c in string_cols:
            clean_df = clean_df.withColumn(c, trim(col(c)))

        # 3.5. Xử lý Null và Xóa trùng lặp
        numeric_cols = [
            c for c, t in expected_schema.items()
            if isinstance(t, (DoubleType, IntegerType))
        ]
        clean_df = clean_df.fillna(0, subset=numeric_cols).dropDuplicates()
            
        # 4. GHI XUỐNG TẦNG SILVER BẰNG DELTA LAKE
        silver_path = "s3a://silver-lake/covid_cleaned/"
        logger.info(f"Ghi Delta vào Silver: {silver_path}")
        logger.info(f"Schema Silver (moi) se ghi: {clean_df.dtypes}")

        # Log schema hiện tại của Silver (nếu đã tồn tại) để dễ so sánh
        try:
            existing_df = spark.read.format("delta").load(silver_path)
            logger.info(f"Schema Silver hiện tại: {existing_df.dtypes}")
        except Exception:
            logger.info("Silver chưa tồn tại hoặc chưa là Delta table. Sẽ tạo mới.")
        
        clean_df.write \
            .format("delta") \
            .mode("append") \
            .option("mergeSchema", "true") \
            .partitionBy(date_col) \
            .save(silver_path)
            
        logger.info(f"Đã xử lý và lưu Delta Lake thành công {clean_df.count()} dòng vào Silver Lake!")
        return f"Success: Spark processed {target_date}"
    except Exception as e:
        logger.error(f"Lỗi trong quá trình Spark xử lý (repr): {repr(e)}")
        details = []
        for attr in ("desc", "message", "msg", "errorClass", "sqlState"):
            try:
                if hasattr(e, attr):
                    details.append(f"{attr}={getattr(e, attr)}")
            except Exception:
                pass
        try:
            j_exc = getattr(e, "java_exception", None)
            if j_exc is not None:
                try:
                    details.append(f"java_class={j_exc.getClass().getName()}")
                except Exception:
                    pass
                try:
                    details.append(f"java_message={j_exc.getMessage()}")
                except Exception:
                    pass
        except Exception:
            pass
        if details:
            logger.error("Chi tiet loi: " + " | ".join(details))
        raise
    finally:
        # ĐẢM BẢO SPARK LUÔN ĐƯỢC TẮT SAU KHI CHẠY (DÙ THÀNH CÔNG HAY THẤT BẠI)
        spark.stop()
        SparkContext._active_spark_context = None
        SparkSession._instantiatedSession = None
        SparkSession._activeSession = None
        SparkContext._gateway = None
        SparkContext._jvm = None
