# Giải Thích Chi Tiết `definitions.py`

File `definitions.py` là nơi định nghĩa toàn bộ logic của Dagster project, bao gồm Assets, Jobs, Sensors và các cấu hình kết nối. Dưới đây là giải thích chi tiết từng phần:

## 1. Thiết Lập Môi Trường (Dòng 1-10)

```python
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)
```

- **Mục đích**: Đảm bảo Python có thể tìm thấy các module nằm trong cùng thư mục (như `sml_logic.py`).
- **Cách hoạt động**: Lấy đường dẫn thư mục hiện tại và thêm vào `sys.path` nếu chưa có.

## 2. Import Thư Viện (Dòng 12-20)

- `dagster`: Thư viện chính để định nghĩa pipeline.
- `datetime`, `timedelta`: Xử lý ngày tháng.
- `sml_logic`: Import hàm xử lý logic `process_batch_data` từ file bên ngoài.

## 3. Cấu Hình Biến Môi Trường & Kết Nối (Dòng 22-31)

```python
DB_CON_STR="postgresql://covid_user:123456@localhost:5432/COVID-19"

MINIO_CONFIG={...}
```

- **DB_CON_STR**: Chuỗi kết nối đến PostgreSQL.
- **MINIO_CONFIG**: Cấu hình để kết nối MinIO (S3 compatible storage).

## 4. Định Nghĩa Phân Vùng Thời Gian (Time Partitions) (Dòng 36-42)

```python
covid_partitions = TimeWindowPartitionsDefinition(
    cron_schedule="0 0 1/5 * *", 
    start="2020-01-01", 
    end="2022-09-16",
    fmt="%Y-%m-%d",
    timezone="Asia/Ho_Chi_Minh"
)
```

- **Mục đích**: Chia dữ liệu thành các khoảng thời gian nhỏ để xử lý.
- **`cron_schedule="0 0 1/5 * *"`**: Chạy 5 ngày một lần.
- **`start`/`end`**: Dữ liệu từ 2020 đến 2022.
- **`timezone`**: Múi giờ Việt Nam.

## 5. Batch Ingestion Asset (Asset Xử Lý Dữ Liệu) (Dòng 45-66)

```python
@asset(
    partitions_def=covid_partitions,
    group_name="ingestion"
)
def batch_ingestion_asset(context):
    ...
```

- **`@asset`**: Đánh dấu hàm này là một Asset của Dagster.
- **`partitions_def`**: Gắn asset này với lịch trình phân vùng đã định nghĩa ở trên.
- **Logic bên trong**:
    1.  Lấy `start_date` và `end_date` của partition đang chạy từ `context`.
    2.  Gọi hàm `process_batch_data` (logic thuần Python) để xử lý dữ liệu cho khoảng thời gian đó.
    3.  Trả về kết quả và log lại.

## 6. Job Definition (Định Nghĩa Job) (Dòng 72-76)

```python
ingestion_job = define_asset_job(
    name="batch_ingestion_asset_job",
    selection=["batch_ingestion_asset"]
)
```

- **Mục đích**: Tạo một Job cụ thể để chạy asset `batch_ingestion_asset`.
- **Quan trọng**: Sensor sẽ kích hoạt Job này.

## 7. Playback Sensor (Sensor Mô Phỏng) (Dòng 80-116)

```python
@sensor(
    job_name="batch_ingestion_asset_job",
    minimum_interval_seconds=30
)
def playback_sensor(context: SensorEvaluationContext):
    ...
```

- **Mục đích**: Tự động kích hoạt các lần chạy (runs) cho Job `batch_ingestion_asset_job` theo kịch bản "playback" (chạy lại dữ liệu quá khứ).
- **Logic**:
    1.  **Dùng Cursor**: Kiểm tra lần chạy cuối cùng (`context.cursor`). Nếu chưa có, bắt đầu từ `2020-01-01`.
    2.  **Tính ngày tiếp theo**: Mỗi lần chạy sensor (30s), nó nhảy tới 5 ngày tiếp theo.
    3.  **Điều kiện dừng**: Nếu vượt quá năm 2022, dừng lại (`SkipReason`).
    4.  **Kích hoạt Run**: Dùng `yield RunRequest(...)` để yêu cầu Dagster chạy Job cho ngày (`partition_key`) cụ thể.
    5.  **Cập nhật Cursor**: Lưu lại ngày vừa chạy để lần sau chạy tiếp từ đó.

## 8. Đăng Ký Definitions (Dòng 119-123)

```python
defs = Definitions(
    assets=[batch_ingestion_asset],
    sensors=[playback_sensor],
    jobs=[ingestion_job]
)
```

- **Mục đích**: Tập hợp tất cả Assets, Sensors, Jobs vào một object `Definitions` để Dagster nhận diện và hiển thị lên UI.
