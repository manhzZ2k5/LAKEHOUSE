import streamlit as st
import requests
import os

API_URL = os.getenv("API_URL", "http://api:8000")

st.set_page_config(page_title="Lakehouse ML Hub", layout="wide", page_icon="🏥")

st.sidebar.title("🔍 Chế độ Dự báo")
app_mode = st.sidebar.radio("Chọn bài toán", ["Dự báo Y tế 🏥", "Đánh giá Chính sách 📊"])

if app_mode == "Dự báo Y tế 🏥":
    st.title("🏥 Dự báo Số Ca Nhiễm Mới (Healthcare Forecast)")
    st.markdown("Dự đoán **tỷ lệ ca mắc mới trên 100,000 dân** sau 14 ngày tới dựa trên các chỉ số y tế lâm sàng và nhân khẩu học.")

    with st.form("healthcare_form"):
        st.subheader("Tham số đầu vào")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            vaccination_rate = st.slider("Tỷ lệ tiêm đủ vaccine (%)", 0.0, 100.0, 60.0, step=0.1)
            elderly_pct = st.slider("Tỷ lệ dân số trên 70 tuổi (%)", 0.0, 30.0, 5.0, step=0.1)
        
        with col2:
            testing_rate = st.slider("Tỷ lệ xét nghiệm (%)", 0.0, 100.0, 5.0, step=0.1)
            icu_rate_per_1m = st.number_input(
                "Số ca ICU mới / 1 triệu dân",
                min_value=0.0,
                value=15.0,
                step=1.0,
                help="Ví dụ: US ~150, VN ~8. Đã chuẩn hóa theo dân số."
            )
            
        with col3:
            new_confirmed_7d_avg = st.number_input("Trung bình ca nhiễm 7 ngày qua", min_value=0, value=1500, step=100)
            search_trends_anosmia = st.slider("Chỉ số tìm kiếm Mất khứu giác", 0, 100, 10, help="Dữ liệu Google Trends (0-100)")
            
        submit = st.form_submit_button("🔮 Chạy Mô hình Dự Báo", type="primary")

    if submit:
        payload = {
            "vaccination_rate":      vaccination_rate / 100.0,
            "new_confirmed_7d_avg":  float(new_confirmed_7d_avg),
            "testing_rate":          testing_rate / 100.0,
            "icu_rate_per_1m":       float(icu_rate_per_1m),
            "elderly_pct":           elderly_pct / 100.0,
            "search_trends_anosmia": float(search_trends_anosmia),
        }
        try:
            with st.spinner("Đang tải mô hình và tính toán ..."):
                res = requests.post(f"{API_URL}/predict/healthcare", json=payload, timeout=120)
            if res.status_code == 200:
                data = res.json()
                rate = data["incidence_rate_14d"]
                risk = data["risk_level"]
                
                st.success("Tải kết quả thành công!")
                colA, colB = st.columns(2)
                colA.metric(label="Dự báo Tỷ lệ lây nhiễm (Sau 14 ngày)", value=f"{rate:,.2f}", delta="Ca / 100k dân", delta_color="off")
                
                if risk == "Critical":
                    colB.error("🚨 CẢNH BÁO ĐỎ: NGUY CƠ BÙNG PHÁT RẤT CAO")
                elif risk == "High":
                    colB.warning("⚠️ Mức CAM: Tình hình ĐÁNG LO NGẠI")
                elif risk == "Medium":
                    colB.info("🟡 Mức VÀNG: Có rủi ro cục bộ")
                else: # Low
                    colB.success("✅ Mức XANH: Dịch đang ĐƯỢC KIỂM SOÁT")
            else:
                st.error(f"Lỗi từ API: {res.text}")
        except Exception as e:
            st.error(f"Lỗi kết nối / xử lý: {e}")

else:
    st.title("📊 Đánh giá Hiệu quả Chính sách (Policy Impact)")
    st.markdown("Dự báo **Tốc độ thay đổi ca nhiễm** sau 14 ngày theo các thiết lập giãn cách.")

    with st.form("policy_form"):
        st.subheader("Cài đặt Chính sách")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            school_closing = st.slider("Mức đóng cửa trường học (0-3)", 0, 3, 2)
            workplace_closing = st.slider("Mức đóng cửa công sở (0-3)", 0, 3, 1)
            
        with col2:
            stay_at_home = st.slider("Lệnh ở nhà / Phong tỏa (0-3)", 0, 3, 1)
            stringency = st.slider("Chỉ số độ nghiêm ngặt (0-100)", 0.0, 100.0, 45.0, help="Oxford Stringency Index")
            
        with col3:
            vaccination_rate = st.slider("Tỷ lệ tiêm chủng bối cảnh (%)", 0.0, 100.0, 60.0)
            
        submit = st.form_submit_button("📊 Phân tích Mức Lây lan", type="primary")

    if submit:
        payload = {
            "school_closing":            float(school_closing),
            "workplace_closing":         float(workplace_closing),
            "stay_at_home_requirements": float(stay_at_home),
            "stringency_index":          float(stringency),
            "vaccination_rate":          vaccination_rate / 100.0,
        }
        try:
            with st.spinner("Đang tính toán hiệu quả chính sách ..."):
                res = requests.post(f"{API_URL}/predict/policy", json=payload, timeout=120)
            if res.status_code == 200:
                data = res.json()
                rate = data["predicted_growth_rate"]
                eff  = data["policy_effectiveness"]
                interpr = data["interpretation"]
                pct = rate * 100
                
                st.success("Tính toán hoàn tất!")
                colA, colB = st.columns(2)
                colA.metric("Dự báo Tốc độ tăng trưởng", f"{pct:+.2f}%", help="So với số ca nhiễm hiện tại")
                
                if eff == "Highly Effective":
                    colB.success(f"🌟 RẤT HIỆU QUẢ: {interpr}")
                elif eff == "Effective":
                    colB.info(f"✅ HIỆU QUẢ: {interpr}")
                elif eff == "Neutral":
                    colB.warning(f"⚖️ TRUNG LẬP: {interpr}")
                else: 
                    colB.error(f"🚨 KÉM HIỆU QUẢ / NGHỊCH CHIỀU: {interpr}")
            else:
                st.error(f"Lỗi từ API: {res.text}")
        except Exception as e:
            st.error(f"Lỗi kết nối / xử lý: {e}")
