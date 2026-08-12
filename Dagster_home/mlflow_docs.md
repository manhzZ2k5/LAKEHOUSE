# Tích hợp Huấn luyện Mô hình & MLflow Registry trong Dagster

Tài liệu này giải thích thiết kế và những thay đổi gần đây trong phần huấn luyện Machine Learning (ML), tập trung vào các luồng Dagster Assets, việc quản lý vòng đời bằng MLflow, và các bản vá lỗi Schema.

## 1. Dagster ML Assets (`auto_train_healthcare_forecast` & `auto_train_policy_effectiveness`)

Đây là hai Asset chịu trách nhiệm tự động hóa toàn bộ quá trình chuẩn bị dữ liệu, huấn luyện, và đánh giá mô hình.

### Chức năng:
- **Tích hợp Nguồn Dữ Liệu (Data Integration)**:
    - `Healthcare Forecast`: Tự động tải và tính toán 6 đặc trưng nâng cao từ Silver Data (thông qua DeltaLake trên MinIO).
    - `Policy Effectiveness`: Tải dữ liệu từ PostgreSQL (bảng `covid_optimized`), thiết kế 5 đặc trưng đo lường hiệu quả giãn cách.
- **Tự động Thử nghiệm Thuật toán (Algorithm Benchmarking)**:
    - Trong mỗi lần chạy, Dagster Asset sẽ huấn luyện thử nhiều thuật toán khác nhau (RandomForest vs XGBoost cho Y tế; LinearRegression vs HistGradientBoosting cho Chính sách).
    - Đánh giá thông qua các chỉ số như `RMSE`, `MAE`, `R²` bằng cơ chế Hold-out Time Split.
- **Lưu vết và Đăng ký (Tracking & Registry)**:
    - Kết quả huấn luyện (Metrics) và Mô hình được tự động lưu vết vào `MLflow Tracking`.
    - Thuật toán có chỉ số `RMSE` tốt nhất sẽ tự động được chọn và đưa vào `MLflow Model Registry` dưới các tên thống nhất là `Healthcare_Covid_Model` và `Policy_Covid_Model`.

## 2. Quản lý Vòng đời (Model Lifecycle & Registry)

MLflow đóng vai trò như một kho chứa phiên bản (Version Control) cho các mô hình.

### Chức năng:
- **Tự động Promote**: Hàm `register_best_model` được thiết kế để tự động thay đổi trạng thái (Transition Stage) của mô hình tốt nhất lên nhãn `Production`.
- **Tự động Archive**: Bất kỳ mô hình cũ nào đang giữ nhãn `Production` sẽ tự động bị hạ cấp xuống `Archived` để nhường chỗ cho mô hình mới, đảm bảo API luôn chỉ tải bản duy nhất.
- **Flexible Model Loader (API)**: Bên trong `api/main.py`, hàm `_load_model_flexible` được áp dụng để linh hoạt tải mô hình dựa vào Registry Stage hoặc Latest Version, thay vì phụ thuộc vào một đường dẫn nội bộ cục bộ. Điều này giúp tách biệt hoàn toàn ứng dụng Streamlit/API khỏi lõi Dagster.

## Tóm tắt các sửa lỗi (Bug Fixes & Schema Enforcement)

Các lỗi nghiêm trọng sau đã được phân tích và khắc phục trong luồng MLflow:

1.  **Lỗi Triệt tiêu Cột (Zero-variance Drop Bug)**:
    - *Vấn đề*: Trong tập dữ liệu khởi điểm (tháng 3-4/2020), các cột như `vaccination_rate` có giá trị `0` toàn bộ. Bộ lọc `std() > 0` tự động loại bỏ các cột này, khiến Schema lưu trên MLflow bị thiếu thốn (VD: nhận 1 input thay vì 6 input). Khi gọi API sẽ sinh ra lỗi thiếu tham số.
    - *Khắc phục*: Gỡ bỏ hoàn toàn bộ lọc `std() > 0` trong các file `ml_assets.py`. Cho phép mô hình học trên toàn bộ các cột gốc.
2.  **Lỗi Xung đột Định dạng Schema (Type Mismatch `int64` vs `float64`)**:
    - *Vấn đề*: Các cột dữ liệu số nguyên (VD: cấp độ đóng cửa trường học `0-3`) được `pandas` tải vào RAM dưới dạng `int64`. Khi đẩy lên MLflow, Schema bị trói buộc cứng vào kiểu `Long (integer)`. Tuy nhiên JSON Body từ giao diện Streamlit/FastAPI lại bắn sang chuẩn dữ liệu `Float (Double)`, khiến MLflow Exception chặn luồng predict.
    - *Khắc phục*: Can thiệp vào Data Loader (`ml_data_gold.py`), ép kiểu dữ liệu tường minh `.astype(float)` cho toàn bộ tập đặc trưng. Đảm bảo MLflow nhận diện toàn bộ mô hình dưới dạng Schema `Double`, giúp tương thích hoàn hảo 100% với REST API Payload.
