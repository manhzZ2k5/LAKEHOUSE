# Môi trường Độc lập: Machine Learning (Sandbox)

Thư mục `ml/` này là môi trường Sandbox để nghiên cứu, thiết kế, và chạy thử (manual testing) các thuật toán Machine Learning trước khi đóng gói lên hệ thống tự động Dagster. 

Mặc dù toàn bộ quy trình Production đã được tự động hóa bên trong Dagster (file `Dagster_home/code/ml_assets.py`), thư mục này vẫn được giữ lại để phục vụ quá trình Debug, tinh chỉnh tham số (Hyperparameter tuning) hoặc phát triển model mới.

## Cấu trúc thư mục

*   `train_healthcare_forecast.py`: Chạy độc lập kịch bản dự báo Y tế (Lấy data từ Silver Lake MinIO).
*   `train_policy_effectiveness.py`: Chạy độc lập kịch bản đánh giá Chính sách (Lấy data từ PostgreSQL).
*   `data_silver.py`: Hàm kết nối với Delta Lake trên MinIO để lấy tập Silver.
*   `data_postgres.py`: Hàm kết nối với PostgreSQL lấy dữ liệu Policy.
*   `features.py` / `train_common.py`: Các hàm tiện ích dùng chung.

---

## 🛠 Điều Kiện Cần (Prerequisites)

Để chạy được các Script ML trong thư mục này mà không bị lỗi cấu hình, hệ thống của bạn **bắt buộc phải đáp ứng các điều kiện sau**:

### 1. Hạ tầng Dữ liệu (Backend Infrastructure)
Các dịch vụ cốt lõi sau phải đang ở trạng thái `Running` (thường thông qua `docker-compose up`):
- **MinIO**: Đã được nạp đầy đủ dữ liệu tại Bucket `silver-lake/covid_cleaned`. (Được sinh ra từ Dagster ETL).
- **PostgreSQL**: Đã có bảng `covid_optimized` và **đã chạy script `fix_policy_merge.py`** để vá lỗi Outer Join Mismatch.
- **MLflow Tracking Server**: Đang mở tại cổng `http://localhost:5000`.

### 2. File Môi trường (`.env`)
Các script sẽ tự động tìm kiếm file `.env` ở thư mục gốc (`d:\LAKEHOUSE\.env`). File này phải chứa đầy đủ thông tin truy cập:
- Thông số MinIO: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MLFLOW_S3_ENDPOINT_URL`...
- Thông số Postgres: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_DB`...
- Cấu hình MLflow: `MLFLOW_TRACKING_URI=http://localhost:5000`

---

## 🚀 Hướng Dẫn Chạy Script

Có 2 phương pháp để kích hoạt chạy file huấn luyện trong thư mục này:

### Phương pháp 1: Chạy qua Container `lakehouse-api`
Vì container `lakehouse-api` đã được cài đặt sẵn 100% các thư viện cần thiết (`pandas`, `scikit-learn`, `mlflow`, `deltalake`...) và đã được liên kết Volume thẳng tới thư mục `ml/`, bạn có thể chạy an toàn tuyệt đối bên trong nó:

1. Mở Terminal / PowerShell.
2. Chạy lệnh:
   ```bash
   docker exec -it lakehouse-api python ml/train_healthcare_forecast.py
   ```
   hoặc
   ```bash
   docker exec -it lakehouse-api python ml/train_policy_effectiveness.py
   ```

