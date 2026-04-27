import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mlflow.pyfunc
import pandas as pd
import numpy as np

# Force Uvicorn Reload


logger = logging.getLogger("lakehouse_api")
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_URI)

healthcare_model = None
policy_model     = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload cả 2 models vào memory khi API khởi động — tránh cold start."""
    global healthcare_model, policy_model
    logger.info("[Startup] Preloading ML models từ MLflow Registry...")
    # Chú ý: _load_model_flexible chưa được định nghĩa ở đây (định nghĩa sau).
    # Preload thực sự sẽ xảy ra ở lần request đầu tiên (lazy load an toàn).
    logger.info("[Startup] API sẵn sàng. Models sẽ được load tự động lần request đầu.")
    yield
    logger.info("[Shutdown] API dừng.")


# ── Schema khớp với feature_cols trong ml_assets.py ──────────────────────────
class HealthcareRequest(BaseModel):
    """Dự báo tỷ lệ ca nhiễm mới (incidence_rate) sau 14 ngày, đơn vị: ca/100,000 dân."""
    # fact_vaccination group
    vaccination_rate:      float  # 0.0 – 1.0 (% tiêm đủ mũi / dân số)
    # fact_covid_cases group
    new_confirmed_7d_avg:  float  # Trung bình ca nhiễm 7 ngày qua
    # fact_healthcare_system group
    testing_rate:          float  # Xét nghiệm / dân số
    icu_rate_per_1m:       float  # Ca ICU mới / 1 triệu dân (normalized)
    # dim_location group
    elderly_pct:           float  # Tỷ lệ dân số trên 70 tuổi (0.0 – 1.0)
    # fact_social_behavior group
    search_trends_anosmia: float  # Google Trends: tìm kiếm mất khứu giác (0-100)


class PolicyRequest(BaseModel):
    """Dự báo tốc độ tăng trưởng ca nhiễm sau 14 ngày dựa trên chính sách."""
    # fact_policy_impact group
    school_closing:             float  # 0=Bình thường, 3=Đóng toàn bộ
    workplace_closing:          float  # 0=Bình thường, 3=WFH bắt buộc
    stay_at_home_requirements:  float  # 0=Không yêu cầu, 3=Lệnh ở nhà toàn quốc
    stringency_index:           float  # 0–100: Chỉ số Oxford tổng hợp
    # fact_vaccination group
    vaccination_rate:           float  # 0.0 – 1.0 (context tiêm vaccine)


# ── Load models từ MLflow Registry ───────────────────────────────────────────────────
from mlflow.tracking.client import MlflowClient


def _load_model_flexible(model_name: str):
    """
    Tải model từ MLflow Registry theo thứ tự ưu tiên:
    1. Stage 'Production' (cũ style, MLflow < 2.9)
    2. Alias 'production' (mới style, MLflow >= 2.9)
    3. Latest version bất kỳ stage nào (fallback)
    """
    client = MlflowClient(tracking_uri=MLFLOW_URI)

    # Thử 1: Production stage (MLflow cũ)
    try:
        return mlflow.pyfunc.load_model(f"models:/{model_name}/Production")
    except Exception:
        pass

    # Thử 2: Tìm version mới nhất bất kỳ stage
    try:
        versions = client.search_model_versions(f"name='{model_name}'")
        if not versions:
            raise ValueError(f"Không có version nào cho model '{model_name}'")
        latest = sorted(versions, key=lambda v: int(v.version), reverse=True)[0]
        uri = f"runs:/{latest.run_id}/model"
        logger.info(f"[{model_name}] Dùng version {latest.version} (run_id={latest.run_id[:8]}...)")
        return mlflow.pyfunc.load_model(uri)
    except Exception as e:
        raise ValueError(f"Không tải được model '{model_name}' từ MLflow. Lỗi: {e}")


def get_healthcare_model():
    global healthcare_model
    if healthcare_model is None:
        try:
            healthcare_model = _load_model_flexible("Healthcare_Covid_Model")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return healthcare_model


def get_policy_model():
    global policy_model
    if policy_model is None:
        try:
            policy_model = _load_model_flexible("Policy_Covid_Model")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return policy_model

app = FastAPI(title="Lakehouse ML API", lifespan=lifespan)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "Lakehouse ML API đang chạy!"}


@app.get("/health")
def health():
    return {
        "status":           "healthy",
        "healthcare_model": healthcare_model is not None,
        "policy_model":     policy_model is not None,
    }


@app.get("/warmup")
def warmup():
    """Kiểm tra trạng thái models. Sử dụng trước lần predict đầu để chắc models đã load."""
    return {
        "healthcare_model_ready": healthcare_model is not None,
        "policy_model_ready":     policy_model is not None,
        "message": "All models ready" if (healthcare_model and policy_model)
                   else "Some models not yet loaded — chạy Dagster train trước!",
    }

@app.get("/refresh_models")
def refresh_models():
    """Reset cache — lần predict kế tiếp sẽ tải model mới nhất từ MLflow."""
    global healthcare_model, policy_model
    healthcare_model = None
    policy_model     = None
    return {"message": "Đã reset cache. Model mới sẽ được tải tự động."}

@app.post("/predict/healthcare")
def predict_healthcare(req: HealthcareRequest):
    try:
        model = get_healthcare_model()
        df = pd.DataFrame([{
            "vaccination_rate":      req.vaccination_rate,
            "new_confirmed_7d_avg":  req.new_confirmed_7d_avg,
            "testing_rate":          req.testing_rate,
            "icu_rate_per_1m":       req.icu_rate_per_1m,
            "elderly_pct":           req.elderly_pct,
            "search_trends_anosmia": req.search_trends_anosmia,
        }])
        # Chỉ giữ các cột mà model đã train (dựa vào feature_names_in_ nếu có)
        if hasattr(model, '_model_impl'):
            try:
                sklearn_pipe = model._model_impl
                if hasattr(sklearn_pipe, 'feature_names_in_'):
                    df = df[sklearn_pipe.feature_names_in_]
            except Exception:
                pass
        pred = model.predict(df)
        value = float(pred[0]) if hasattr(pred, '__len__') else float(pred)
        rate  = round(max(value, 0), 2)  # incidence rate không âm

        # Phân loại mức độ nguy hiểm theo WHO classification
        if rate < 10:
            risk_level = "Low"
        elif rate < 50:
            risk_level = "Medium"
        elif rate < 150:
            risk_level = "High"
        else:
            risk_level = "Critical"

        return {
            "incidence_rate_14d": rate,
            "risk_level":         risk_level,
            "unit":               "ca / 100,000 dân",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Healthcare] Lỗi khi predict")
        raise HTTPException(status_code=500, detail=f"Lỗi predict healthcare: {type(e).__name__}: {e}")

@app.post("/predict/policy")
def predict_policy(req: PolicyRequest):
    try:
        model = get_policy_model()
        df = pd.DataFrame([{
            "school_closing":            req.school_closing,
            "workplace_closing":         req.workplace_closing,
            "stay_at_home_requirements": req.stay_at_home_requirements,
            "stringency_index":          req.stringency_index,
            "vaccination_rate":          req.vaccination_rate,
        }])
        pred = model.predict(df)
        value = float(pred[0]) if hasattr(pred, '__len__') else float(pred)
        rate  = round(value, 4)

        # Phân loại hiệu quả chính sách
        if rate < -0.10:
            effectiveness = "Highly Effective"    # Giảm > 10%
        elif rate < -0.05:
            effectiveness = "Effective"            # Giảm 5–10%
        elif rate < 0.05:
            effectiveness = "Neutral"              # Thay đổi không đáng kể
        else:
            effectiveness = "Ineffective"          # Tăng > 5%

        trend = "giảm" if rate < 0 else "tăng"
        return {
            "predicted_growth_rate": rate,
            "policy_effectiveness":  effectiveness,
            "interpretation":        f"Dịch dự kiến {trend} {abs(rate)*100:.1f}% trong 14 ngày",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[Policy] Lỗi khi predict")
        raise HTTPException(status_code=500, detail=f"Lỗi predict policy: {type(e).__name__}: {e}")
