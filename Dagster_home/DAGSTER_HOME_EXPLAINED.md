# Giải Phẫu: Dagster_home

Tài liệu này giải thích chi tiết về vai trò và cách hoạt động của thư mục `Dagster_home` trong kiến trúc Lakehouse của chúng ta.

## 1. Tổng quan
Trong Dagster, khái niệm "Home" (`DAGSTER_HOME`) rất quan trọng. Nó là nơi Dagster Instance (cả Webserver và Daemon) tìm kiếm:
1.  **Cấu hình hệ thống:** Kết nối Database nào? Lưu logs ở đâu?
2.  **Mã nguồn (Workspace):** Code của bạn nằm ở đâu để tôi load lên?

Trong dự án này, chúng ta mount thư mục `Dagster_home` từ máy Host vào đường dẫn `/opt/dagster/dagster_home` trong container.

---

## 2. Chi tiết từng file

### 📄 `dagster.yaml` (Bộ não của Instance)
Đây là file cấu hình cấp thấp (Instance Level Configuration).
*   **Tác dụng:** Nói cho Dagster biết "Hạ tầng của tôi gồm những gì?".
*   **Nội dung quan trọng:**
    *   `storage`: Cấu hình Postgres làm nơi lưu trữ Run History và Event Logs (thay vì SQLite mặc định).
    *   `compute_logs`: Cấu hình nơi lưu logs của các jobs đang chạy.
*   **Workflow:** Khi container khởi động, Dagster sẽ đọc file này đầu tiên. Nếu không có nó, Dagster sẽ báo lỗi hoặc dùng cấu hình mặc định tạm bợ (ephemeral).

### 📄 `workspace.yaml` (Bản đồ kho báu)
*   **Tác dụng:** Chỉ cho Dagster biết "Code định nghĩa data pipeline (Assets, Jobs) nằm ở đâu?".
*   **Nội dung:**
    ```yaml
    load_from:
      - python_file: code/definitions.py
    ```
*   **Workflow:** Sau khi khởi động Instance, Dagster đọc file này để nạp code của bạn lên giao diện UI. Nếu bạn thêm file code mới, bạn phải sửa file này.

### 📄 `Dockerfile` (Công thức chế biến)
*   **Tác dụng:** Định nghĩa môi trường chạy (Runtime Environment).
*   **Nội dung:**
    *   `FROM python:3.10`: Dùng Python 3.10.
    *   `COPY requirements.txt .`: Cài thư viện.
    *   `ENV DAGSTER_HOME=...`: Thiết lập biến môi trường quan trọng.
*   **Workflow:** File này được dùng khi bạn chạy `docker-compose build`. Nó đóng gói code và môi trường thành một "Image".

### 📄 `requirements.txt` (Nguyên liệu phụ gia)
*   **Tác dụng:** Liệt kê các thư viện Python cần thiết (ví dụ: `dagster`, `dagster-postgres`, `boto3`, `pandas`).
*   **Workflow:** Được `Dockerfile` đọc và chạy `pip install` khi build image.

### 📂 `code/` (Trái tim - Logic)
*   **Tác dụng:** Chứa logic nghiệp vụ thực sự của bạn.
*   **File `definitions.py`:**
    *   Nơi bạn định nghĩa `Asset` (Ví dụ: hàm đọc file CSV, hàm ghi vào MinIO).
    *   Nơi bạn kết nối các Asset thành một luồng xử lý.
*   **Workflow:** Đây là nơi bạn sẽ làm việc hàng ngày. Khi bạn sửa code ở đây, bạn chỉ cần reload lại Location trong giao diện Dagster (Reload Code) mà không cần restart container (nhờ cơ chế mount volume).

---

## 3. Workflow hoạt động như thế nào?

Quy trình khép kín hoạt động như sau:

1.  **Khởi động (`docker-compose up`):**
    *   Container `dagster-webserver` và `dagster-daemon` được tạo ra.
    *   Chúng đọc biến môi trường `DAGSTER_HOME=/opt/dagster/dagster_home`.

2.  **Cấu hình (Initialization):**
    *   Chúng tìm file `dagster.yaml` tại đường dẫn trên.
    *   Kết nối tới `postgres` container để đảm bảo hệ thống lưu trữ đã sẵn sàng.

3.  **Nạp Code (Code Loading):**
    *   Chúng đọc `workspace.yaml`.
    *   File này trỏ tới `code/definitions.py`.
    *   Dagster import file python này, tìm các hàm được đánh dấu `@asset`.

4.  **Thực thi (Execution):**
    *   Bạn bấm "Materialize" trên Web UI.
    *   Daemon nhận lệnh, kích hoạt "Run".
    *   Logic trong `definitions.py` được thực thi, sử dụng các thư viện đã cài từ `requirements.txt`.
    *   Kết quả (Logs) được ghi lại vào Postgres và hiển thị lên UI.

---
**Tóm lại:** Folder `Dagster_home` là cầu nối giữa code của bạn và hệ thống vận hành của Dagster.
