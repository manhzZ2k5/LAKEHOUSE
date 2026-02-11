import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from dagster import (
    asset, Definitions, 
    DailyPartitionsDefinition, 
    define_asset_job,
    sensor, RunRequest, SkipReason, SensorEvaluationContext, 
    DefaultSensorStatus
)
from datetime import datetime, timedelta
from sml_logic import process_batch_data

# --- 1. CẤU HÌNH (Giữ nguyên) ---
DB_CON_STR = "postgresql://covid_user:123456@host.docker.internal:5432/COVID-19"

MINIO_CONFIG = {
    "key": "minio_admin", 
    "secret": "minio_secret_secure_password_123", 
    "client_kwargs": {
        "endpoint_url": "http://minio:9000"
    }
}

# --- 2. PARTITION (Bỏ end_date để chạy vô tận) ---
covid_partitions = DailyPartitionsDefinition(
    start_date="2020-01-01", 
    # end_date="2022-09-16", # <-- Bỏ dòng này đi để không bị giới hạn
    timezone="Asia/Ho_Chi_Minh"
)

# --- 3. ASSET (Giữ nguyên) ---
@asset(
    partitions_def=covid_partitions,
    group_name="ingestion"
)
def batch_ingestion_asset(context):
    start_str = context.partition_time_window.start.strftime("%Y-%m-%d")
    end_str = context.partition_time_window.end.strftime("%Y-%m-%d")
    
    context.log.info(f" Đang chạy dữ liệu cho ngày: {start_str}")

    result_message = process_batch_data(
        start_date=start_str,
        end_date=end_str,
        db_con_str=DB_CON_STR,
        minio_config=MINIO_CONFIG
    )
    return result_message

# --- 4. JOB (Giữ nguyên) ---
ingestion_job = define_asset_job(
    name="batch_ingestion_asset_job",
    selection=["batch_ingestion_asset"]
)

# --- 5. SENSOR "CUỐN CHIẾU" (THAY THẾ CHO SCHEDULE) ---
@sensor(
    job_name="batch_ingestion_asset_job",
    minimum_interval_seconds=60, # Kiểm tra mỗi 1 phút
    default_status=DefaultSensorStatus.RUNNING
)
def rolling_playback_sensor(context: SensorEvaluationContext):
    # Cấu hình giờ chạy mong muốn (Ví dụ: 12 giờ trưa)
    TARGET_HOUR = 12
    
    # Lấy thời gian thực tế hiện tại
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d") # Ví dụ: "2026-02-11"

    # Lấy cursor (trạng thái lưu từ lần chạy trước)
    # Định dạng cursor sẽ là: "NGÀY_THỰC_TẾ_ĐÃ_CHẠY|NGÀY_DATA_TIẾP_THEO"
    # Ví dụ: "2026-02-11|2020-01-02" (Nghĩa là hôm nay 11/2 đã chạy xong data ngày 2/1/2020 rồi)
    cursor = context.cursor

    # 1. Khởi tạo nếu chưa chạy bao giờ
    if not cursor:
        # Giả sử chưa chạy gì, set ngày data bắt đầu là 2020-01-01
        next_data_date_str = "2020-01-01"
        last_run_real_date = "1970-01-01" # Ngày quá khứ xa xăm
    else:
        # Tách cursor ra thành 2 phần
        try:
            last_run_real_date, next_data_date_str = cursor.split("|")
        except ValueError:
            # Nếu cursor lỗi định dạng cũ, reset lại
            last_run_real_date = "1970-01-01"
            next_data_date_str = "2020-01-01"

    # 2. Kiểm tra điều kiện thời gian thực tế
    # Nếu chưa đến 12h trưa -> Chưa làm gì cả
    if now.hour < TARGET_HOUR:
        return SkipReason(f"Chưa đến {TARGET_HOUR}h trưa. Hiện tại là {now.hour}h.")

    # 3. Kiểm tra xem HÔM NAY đã chạy chưa?
    if last_run_real_date == today_str:
        return SkipReason(f"Hôm nay ({today_str}) đã chạy data ngày {next_data_date_str} rồi. Hẹn mai gặp lại!")

    # 4. Đến đây nghĩa là: Đã qua 12h trưa VÀ hôm nay chưa chạy lần nào -> BẮN LỆNH CHẠY
    
    # Tính toán ngày tiếp theo cho lần chạy SAU (để lưu vào cursor)
    current_data_date = datetime.strptime(next_data_date_str, "%Y-%m-%d")
    next_cycle_data_date = current_data_date + timedelta(days=1)
    next_cycle_data_date_str = next_cycle_data_date.strftime("%Y-%m-%d")

    # Tạo cursor mới: "Hôm nay|Ngày data kế tiếp"
    new_cursor = f"{today_str}|{next_cycle_data_date_str}"
    
    # Update cursor ngay lập tức
    context.update_cursor(new_cursor)
    
    # Bắn run request
    run_key = f"daily_rolling_{today_str}_{next_data_date_str}"
    context.log.info(f"Triggering run for data date: {next_data_date_str}")
    
    yield RunRequest(
        run_key=run_key,
        partition_key=next_data_date_str
    )

# --- 6. ĐĂNG KÝ ---
defs = Definitions(
    assets=[batch_ingestion_asset],
    jobs=[ingestion_job],
    sensors=[rolling_playback_sensor] # <--- Dùng Sensor này thay cho Schedule
)