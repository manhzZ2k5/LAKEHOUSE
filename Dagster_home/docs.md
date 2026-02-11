# Xử lý Batch Ingestion & Playback Sensor trong Dagster

Tài liệu này giải thích những thay đổi gần đây trong code Dagster, tập trung vào `Batch Ingestion Asset` và `Playback Sensor`.

## 1. Batch Ingestion Asset (`batch_ingestion_asset`)

`batch_ingestion_asset` là một asset của Dagster được thiết kế để xử lý dữ liệu theo từng lô (batch) dựa trên phân vùng thời gian (time partitions).

### Chức năng:
- **Thực thi phân vùng (Partitioned Execution)**: Hoạt động dựa trên định nghĩa phân vùng thời gian (`covid_partitions`), nghĩa là các lần chạy được kích hoạt cho các khoảng thời gian cụ thể (ví dụ: hàng ngày, hàng tháng).
- **Xử lý thuần Python (Pure Python Logic)**: Nó ủy quyền việc xử lý dữ liệu thực tế cho hàm Python thuần túy `process_batch_data` nằm trong file `sml_logic.py`. Điều này giữ cho logic của Dagster asset sạch sẽ và chỉ tập trung vào việc điều phối.
- **Đầu vào (Inputs)**:
    - `start_date`: Ngày bắt đầu của cửa sổ thời gian phân vùng.
    - `end_date`: Ngày kết thúc của cửa sổ thời gian phân vùng.
    - `db_con_str`: Chuỗi kết nối cơ sở dữ liệu.
    - `minio_config`: Cấu hình để kết nối với kho lưu trữ MinIO.
- **Đầu ra (Outputs)**: Ghi log kết quả xử lý vào Dagster event log.

## 2. Playback Sensor (`playback_sensor`)

`playback_sensor` được thiết kế để mô phỏng việc nạp dữ liệu lịch sử hoặc "phát lại" (playback) dữ liệu.

### Chức năng:
- **Kích hoạt tuần tự (Sequential Triggering)**: Nó kích hoạt các lần chạy cho `batch_ingestion_asset_job` một cách tuần tự, tiến về phía trước theo thời gian.
- **Quản lý con trỏ (Cursor Management)**: Sử dụng một con trỏ (`context.cursor`) để theo dõi ngày đã xử lý gần nhất.
- **Logic mô phỏng (Simulation Logic)**:
    - Nếu chưa có con trỏ nào, bắt đầu từ `2020-01-01`.
    - Trong mỗi lần thực thi (mỗi 30 giây), nó tiến ngày thêm 5 ngày.
    - Nó ngừng kích hoạt các lần chạy mới khi ngày mô phỏng vượt quá năm `2022`.
- **Yêu cầu chạy (Run Request)**: Đối với mỗi bước, nó tạo ra một `RunRequest` với một `partition_key` cụ thể, đảm bảo asset chạy đúng cho ngày được mô phỏng.

## Tóm tắt các sửa lỗi

Các lỗi sau đã được sửa trong mã nguồn:
1.  **definitions.py**:
    - Sửa `DB_CONNECTION_STR` (chưa được định nghĩa) thành `DB_CON_STR` (đã được định nghĩa).
    - Sửa tham số từ khóa trong lệnh gọi `process_batch_data` từ `db_conn_str` thành `db_con_str` để khớp với định nghĩa hàm.
2.  **sml_logic.py**:
    - Sửa lệnh gọi `engine.connect` bằng cách thêm dấu ngoặc đơn: `with engine.connect() as conn:`.
