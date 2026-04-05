# 🌌 Thiết kế Dữ liệu Tầng Gold: Galaxy Schema (Lược đồ Thiên Hà)

Để phục vụ bài toán phân tích đa chiều về đại dịch COVID-19 (Tác động của Chính sách, Hiệu quả Vaccine, Hành vi Xã hội và Áp lực Y tế), hệ thống áp dụng mô hình **Galaxy Schema (Fact Constellation)** tại tầng Gold. 

Mô hình này sử dụng **Conformed Dimensions (Các bảng chiều dùng chung)** kết nối với nhiều bảng Fact chuyên biệt, đảm bảo khả năng mở rộng linh hoạt (Horizontal Scaling) và tối ưu hóa tuyệt đối cho các công cụ BI (Dashboard).



## 🎯 Các Nguyên Tắc Thiết Kế Cốt Lõi Đã Áp Dụng:
1. **Không sử dụng cột `id` tự tăng trong bảng Fact:** Khóa chính của các bảng Fact là tổ hợp Khóa ngoại `(date_key + location_key)`. Việc loại bỏ `id` giúp tiết kiệm dung lượng Delta Lake và tăng tốc độ xử lý của Spark.
2. **Tối ưu hóa `date_key`:** Chuyển từ kiểu `date` sang kiểu số nguyên `int` (định dạng `YYYYMMDD`) để tối đa hóa hiệu năng thực thi lệnh `JOIN`.
3. **Tách biệt Nguyên nhân và Hậu quả:** Chỉ số dịch bệnh (`new_confirmed`, `new_deaths`) được tách riêng thành một bảng Fact trung tâm (`fact_covid_cases`) độc lập với các bảng nguyên nhân (Chính sách, Vaccine), giúp Dashboard không bị sai lệch số liệu (fan trap) khi cross-filtering.

---

## 🧭 1. Các Bảng Chiều Dùng Chung (Conformed Dimensions)

Các bảng này đóng vai trò là bộ lọc (Slicers) và trục phân tích chính cho toàn bộ hệ thống.

### `dim_date`
*Bảng chiều thời gian.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **PK** | Mã ngày định dạng `YYYYMMDD` (VD: `20200125`) |
| `full_date` | `date` | | Ngày gốc, dùng để hiển thị nhãn trục X trên biểu đồ |
| `year` | `int` | | Năm |
| `month` | `int` | | Tháng (1 - 12) |
| `quarter` | `int` | | Quý (1 - 4) |

### `dim_location`
*Bảng chiều không gian địa lý và thông tin vĩ mô.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`location_key`** | `varchar` | **PK** | Mã định danh khu vực (Chuỗi MD5) |
| `country_name` | `varchar` | | Tên quốc gia |
| `population` | `bigint` | | Dân số tổng (Hỗ trợ tính tỷ lệ trên 1 triệu dân) |
| `gdp_per_capita_usd` | `float` | | GDP bình quân đầu người |

---

## 📊 2. Các Bảng Sự Kiện Chuyên Biệt (Fact Tables)

Các bảng Fact lưu trữ các chỉ số (Metrics) có thể tính toán, gom nhóm (SUM, AVG) theo thời gian và địa điểm.

### `fact_covid_cases` (Bảng Hậu Quả Trung Tâm)
*Lưu trữ diễn biến thực tế của dịch bệnh.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date` |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location` |
| `new_confirmed` | `int` | Metric | Số ca nhiễm mới ghi nhận trong ngày |
| `new_deaths` | `int` | Metric | Số ca tử vong mới ghi nhận trong ngày |

### `fact_policy_impact`
*Lưu trữ mức độ can thiệp của chính phủ.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date` |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location` |
| `stringency_index` | `float` | Metric | Chỉ số nghiêm ngặt của chính sách (0 - 100) |
| `school_closing` | `int` | Metric | Cấp độ đóng cửa trường học |
| `workplace_closing` | `int` | Metric | Cấp độ đóng cửa nơi làm việc |

### `fact_vaccination`
*Lưu trữ tiến độ tiêm chủng vaccine.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date` |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location` |
| `new_persons_vaccinated` | `int` | Metric | Số người được tiêm mũi mới trong ngày |
| `cumulative_persons_fully_vaccinated` | `int` | Metric | Lũy kế số người đã tiêm đủ liều |

### `fact_social_behavior`
*Lưu trữ sự thay đổi trong hành vi của người dân (Dữ liệu Mobility).*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date` |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location` |
| `mobility_retail_and_recreation` | `float` | Metric | Tỷ lệ thay đổi di chuyển đến khu giải trí/bán lẻ |
| `mobility_residential` | `float` | Metric | Tỷ lệ thay đổi di chuyển tại khu dân cư |
| `search_trends_symptoms` | `float` | Metric | Xu hướng tìm kiếm các triệu chứng bệnh trên Internet |

### `fact_healthcare_system`
*Lưu trữ dữ liệu về áp lực lên hệ thống y tế.*

| Tên Cột | Kiểu Dữ Liệu | Loại Khóa | Mô tả chi tiết |
| :--- | :--- | :--- | :--- |
| **`date_key`** | `int` | **FK** | Trỏ đến `dim_date` |
| **`location_key`** | `varchar` | **FK** | Trỏ đến `dim_location` |
| `icu_patients` | `int` | Metric | Số lượng bệnh nhân đang nằm phòng chăm sóc tích cực (ICU) |
| `hosp_patients` | `int` | Metric | Số lượng bệnh nhân đang nhập viện |
| `new_tests` | `int` | Metric | Số lượng xét nghiệm mới được thực hiện |