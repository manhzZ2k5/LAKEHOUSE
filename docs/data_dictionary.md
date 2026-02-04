# 📘 DATA OVERVIEW: COVID-19 LAKEHOUSE PROJECT

---

## 1. 🌐 Giới thiệu chung (General Introduction)

Bộ dữ liệu này được tối ưu hóa từ nguồn **Google COVID-19 Open Data** danh tiếng, phục vụ chuyên biệt cho việc xây dựng **Data Lakehouse** và phân tích chuyên sâu.

- **🚩 Nguồn gốc:** Google Health / Google Cloud Platform.
- **🎯 Mục tiêu:** Phân tích diễn biến dịch tễ, tiến độ vắc-xin và hiệu quả chính sách toàn cầu.
- **🛑 Trạng thái:** `Retrospective` (Dữ liệu lịch sử chuẩn - Đã chốt sổ).

---

## 2. 📊 Phạm vi Dữ liệu (Scope)

Dữ liệu bao trùm toàn bộ vòng đời của đại dịch COVID-19 trên phạm vi toàn cầu.

| Tiêu chí | Chi tiết |
| :--- | :--- |
| **📅 Thời gian** | Từ `01/01/2020` đến `15/09/2022` |
| **🌍 Không gian** | **246** Quốc gia & Vùng lãnh thổ |
| **📐 Độ phân giải** | 3 Cấp độ: **Quốc gia** (L0) > **Tỉnh/Bang** (L1) > **Quận/Huyện** (L2) |
| **💾 Khối lượng** | ~ **22.6 Triệu** dòng (Records) |

---

## 3. 🛠️ Chiến lược Tối ưu hóa (Optimization Strategy)

Quá trình chuyển đổi từ **Raw Data** sang **Silver Table** để tăng tốc độ xử lý cho Data Warehouse:

| Đặc điểm | 🔴 Dữ liệu gốc (Raw) | 🟢 Dữ liệu tối ưu (Optimized) | 🚀 Hiệu quả |
| :--- | :--- | :--- | :--- |
| **Số trường** | `> 500 cột` | `54 cột` | Loại bỏ thông tin rác/thừa. |
| **Dung lượng** | `~21 GB` | `~1.5 GB` | Giảm **90%** tải lưu trữ. |
| **Cấu trúc** | Phức tạp | Tinh gọn | Chuẩn hóa kiểu dữ liệu (`Date`, `Double`). |

---

## 4. 🗂️ Cấu trúc Thông tin (6 Core Data Groups)

54 trường dữ liệu được tổ chức thành 6 nhóm logic chặt chẽ:

### 1️⃣ Định danh (Identity & Time)
> *Khóa chính xác định không gian và thời gian.*
* `date`: Ngày ghi nhận.
* `location_key`, `country_name`: Định danh địa lý.

### 2️⃣ Dịch tễ học (Epidemiology)
> *Số liệu cốt lõi về sự lây lan của virus.*
* `new_confirmed`, `cumulative_confirmed`: Ca nhiễm.
* `new_deceased`, `cumulative_deceased`: Ca tử vong.

### 3️⃣ Y tế & Vắc-xin (Healthcare)
> *Năng lực y tế và miễn dịch cộng đồng.*
* `persons_vaccinated`: Tiến độ tiêm chủng.
* `hospital_beds_per_1000`, `icu_patients`: Khả năng đáp ứng y tế.

### 4️⃣ Nhân khẩu học (Demographics)
> *Dữ liệu nền tảng để chuẩn hóa và so sánh.*
* `population`: Dân số tổng.
* `age_groups`: Cấu trúc độ tuổi.
* `gdp_per_capita_usd`: Chỉ số kinh tế.

### 5️⃣ Chính sách (Government Response)
> *Đánh giá phản ứng của chính quyền (Nguồn: Oxford).*
* `stringency_index`: Chỉ số nghiêm ngặt (0-100).
* `school_closing`, `workplace_closing`: Các lệnh cấm cụ thể.

### 6️⃣ Hành vi & Xu hướng (Trends)
> *Dữ liệu hành vi người dùng (Nguồn: Google).*
* `mobility_residential`: Thay đổi thói quen ở nhà/ra đường.
* `search_trends_anosmia`: Xu hướng tìm kiếm triệu chứng bệnh.

---

## 5. ⚠️ Lưu ý Chất lượng Dữ liệu (Data Quality)

* **✅ Độ tin cậy cao nhất:** Ở cấp **Quốc gia (Level 0)**.
* **📉 Dữ liệu thưa (Sparse Data):**
    * **Vắc-xin:** `NULL` cao trước năm 2021 (do chưa có vắc-xin).
    * **Google Trends:** `NULL` ở các vùng dân cư nhỏ (do chính sách bảo mật Privacy Threshold).
    * **Chính sách:** Thường chỉ áp dụng chung cho cả nước, ít chi tiết xuống cấp huyện.

---
*Created for COVID-19 Lakehouse Project.*