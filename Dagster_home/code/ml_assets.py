"""
ML Pipeline: Silver Lake (MinIO) → MLflow Registry

Dagster Lineage:
  batch_ingestion_asset (Bronze/ingestion)
        ↓  [daily partition]
  silver_covid_data (Silver/transformation)
        ↓  [deps=["silver_covid_data"]]
  auto_train_healthcare_forecast  →  Healthcare_Covid_Model (MLflow/Production)
  auto_train_policy_effectiveness →  Policy_Covid_Model    (MLflow/Production)

Hai bài toán:
  1. Dự báo Y tế: Dự đoán số ca nhiễm mới (new_confirmed) sau 14 ngày
     Features: cumulative_persons_fully_vaccinated, population, new_deceased
     Algorithms: RandomForest, XGBoost

  2. Đánh giá Chính sách: Dự đoán tốc độ tăng trưởng ca nhiễm sau 14 ngày
     dựa trên chính sách giãn cách (Oxford Index) và di chuyển (Google Mobility)
     Features: school_closing, workplace_closing, mobility_retail_and_recreation
     Algorithms: LinearRegression, GradientBoosting
"""
import os
from dagster import asset, Output, MetadataValue
from mlflow.tracking.client import MlflowClient
import mlflow
import mlflow.sklearn
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from xgboost import XGBRegressor

from ml_data_gold import load_healthcare_data, load_policy_data
from ml_utils import (
    time_holdout_split,
    regression_metrics,
    make_supervised_shift,
    make_growth_rate_target,
    cross_val_time_series,
    naive_mean_baseline,
)

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")


# ── Hàm dùng chung ────────────────────────────────────────────────────────────

def set_mlflow_env():
    mlflow.set_tracking_uri(MLFLOW_URI)


def build_pipeline(estimator):
    """
    Pipeline chuẩn: SimpleImputer → StandardScaler → Model.
    SimpleImputer (median) xử lý NaN còn sót.
    Silver đã fillna(0) nên imputer ít phải làm việc, nhưng giữ để robustness.
    """
    return Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("model",   estimator),
    ])


def register_best_model(run_id: str, best_rmse: float, model_name: str):
    """
    Đăng ký model tốt nhất lên MLflow Registry và set stage = Production.
    Model cũ đang Production sẽ bị Archived.
    """
    client = MlflowClient(tracking_uri=MLFLOW_URI)
    model_version = mlflow.register_model(f"runs:/{run_id}/model", model_name)

    # Archive phiên bản Production cũ (nếu có)
    for mv in client.search_model_versions(f"name='{model_name}'"):
        if mv.current_stage == "Production" and mv.version != model_version.version:
            client.transition_model_version_stage(
                name=model_name, version=mv.version, stage="Archived"
            )
    # Promote phiên bản mới lên Production
    client.transition_model_version_stage(
        name=model_name, version=model_version.version, stage="Production"
    )


# ── Asset 1: Dự báo Y tế (Healthcare Forecast) ────────────────────────────────
@asset(deps=["silver_covid_data"], group_name="mlflow")
def auto_train_healthcare_forecast(context):
    """
    Bài toán: Dự báo tỷ lệ ca nhiễm COVID-19 mới (incidence_rate) sau 14 ngày.
    Target: incidence_rate_14d = new_confirmed_future / population * 100,000
            (ca / 100,000 dân — có thể so sánh giữa các quốc gia)

    Nguồn dữ liệu: Silver Lake (s3://silver-lake/covid_cleaned/)
    Cấp phân tích:  Quốc gia (location_key 2 ký tự)

    Features theo Gold Schema:
      fact_vaccination      → vaccination_rate      [0-1]
      fact_covid_cases      → new_confirmed_7d_avg  [xu hướng 7 ngày — predictor chính]
      fact_healthcare_system → testing_rate, new_intensive_care_patients
      fact_social_behavior  → search_trends_anosmia [early COVID signal]
      dim_location          → elderly_pct           [risk profile]

    Algorithms:
      - RandomForestRegressor  (ensemble, handles non-linearity)
      - XGBRegressor           (gradient boosting, tốt cho tabular time-series)
    """
    set_mlflow_env()
    mlflow.set_experiment("auto_healthcare_forecast")

    # ── Tải dữ liệu từ Silver Lake (feature engineering đã thực hiện trong ml_data_gold) ─
    df = load_healthcare_data()
    context.log.info(
        f"[Healthcare] Silver Lake: {len(df):,} rows | "
        f"{df['location_key'].nunique()} quốc gia | "
        f"{df['date'].min().date()} → {df['date'].max().date()}"
    )
    if df.empty:
        raise ValueError(
            "Không có dữ liệu Healthcare từ Silver Lake! "
            "Hãy chắc chắn silver_covid_data đã được materialized."
        )

    # ── Features theo Gold Schema ──────────────────────────────────────────────
    all_feature_cols = [
        "vaccination_rate",             # fact_vaccination — tiêm chủng chuẩn hóa
        "new_confirmed_7d_avg",         # fact_covid_cases — xu hướng hiện tại (quan trọng nhất!)
        "testing_rate",                 # fact_healthcare_system — độ bao phủ xét nghiệm
        "elderly_pct",                  # dim_location — rủi ro dân số già
        "icu_rate_per_1m",              # fact_healthcare_system — ICU/1M dân (normalized)
        "search_trends_anosmia",        # fact_social_behavior — early warning signal
    ]
    feature_cols = [
        c for c in all_feature_cols
        if c in df.columns
    ]
    if not feature_cols:
        raise ValueError(f"Tất cả healthcare features zero-variance: {all_feature_cols}")

    dropped = set(all_feature_cols) - set(feature_cols)
    if dropped:
        context.log.warning(f"[Healthcare] Bỏ features thiếu trong DB: {dropped}")
    context.log.info(f"[Healthcare] Features hợp lệ: {feature_cols}")

    # Target: incidence_rate (per 100k) được shift 14 ngày bởi make_supervised_shift
    X, y, dates = make_supervised_shift(
        df,
        group_col="location_key",
        date_col="date",
        target_col="incidence_rate",   # MỚI: ca/100k thay vì số tuyệt đối
        horizon_days=14,
        feature_cols=feature_cols,
    )
    context.log.info(f"[Healthcare] X.shape={X.shape} | y.shape={y.shape}")
    if X.shape[0] == 0:
        raise ValueError(
            "Không tạo được training set! make_supervised_shift trả về 0 rows."
        )

    split = time_holdout_split(X, y, dates, test_days=30)
    context.log.info(
        f"[Healthcare] Train: {len(split.X_train):,} | Test: {len(split.X_test):,}"
    )

    # ── Huấn luyện & Log MLflow ────────────────────────────────────────────────
    algorithms = {
        "RandomForest": RandomForestRegressor(
            n_estimators=100, random_state=42, n_jobs=-1
        ),
        "XGBoost": XGBRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=6,
            random_state=42, n_jobs=-1
        ),
    }

    best_rmse, best_run_id, best_algo = float("inf"), None, None

    for algo_name, estimator in algorithms.items():
        with mlflow.start_run(run_name=f"healthcare_{algo_name}_incidence_14d") as run:
            model = build_pipeline(estimator)
            model.fit(split.X_train, split.y_train)
            metrics = regression_metrics(split.y_test, model.predict(split.X_test))

            # ── Cross-Validation (TimeSeriesSplit k=3) ──
            cv_metrics = cross_val_time_series(model, split.X_train, split.y_train, n_splits=3)

            # ── Naive Mean Baseline ──
            baseline_metrics = naive_mean_baseline(split.y_train, split.y_test)

            mlflow.log_params({
                "algorithm":    algo_name,
                "target":       "incidence_rate_per100k_+14d",
                "horizon_days": 14,
                "features":     str(feature_cols),
                "data_tier":    "silver",
                "data_source":  "s3://silver-lake/covid_cleaned/",
                "train_rows":   len(split.X_train),
                "test_rows":    len(split.X_test),
            })
            mlflow.log_metrics(metrics)
            mlflow.log_metrics(cv_metrics)
            mlflow.log_metrics(baseline_metrics)
            mlflow.sklearn.log_model(
                model,
                artifact_path="model",
                input_example=split.X_train.head(3),
            )
            context.log.info(
                f"[Healthcare] {algo_name}: RMSE={metrics['rmse']:.4f} | "
                f"MAE={metrics['mae']:.4f} | R²={metrics['r2']:.4f} | "
                f"CV_RMSE={cv_metrics['cv_rmse_mean']:.4f}±{cv_metrics['cv_rmse_std']:.4f} | "
                f"Baseline_RMSE={baseline_metrics['baseline_rmse']:.4f}"
            )

            if metrics["rmse"] < best_rmse:
                best_rmse   = metrics["rmse"]
                best_run_id = run.info.run_id
                best_algo   = algo_name

    # ── Đăng ký model tốt nhất ────────────────────────────────────────────────
    register_best_model(best_run_id, best_rmse, "Healthcare_Covid_Model")
    context.log.info(
        f"[Healthcare] ✅ Model tốt nhất: {best_algo} | RMSE={best_rmse:.4f} → Production"
    )

    return Output(
        value={"best_algo": best_algo, "best_rmse": best_rmse, "run_id": best_run_id},
        metadata={
            "Best_Algorithm": MetadataValue.text(best_algo),
            "RMSE":           MetadataValue.float(best_rmse),
            "Features":       MetadataValue.text(str(feature_cols)),
            "Target":         MetadataValue.text("incidence_rate_per100k_14d"),
            "Data_Tier":      MetadataValue.text("silver"),
            "Rows_Trained":   MetadataValue.int(len(split.X_train)),
        },
    )


# ── Asset 2: Đánh giá Hiệu quả Chính sách (Policy Effectiveness) ──────────────
@asset(deps=["silver_covid_data"], group_name="mlflow")
def auto_train_policy_effectiveness(context):
    """
    Bài toán: Đánh giá tác động của chính sách giãn cách đến tốc độ lây lan COVID-19.
    Target: growth_rate = (new_confirmed[t+14] - new_confirmed[t]) / new_confirmed[t]
            growth_rate < 0 → dịch giảm → chính sách hiệu quả

    Nguồn dữ liệu: PostgreSQL (covid_optimized đã fix OJM)
    Cấp phân tích:  Quốc gia (location_key 2 ký tự)

    Features theo Gold Schema (fact_policy_impact + fact_vaccination):
      - school_closing              (0-3) Oxford Index
      - workplace_closing           (0-3) Oxford Index
      - stay_at_home_requirements   (0-3) Oxford Index — MỚI
      - stringency_index            (0-100) Oxford composite — MỚI
      - vaccination_rate            (0-1) context tiêm vaccine — MỚI
      [REMOVED] mobility_retail_and_recreation — outcome của policy, không phải input

    Algorithms:
      - LinearRegression      (baseline, interpretable)
      - GradientBoosting      (non-linear, captures interaction effects)
    """
    set_mlflow_env()
    mlflow.set_experiment("auto_policy_effectiveness")

    # ── Tải dữ liệu từ PostgreSQL (feature engineering trong ml_data_gold) ──────
    df = load_policy_data()
    context.log.info(
        f"[Policy] PostgreSQL: {len(df):,} rows | "
        f"{df['location_key'].nunique()} quốc gia | "
        f"{df['date'].min().date()} → {df['date'].max().date()}"
    )
    if df.empty:
        raise ValueError(
            "Không có dữ liệu Policy từ PostgreSQL! "
            "Hãy chắc chắn fix_policy_merge.py đã được chạy."
        )

    # ── Features theo Gold Schema ──────────────────────────────────────────────
    # ── Feature Columns theo Algorithm ──
    # LINEAR: chỉ dùng stringency_index (composite) + vaccination_rate
    #   → tránh Multicollinearity vì stringency = f(school + workplace + stayhome + ...)
    # GradientBoosting: dùng full 5 features (tree không bị ảnh hưởng bởi multicollinearity)
    feature_cols_linear = [
        "stringency_index",          # Tổng hợp đủ signal, không trùng lặp
        "vaccination_rate",
    ]
    feature_cols_tree = [
        "school_closing",
        "workplace_closing",
        "stay_at_home_requirements",
        "stringency_index",
        "vaccination_rate",
    ]

    # ── Huấn luyện & Log MLflow ──────────────────────────────────────────
    algorithms = {
        "LinearRegression": (LinearRegression(), feature_cols_linear),
        "GradientBoosting": (GradientBoostingRegressor(
            n_estimators=100, learning_rate=0.1, max_depth=4, random_state=42
        ), feature_cols_tree),
    }

    best_rmse, best_run_id, best_algo = float("inf"), None, None

    for algo_name, (estimator, feature_cols) in algorithms.items():
        # Kiểm tra features hợp lệ với data hiện có
        valid_cols = [c for c in feature_cols if c in df.columns]
        if not valid_cols:
            context.log.warning(f"[Policy] {algo_name}: không có feature nào hợp lệ, bỏ qua.")
            continue

        split = time_holdout_split(*make_growth_rate_target(
            df,
            group_col="location_key",
            date_col="date",
            base_col="new_confirmed",
            horizon_days=14,
            feature_cols=valid_cols,
        )[0:3], test_days=30)

        model = build_pipeline(estimator)
        with mlflow.start_run(run_name=f"policy_{algo_name}_v2_14d") as run:
            model.fit(split.X_train, split.y_train)
            metrics = regression_metrics(split.y_test, model.predict(split.X_test))

            # ── Cross-Validation (TimeSeriesSplit k=3) ──
            cv_metrics = cross_val_time_series(model, split.X_train, split.y_train, n_splits=3)

            # ── Naive Mean Baseline ──
            baseline_metrics = naive_mean_baseline(split.y_train, split.y_test)

            mlflow.log_params({
                "algorithm":    algo_name,
                "target":       "confirmed_growth_rate_+14d",
                "horizon_days": 14,
                "features":     str(feature_cols),
                "data_tier":    "postgresql",
                "data_source":  "covid_optimized (OJM fixed)",
                "train_rows":   len(split.X_train),
                "test_rows":    len(split.X_test),
            })
            mlflow.log_metrics(metrics)
            mlflow.log_metrics(cv_metrics)
            mlflow.log_metrics(baseline_metrics)
            mlflow.sklearn.log_model(
                model,
                artifact_path="model",
                input_example=split.X_train.head(3),
            )
            context.log.info(
                f"[Policy] {algo_name}: RMSE={metrics['rmse']:.4f} | "
                f"MAE={metrics['mae']:.4f} | R²={metrics['r2']:.4f} | "
                f"CV_RMSE={cv_metrics['cv_rmse_mean']:.4f}±{cv_metrics['cv_rmse_std']:.4f} | "
                f"Baseline_RMSE={baseline_metrics['baseline_rmse']:.4f}"
            )

            if metrics["rmse"] < best_rmse:
                best_rmse   = metrics["rmse"]
                best_run_id = run.info.run_id
                best_algo   = algo_name

    # ── Đăng ký model tốt nhất ────────────────────────────────────────────────
    register_best_model(best_run_id, best_rmse, "Policy_Covid_Model")
    context.log.info(
        f"[Policy] ✅ Model tốt nhất: {best_algo} | RMSE={best_rmse:.4f} → Production"
    )

    return Output(
        value={"best_algo": best_algo, "best_rmse": best_rmse, "run_id": best_run_id},
        metadata={
            "Best_Algorithm": MetadataValue.text(best_algo),
            "RMSE":           MetadataValue.float(best_rmse),
            "Features":       MetadataValue.text(str(feature_cols_tree)),
            "Data_Tier":      MetadataValue.text("postgresql"),
            "Rows_Trained":   MetadataValue.int(len(split.X_train)),
        },
    )
