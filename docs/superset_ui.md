# 📊 Thiết Kế UI/UX Dashboard: Phân Tích Đa Chiều COVID-19 (Superset)

**Mục tiêu Dashboard:** Cung cấp cái nhìn toàn cảnh về tình hình dịch bệnh và đánh giá hiệu quả của các biện pháp can thiệp (Chính sách phong tỏa, Chiến dịch tiêm chủng) dựa trên Galaxy Schema tầng Gold.

**Bố cục tổng thể:** Gồm 1 Thanh Filter dùng chung (Global Filters) và 3 Tabs phân tích chuyên sâu.

---

## 🎛️ 1. Thanh Bộ Lọc Toàn Cục (Global Filters Box)
*Vị trí: Lề trái (Left Sidebar) hoặc cố định trên cùng (Top Bar) để áp dụng cho toàn bộ các biểu đồ.*

* **Time Range (Khoảng thời gian):** Lọc theo `dim_date.full_date` (VD: Last 1 year, Custom range).
* **Country Filter (Quốc gia):** Dropdown đa chọn (Multi-select) từ `dim_location.country_name`.
* **Metric Selector (Tùy chọn - Dành cho User nâng cao):** Dropdown để user chọn xem dữ liệu theo "Số tuyệt đối" hoặc "Tỷ lệ / 1 triệu dân".

---

## 📑 2. Thiết kế chi tiết các Tabs

### Tab 1: 🌐 Tổng quan Toàn cầu (Executive Summary)
*Mục đích: Cho cấp quản lý (C-level) nắm bắt con số tổng quan nhanh nhất.*

| Vị trí | Loại Biểu đồ (Chart Type) | Dữ liệu đầu vào (Metrics & Dimensions) | Mục đích / Ý nghĩa |
| :--- | :--- | :--- | :--- |
| **Row 1** (Top) | **Big Number with Trendline** (3 block ngang nhau) | 1. Tổng ca nhiễm (`SUM(new_confirmed)`) <br> 2. Tổng tử vong (`SUM(new_deaths)`) <br> 3. Lũy kế tiêm chủng (`MAX(cumulative_persons_fully_vaccinated)`) | Hiển thị KPI cốt lõi. Đường trendline nhỏ bên dưới cho thấy xu hướng 30 ngày gần nhất. |
| **Row 2** (Middle) | **World Map** (Bản đồ thế giới) | Location: `country_name` <br> Metric: `SUM(new_confirmed)` | Dùng Heatmap (màu đỏ đậm dần) để thấy ngay "tâm dịch" toàn cầu đang nằm ở đâu. |
| **Row 3** (Bottom) | **Bar Chart** (Biểu đồ cột ngang) | Y-Axis: `country_name` <br> X-Axis: `SUM(new_deaths)` (Top 10) | Bảng xếp hạng 10 quốc gia chịu thiệt hại về sinh mạng nặng nề nhất. |

### Tab 2: ⚖️ Tác động của Chính sách (Policy Impact)
*Mục đích: Lệnh phong tỏa, đóng cửa trường học có làm gãy đà tăng của dịch không?*

| Vị trí | Loại Biểu đồ (Chart Type) | Dữ liệu đầu vào (Metrics & Dimensions) | Mục đích / Ý nghĩa |
| :--- | :--- | :--- | :--- |
| **Row 1** (Full width) | **Mixed Time-Series** (Đường + Miền) | X-Axis: `full_date` <br> Y-Axis (Trái - Area): `new_confirmed` <br> Y-Axis (Phải - Line): `stringency_index` | Trực quan hóa **Độ trễ chính sách**. Xem độ dốc của ca nhiễm có giảm sau khi đường chính sách (siết chặt) tăng lên không. |
| **Row 2** (Left 50%) | **Scatter Plot** (Phân tán) | X-Axis: `stringency_index` <br> Y-Axis: `new_confirmed` <br> Group by: `country_name` | Tìm ra các quốc gia "ngoại lệ": Nước nào cấm ngặt nhưng dịch vẫn tăng, nước nào nới lỏng nhưng dịch vẫn giảm. |
| **Row 2** (Right 50%) | **Pie Chart** / **Donut Chart** | Group by: `school_closing` (0, 1, 2, 3) <br> Metric: `SUM(new_confirmed)` | Phân bổ số ca nhiễm theo các mức độ đóng cửa trường học khác nhau. |

### Tab 3: 💉 Hiệu quả Vaccine & Y tế (Vaccine & Healthcare)
*Mục đích: Đánh giá sức chống chịu của hệ thống y tế và màng lọc Vaccine.*

| Vị trí | Loại Biểu đồ (Chart Type) | Dữ liệu đầu vào (Metrics & Dimensions) | Mục đích / Ý nghĩa |
| :--- | :--- | :--- | :--- |
| **Row 1** (Full width) | **Dual-Axis Line Chart** (Đường kép) | X-Axis: `full_date` <br> Y-Axis 1 (Line Xanh): Tỷ lệ tiêm chủng <br> Y-Axis 2 (Line Đỏ): `SUM(new_deaths)` | Chứng minh tính sinh tồn: Khi đường xanh (vaccine) đi lên, đường đỏ (tử vong) phải đi ngang hoặc cắm xuống. |
| **Row 2** (Left 50%) | **Bubble Chart** (Bong bóng) | X-Axis: `gdp_per_capita_usd` <br> Y-Axis: Tỷ lệ phủ Vaccine <br> Bubble Size: `population` | Trả lời câu hỏi vĩ mô: Có phải các quốc gia giàu (GDP cao) thì tốc độ phủ Vaccine nhanh hơn không? |
| **Row 2** (Right 50%) | **Time-Series Bar** (Biểu đồ cột dọc) | X-Axis: `full_date` <br> Metrics: `icu_patients`, `hosp_patients` | Theo dõi áp lực lên giường bệnh và phòng hồi sức tích cực theo từng làn sóng dịch. |

---

## 🛠️ Hướng dẫn Setup Virtual Dataset (Cho Data Engineer)
Để Superset vẽ mượt các biểu đồ trên mà không bắt người dùng (Business User) phải biết viết lệnh JOIN, hãy tạo một **Virtual Dataset** trong giao diện `SQL Lab` của Superset với đoạn mã sau:

```sql
SELECT 
    d.full_date, d.year, d.month,
    l.country_name, l.population, l.gdp_per_capita_usd,
    c.new_confirmed, c.new_deaths,
    p.stringency_index, p.school_closing,
    v.new_persons_vaccinated, v.cumulative_persons_fully_vaccinated,
    h.icu_patients, h.hosp_patients
FROM fact_covid_cases c
JOIN dim_date d ON c.date_key = d.date_key
JOIN dim_location l ON c.location_key = l.location_key
LEFT JOIN fact_policy_impact p ON c.date_key = p.date_key AND c.location_key = p.location_key
LEFT JOIN fact_vaccination v ON c.date_key = v.date_key AND c.location_key = v.location_key
LEFT JOIN fact_healthcare_system h ON c.date_key = h.date_key AND c.location_key = h.location_key