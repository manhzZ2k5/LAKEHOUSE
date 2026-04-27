# 🏥 COVID-19 Lakehouse ML Pipeline

Hệ thống Lakehouse tích hợp đầy đủ từ ingestion dữ liệu COVID-19 đến dự báo ML — xây dựng trên nền tảng **Dagster + MinIO + PostgreSQL + MLflow + FastAPI + Streamlit**.

---

## 📐 Kiến trúc tổng quan

```
COVID Open Data (GCS)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  BRONZE LAYER  (MinIO: bronze-lake)                             │
│  batch_ingestion_asset — Parquet from covid_optimized (PG)     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Spark ETL
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  SILVER LAYER  (MinIO: silver-lake / Delta Lake)                │
│  silver_covid_data — Merge 54 cột, fillna(0), dropDuplicates   │
└───────────┬────────────────────────────────┬────────────────────┘
            │ deltalake (no Spark)           │ PostgreSQL
            ▼                               ▼
┌─────────────────────┐         ┌──────────────────────────┐
│ Healthcare Forecast │         │  Policy Effectiveness    │
│ (Silver → MLflow)   │         │  (PostgreSQL → MLflow)   │
└─────────┬───────────┘         └──────────┬───────────────┘
          │                               │
          └──────────────┬────────────────┘
                         ▼
              ┌─────────────────────┐
              │   MLflow Registry   │
              │  Production Models  │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │   FastAPI (:8000)   │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │  Streamlit (:8501)  │
              └─────────────────────┘
```

---

## 🛠️ Stack công nghệ

| Layer | Công nghệ |
|---|---|
| Orchestration | Dagster |
| Object Storage | MinIO (Bronze/Silver/Gold Lake) |
| Table Format | Delta Lake (via `deltalake`) |
| ETL (Bronze→Silver) | Apache Spark 3.5.1 + Delta Spark 3.2.0 |
| Database | PostgreSQL |
| ML Training | scikit-learn 1.5.2, XGBoost, MLflow |
| ML Serving | FastAPI + Uvicorn |
| Frontend | Streamlit |
| Monitoring UI | Dagster UI (:3000), MLflow UI (:5000), MinIO Console (:9001) |

---

## ⚙️ Yêu cầu môi trường

- Docker Desktop với WSL 2 backend
- RAM tối thiểu **8GB** cấp cho Docker (khuyến nghị với máy 16GB)

### Cấu hình WSL 2 RAM (bắt buộc cho Spark)

Tạo file `C:\Users\<username>\.wslconfig`:

```ini
[wsl2]
memory=8GB
processors=4
swap=4GB
pageReporting=false
```

Sau đó restart WSL:
```bash
wsl --shutdown
```

Khởi động lại Docker Desktop.

---

## 🚀 Hướng dẫn khởi động

### Bước 1 — Clone & chuẩn bị

```bash
git clone <repository-url>
cd LAKEHOUSE
```

Tạo file `.env` từ mẫu (nếu chưa có):
```env
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123
POSTGRES_DB=lakehouse_db
MINIO_ROOT_USER=minio_admin
MINIO_ROOT_PASSWORD=minio_secret_secure_password_123
MLFLOW_TRACKING_URI=http://mlflow:5000
```

### Bước 2 — Build và khởi động toàn bộ stack

```bash
docker-compose up -d --build
```

> ⏱️ Lần đầu build mất **15-30 phút** do tải PySpark, Delta Spark, MLflow...

Kiểm tra tất cả container đã chạy:
```bash
docker ps
```

### Bước 3 — Load dữ liệu vào PostgreSQL (chạy 1 lần)

```bash
# Load toàn bộ COVID Open Data vào PostgreSQL
docker exec -it lakehouse-dagster-webserver python /opt/dagster/app/code/../../../load_covid_data_to_postgres.py

# Fix Outer Join Mismatch cho dữ liệu chính sách Oxford
docker exec -it lakehouse-dagster-webserver python /opt/dagster/app/fix_policy_merge.py
```

> ⚠️ **Bước này bắt buộc** trước khi chạy bất kỳ Dagster asset nào. `fix_policy_merge.py` đảm bảo `school_closing`, `workplace_closing` được merge đúng với `new_confirmed` trong cùng một dòng.

---

## 🔄 Chạy MLflow Pipeline

### Chuẩn bị trước khi chạy ML Assets

Trước khi chạy `auto_train_healthcare_forecast` hoặc `auto_train_policy_effectiveness`, cần đảm bảo:

**1. Silver Layer đã được materialized** (nguồn dữ liệu cho Healthcare model):

Vào Dagster UI (`http://localhost:3000`) → Assets → chọn `silver_covid_data` → **Materialize**.

> Hoặc chạy backfill cho một khoảng thời gian cụ thể. Silver layer đọc từ Bronze (MinIO) qua Spark. Mỗi partition là 1 ngày dữ liệu COVID.

**2. PostgreSQL đã có dữ liệu policy** (nguồn cho Policy model):

Kiểm tra bằng cách chạy:
```bash
python diag_policy.py
```

Đầu ra mong đợi: `school_closing` có std > 0, `new_confirmed > 0`.

**3. MLflow server đang chạy**:

Truy cập `http://localhost:5000` — trang MLflow UI phải hiển thị.

---

### Chạy ML Assets trong Dagster UI

1. Mở `http://localhost:3000` → tab **Assets**
2. Chạy **Healthcare Forecast**:
   - Click `auto_train_healthcare_forecast` → **Materialize**
   - Đọc dữ liệu từ **Silver Lake** (MinIO Delta Lake) qua thư viện `deltalake`
   - Train RandomForest + XGBoost, chọn model tốt nhất theo RMSE
   - Đăng ký `Healthcare_Covid_Model` vào MLflow Registry với stage **Production**

3. Chạy **Policy Effectiveness**:
   - Click `auto_train_policy_effectiveness` → **Materialize**
   - Đọc dữ liệu từ **PostgreSQL** (`covid_optimized`) — đã fix OJM
   - Train LinearRegression + GradientBoosting, chọn model tốt nhất
   - Đăng ký `Policy_Covid_Model` vào MLflow Registry với stage **Production**

---

### Xác nhận kết quả training

Mở MLflow UI (`http://localhost:5000`) → **Models**:

| Model | Version | Stage |
|---|---|---|
| `Healthcare_Covid_Model` | latest | **Production** |
| `Policy_Covid_Model` | latest | **Production** |

---

## 🤖 Hai bài toán ML

### Bài toán 1: Dự báo Y tế (Healthcare Forecast)

**Mục tiêu:** Dự đoán **số ca nhiễm mới** (`new_confirmed`) sau 14 ngày.

| | Chi tiết |
|---|---|
| **Nguồn dữ liệu** | Silver Lake (MinIO: `s3://silver-lake/covid_cleaned/`) |
| **Features** | `cumulative_persons_fully_vaccinated`, `population`, `new_deceased` |
| **Target** | `new_confirmed` tại `t + 14 ngày` |
| **Algorithms** | RandomForest, XGBoost |
| **Evaluation** | RMSE, MAE, R² (time-series holdout split) |
| **API endpoint** | `POST /predict/healthcare` |

### Bài toán 2: Đánh giá Hiệu quả Chính sách (Policy Effectiveness)

**Mục tiêu:** Dự đoán **tốc độ tăng trưởng** số ca nhiễm sau 14 ngày dựa trên chính sách giãn cách.

| | Chi tiết |
|---|---|
| **Nguồn dữ liệu** | PostgreSQL (`covid_optimized` — đã fix OJM) |
| **Features** | `school_closing`, `workplace_closing`, `mobility_retail_and_recreation` |
| **Target** | `growth_rate` = `(new_confirmed[t+14] - new_confirmed[t]) / new_confirmed[t]` |
| **Algorithms** | LinearRegression, GradientBoosting |
| **Evaluation** | RMSE, MAE, R² |
| **API endpoint** | `POST /predict/policy` |

> **Lưu ý nguồn dữ liệu Policy:** Silver layer hiện chỉ có khoảng 35-40 ngày đầu dịch (2020-03 đến 2020-04) — đây là thời điểm `school_closing` gần như bằng 0 vì Bronze được ingest từ PostgreSQL **trước** khi chạy `fix_policy_merge.py`. Vì vậy Policy model tạm thời đọc từ PostgreSQL đã được fix. Khi Silver được backfill đầy đủ (2020→2022), có thể chuyển về Silver hoàn toàn.

---

## 🌐 Truy cập các dịch vụ

| Dịch vụ | URL | Mô tả |
|---|---|---|
| Dagster UI | http://localhost:3000 | Orchestration & Asset Lineage |
| MLflow UI | http://localhost:5000 | Experiment tracking & Model Registry |
| MinIO Console | http://localhost:9001 | Object Storage (Bronze/Silver/Gold Lake) |
| FastAPI Docs | http://localhost:8000/docs | Swagger UI cho ML API |
| Streamlit App | http://localhost:8501 | Dashboard dự báo COVID-19 |
| API Health | http://localhost:8000/health | Kiểm tra model đã load chưa |
| API Warmup | http://localhost:8000/warmup | Kiểm tra trạng thái chi tiết |

---

## 📁 Cấu trúc thư mục quan trọng

```
LAKEHOUSE/
├── docker-compose.yml              # Toàn bộ stack
├── .env                            # Biến môi trường (không commit)
├── fix_policy_merge.py             # Fix OJM cho dữ liệu policy
├── load_covid_data_to_postgres.py  # Load dữ liệu COVID vào PostgreSQL
│
├── Dagster_home/
│   ├── Dockerfile                  # Image Dagster (có Java cho Spark)
│   ├── requirements.txt            # Deps: dagster, pyspark, scikit-learn==1.5.2...
│   ├── dagster.yaml                # Config: PostgreSQL storage, QueuedRunCoordinator
│   └── code/
│       ├── definitions.py          # Entry point Dagster
│       ├── ingestion_assets.py     # Bronze layer assets
│       ├── silver_assets.py        # Silver layer assets (Spark)
│       ├── gold_assets.py          # Gold layer assets
│       ├── ml_assets.py            # ⭐ ML training assets (MLflow)
│       ├── ml_data_gold.py         # ⭐ Data loaders (Silver + PostgreSQL)
│       └── ml_utils.py             # Time-series split, metrics helpers
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt            # scikit-learn==1.5.2 (khớp với Dagster)
│   └── main.py                     # FastAPI: load MLflow model & serve predictions
│
├── streamlit_app/
│   └── app.py                      # Dashboard Streamlit 2 bài toán
│
├── etl_pipeline/
│   └── spark_logic.py              # Bronze→Silver Spark transformation
│
└── mlruns/                         # MLflow artifact storage (auto-generated)
```

---

## 🔧 Troubleshooting

### Lỗi: `ClassNotFoundException: com.amazonaws.auth.AWSCredentialsProvider`

Spark không tìm thấy AWS SDK JAR. Nguyên nhân: Ivy cache bị xóa sau khi restart Docker. Fix đã được áp dụng trong `docker-compose.yml` qua `PYSPARK_SUBMIT_ARGS` để dùng JAR local.

### Lỗi: `Java gateway process exited before sending its port number`

Thiếu RAM cho JVM. Đảm bảo `.wslconfig` cấu hình đúng (8GB+) và Docker Desktop đã tắt "Enable Resource Saver".

### Lỗi: `AttributeError: 'SimpleImputer' object has no attribute '_fill_dtype'`

scikit-learn version mismatch giữa Dagster (train) và API (serve). Đảm bảo cả 2 dùng `scikit-learn==1.5.2` trong `requirements.txt` và retrain lại models.

### Lỗi: `Không có dữ liệu Healthcare từ Silver Lake`

Silver data đang dùng filter `today - 730 days`. COVID data là lịch sử (2020-2022), cần dùng mốc cố định `2020-01-01`. File `ml_data_gold.py` đã được fix.

### Run Dagster bị Queued mãi không chạy

Kiểm tra `dagster-daemon` container:
```bash
docker logs lakehouse-dagster-daemon --tail 20
docker-compose restart dagster-daemon
```

---

## 📊 Medallion Architecture — Data Lineage

```
batch_ingestion_asset ──► silver_covid_data ──► auto_train_healthcare_forecast
        │                                   └──► auto_train_policy_effectiveness
        │                                              │
        │                                              ▼
        │                                     MLflow Model Registry
        │                                     (Healthcare & Policy: Production)
        │
        └──► gold: covid_analytic_cube (Superset/BI)
```

---

## 👥 Đóng góp

1. Tạo branch mới: `git checkout -b feature/ten-tinh-nang`
2. Commit thay đổi: `git commit -m "feat: mô tả"`
3. Push và tạo Pull Request

---

*Dự án này sử dụng [Google COVID-19 Open Data](https://health.google.com/covid-19/open-data/) cho mục đích học thuật và nghiên cứu.*
