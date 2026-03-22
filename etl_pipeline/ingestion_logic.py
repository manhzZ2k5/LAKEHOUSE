import pandas as pd
from sqlalchemy import create_engine
import logging

# Cấu hình logging để in ra màn hình console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ETL_Worker")


def process_batch_data(start_date, end_date, db_con_str, minio_config):
    query = f"""
    SELECT * FROM covid_optimized
    where date >='{start_date}' AND date <'{end_date}'
    """
    logger.info(f"Đang chạy dữ liệu từ ngày {start_date} đến {end_date}")


    try:
         engine= create_engine(db_con_str)
         with engine.connect() as conn:
            df= pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Lỗi kết nối database: {e}")
        raise e
    

    # kiểm tra dữ liệu
    if df.empty:
        logger.warning(f"không tìm thấy dữ liệu trong ngày {start_date} đến {end_date}")
        return "Empty_batch"


    # Ghi đè toàn bộ dữ liệu vào file minio
    file_path = f"s3://bronze-lake/date={start_date}/batch_data.parquet"
    
    logger.info(f"Đang ghi {len(df)} dòng vào MinIO: {file_path}")
    
    try:
        df.to_parquet(
            file_path,
            storage_options=minio_config,
            index=False
        )
    except Exception as e:
        logger.error(f"Lỗi ghi file MinIO: {e}")
        raise e

    return f"Success: {len(df)} rows -> {file_path}"


