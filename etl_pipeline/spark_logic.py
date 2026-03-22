import os

from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_date
from delta import configure_spark_with_delta_pip
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Spark_Silver_Worker")

def process_bronze_to_silver(target_date, minio_endpoint, minio_access_key, minio_secret_key):
    logger.info(f"Khởi động Spark để xử lý dữ liệu ngày: {target_date}")

    # Đảm bảo không dùng lại SparkContext đã bị stop
    # (Dagster chạy nhiều op trong cùng process có thể giữ context cũ)
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
                # Nếu còn sống thì stop để tạo mới sạch sẽ
                active_sc.stop()
                SparkContext._active_spark_context = None
                SparkSession._instantiatedSession = None
                SparkSession._activeSession = None
                SparkContext._gateway = None
                SparkContext._jvm = None
    except Exception:
        # Nếu có vấn đề khi đọc trạng thái, cứ reset an toàn
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

    # Tải thư viện giao tiếp với S3 (MinIO) và Delta Lake
    spark = configure_spark_with_delta_pip(
        builder, 
        extra_packages=["org.apache.hadoop:hadoop-aws:3.3.4", "com.amazonaws:aws-java-sdk-bundle:1.12.262"]
    ).getOrCreate()
    
    spark.sparkContext.setLogLevel("ERROR") # Giảm bớt log rác

    try:
        # 2. Đọc dữ liệu từ tầng Bronze theo đúng ngày (Partition)
        bronze_path = f"s3a://bronze-lake/date={target_date}/batch_data.parquet"
        df = spark.read.parquet(bronze_path)
        
        # 3. Làm sạch dữ liệu (Transformation)
        # Giả sử cấu trúc có các cột này, bạn có thể tự đổi tên cho khớp với data thực tế
        clean_df = df \
            .withColumn("date", to_date(col("date"))) \
            .fillna(0) # Điền số 0 cho các giá trị null ở cột số
            
        # 4. Ghi xuống tầng Silver bằng chuẩn Delta Lake
        silver_path = "s3a://silver-lake/covid_cleaned/"
        
        clean_df.write \
            .format("delta") \
            .mode("append") \
            .partitionBy("date") \
            .save(silver_path)
            
        logger.info(f"Đã xử lý và lưu Delta Lake thành công {clean_df.count()} dòng vào Silver Lake!")
        return f"Success: Spark processed {target_date}"
        
    except Exception as e:
        logger.error(f"Lỗi trong quá trình Spark xử lý: {e}")
        raise e
    finally:
        spark.stop()  # Giải phóng Spark sau mỗi run
        # Xóa session tĩnh để lần sau tạo mới clean
        SparkContext._active_spark_context = None
        SparkSession._instantiatedSession = None
        SparkSession._activeSession = None
        SparkContext._gateway = None
        SparkContext._jvm = None
