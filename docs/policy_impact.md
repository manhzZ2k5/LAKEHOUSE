# 🚀 Dự án Data Lakehouse: Phân tích Tác động Chính sách đến dịch COVID-19

Dự án Xây dựng hệ thống Data Lakehouse tự động hóa toàn phần để xử lý, làm sạch và mô hình hóa dữ liệu COVID-19 (quy mô hàng chục triệu dòng). Hệ thống được thiết kế theo chuẩn **Medallion Architecture** (Bronze - Silver - Gold) của Databricks, đảm bảo tính mở rộng, toàn vẹn dữ liệu và tối ưu cho truy vấn BI.

---

## 🛠️ Công nghệ & Hạ tầng (Tech Stack)
Toàn bộ hệ thống được đóng gói và chạy độc lập trên môi trường Docker.
* **Orchestration:** Dagster (Quản lý Data Pipeline, Sensor, Auto-Materialize).
* **Data Storage:** MinIO (Object Storage đóng vai trò như S3 Data Lake).
* **Processing Engine:** Pandas (Tầng Ingestion) & Apache Spark (Tầng Transformation).
* **Table Format:** Delta Lake (Cung cấp ACID transactions, Time Travel, Schema Enforcement).
* **Database Source:** PostgreSQL.

---

## 🌊 Luồng Dữ liệu (Data Flow)

Kiến trúc đường ống dữ liệu được chia làm 3 tầng (Medallion Architecture):

### 1. Tầng Bronze (Raw Data)
* **Nhiệm vụ:** Trích xuất dữ liệu (Ingestion) nguyên bản từ Postgres.
* **Cơ chế:** Dagster sử dụng `rolling_playback_sensor` để quét tự động (Polling) theo thời gian. Mỗi khi qua ngày mới, hệ thống kích hoạt Pandas kéo dữ liệu và lưu xuống MinIO dưới định dạng `.parquet`.
* **Cấu trúc lưu trữ:** Phân vùng theo ngày `s3a://bronze-lake/date=YYYY-MM-DD/`

### 2. Tầng Silver (Cleaned Data)
* **Nhiệm vụ:** Làm sạch, chuẩn hóa và đóng gói thành "Nguồn chân lý duy nhất" (Single Source of Truth).
* **Cơ chế:** Kích hoạt hoàn toàn tự động bằng **Event-driven** (`AutoMaterializePolicy.eager()` của Dagster) ngay khi có partition mới ở tầng Bronze.
* **Các bước Làm sạch (Spark):**
  1. *Type Casting:* Ép kiểu thời gian (`DateType`) và ép kiểu số nguyên (`IntegerType`) khắt khe cho các cột count (ca nhiễm, tử vong, tiêm chủng).
  2. *Snake_case Standardization:* Dùng Regex chuẩn hóa toàn bộ tên cột (VD: `Country/Region` -> `country_region`).
  3. *Null Handling & Trimming:* Thay thế giá trị khuyết thiếu (`fillna(0)`), cắt khoảng trắng thừa (`trim`).
* **Format:** Ghi xuống MinIO bằng **Delta Lake** (`mergeSchema=true`) để tự động xử lý các biến động về cấu trúc cột qua từng ngày.

### 3. Tầng Gold (Business-Ready Data)
* **Nhiệm vụ:** Chuyển đổi bảng phẳng (Flat table) ở Silver thành mô hình **Galaxy Schema** tối ưu hóa cho công cụ BI (Dashboard). Tập trung phân tích tác động của các lệnh phong tỏa, đóng cửa trường học lên tốc độ lây lan dịch bệnh.

---

## 🌟 Thiết kế Dữ liệu Tầng Gold (Galaxy Schema)

Tầng Gold áp dụng **Galaxy Schema (Fact Constellation)** để phục vụ nhiều hướng phân tích khác nhau (chính sách, vaccine, hành vi xã hội, áp lực y tế). Các bảng Dimension được **dùng chung** để đảm bảo dữ liệu đồng nhất.

### 1. Các Bảng Chiều Dùng Chung

#### `dim_date`
*Bảng chiều thời gian.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **PK** | Định dạng `YYYYMMDD` (VD: `20200125`). |
| `full_date` | `date` | | Ngày gốc (VD: `2020-01-25`). |
| `year` | `int` | | Năm. |
| `month` | `int` | | Tháng (1 - 12). |
| `quarter` | `int` | | Quý (1 - 4). |

#### `dim_location`
*Bảng chiều địa lý và thông tin vĩ mô.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`location_key`** | `varchar` | **PK** | Mã định danh khu vực (Chuỗi MD5). |
| `country_name` | `varchar` | | Tên quốc gia. |
| `population` | `bigint` | | Dân số tổng. |
| `gdp_per_capita_usd` | `double` | | GDP bình quân đầu người. |

### 2. Các Bảng Fact

#### `fact_covid_cases`
*Bảng hậu quả trung tâm về diễn biến dịch.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date`. |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location`. |
| `new_confirmed` | `int` | Metric | Số ca nhiễm mới trong ngày. |
| `new_deaths` | `int` | Metric | Số ca tử vong mới trong ngày. |

#### `fact_policy_impact`
*Bảng chính sách can thiệp của chính phủ.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date`. |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location`. |
| `stringency_index` | `double` | Metric | Chỉ số nghiêm ngặt của chính phủ (0 - 100). |
| `school_closing` | `int` | Metric | Mức độ đóng cửa trường học. |
| `workplace_closing` | `int` | Metric | Mức độ đóng cửa nơi làm việc. |

#### `fact_vaccination`
*Bảng tiến độ tiêm chủng.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date`. |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location`. |
| `new_persons_vaccinated` | `int` | Metric | Số người được tiêm mới trong ngày. |
| `cumulative_persons_fully_vaccinated` | `int` | Metric | Lũy kế số người đã tiêm đủ liều. |

#### `fact_social_behavior`
*Bảng hành vi xã hội (Mobility + Search Trends).*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date`. |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location`. |
| `mobility_retail_and_recreation` | `double` | Metric | Thay đổi di chuyển đến khu giải trí/bán lẻ. |
| `mobility_residential` | `double` | Metric | Thay đổi di chuyển tại khu dân cư. |
| `search_trends_symptoms` | `double` | Metric | Xu hướng tìm kiếm triệu chứng. |

#### `fact_healthcare_system`
*Bảng áp lực hệ thống y tế.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date`. |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location`. |
| `icu_patients` | `int` | Metric | Số bệnh nhân ICU. |
| `hosp_patients` | `int` | Metric | Số bệnh nhân nhập viện. |
| `new_tests` | `int` | Metric | Số xét nghiệm mới trong ngày. |
