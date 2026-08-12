from __future__ import annotations

import argparse
from datetime import datetime, timezone

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from xgboost import XGBRegressor
from sklearn.ensemble import RandomForestRegressor

from .data_silver import load_healthcare_silver
from .features import make_supervised_shift
from .mlflow_utils import configure_mlflow, write_model_pointer
from .settings import load_settings
from .train_common import regression_metrics, time_holdout_split, cross_val_time_series, naive_mean_baseline


def _build_model(algorithm: str, random_state: int, feature_cols: list[str]) -> Pipeline:
    numeric_features = feature_cols

    if algorithm == "rf":
        estimator = RandomForestRegressor(
            n_estimators=400,
            random_state=random_state,
            n_jobs=-1,
        )
        scaler = "passthrough"
    elif algorithm == "xgb":
        estimator = XGBRegressor(
            n_estimators=800,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=random_state,
            n_jobs=-1,
        )
        scaler = "passthrough"
    else:
        raise ValueError("algorithm must be one of: rf, xgb")

    pre = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", scaler),
                    ]
                ),
                numeric_features,
            )
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline(steps=[("pre", pre), ("model", estimator)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Train + log MLflow for healthcare forecast task.")
    parser.add_argument(
        "--target",
        default="incidence_rate",
        help="Target để dự đoán (Ca nhiễm mới trên 100k dân).",
    )
    parser.add_argument("--horizon-days", type=int, default=14, choices=[7, 14])
    parser.add_argument("--algorithm", choices=["xgb", "rf"], default="xgb")
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--experiment", default="healthcare_forecast")
    parser.add_argument("--model-pointer", default="ml/models/healthcare_latest.json")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD (optional)")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD (optional)")
    parser.add_argument("--limit-rows", type=int, default=None, help="Optional SQL LIMIT")
    args = parser.parse_args()

    settings = load_settings()
    if args.tracking_uri:
        settings = settings.__class__(**{**settings.__dict__, "mlflow_tracking_uri": args.tracking_uri})

    configure_mlflow(settings)
    mlflow.set_experiment(args.experiment)

    feature_cols = [
        "vaccination_rate",
        "new_confirmed_7d_avg",
        "testing_rate",
        "elderly_pct",
        "icu_rate_per_1m",          # Đã normalize: ICU / 1M dân (thay cho số tuyệt đối)
        "search_trends_anosmia",
    ]
    dataset = load_healthcare_silver(
        settings,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    df = dataset.df

    X, y, dates = make_supervised_shift(
        df,
        group_col="location_key",
        date_col="date",
        target_col=args.target,
        horizon_days=int(args.horizon_days),
        feature_cols=feature_cols,
    )

    split = time_holdout_split(X, y, dates, test_days=int(args.test_days))
    model = _build_model(args.algorithm, random_state=int(args.random_state), feature_cols=feature_cols)

    with mlflow.start_run(run_name=f"{args.algorithm}_{args.target}_{args.horizon_days}d") as run:
        mlflow.set_tags(
            {
                "task": "healthcare_forecast",
                "target": args.target,
                "horizon_days": int(args.horizon_days),
                "algorithm": args.algorithm,
                "data_source": dataset.source,
            }
        )
        mlflow.log_params(
            {
                "feature_cols": ",".join(feature_cols),
                "test_days": int(args.test_days),
                "random_state": int(args.random_state),
            }
        )

        model.fit(split.X_train, split.y_train)
        preds = model.predict(split.X_test)
        metrics = regression_metrics(split.y_test, preds)
        mlflow.log_metrics(metrics)

        # ── Cross-Validation (TimeSeriesSplit k=3) ──
        # Chạy trên tập train để ước lượng variance của metrics
        cv_metrics = cross_val_time_series(model, split.X_train, split.y_train, n_splits=3)
        mlflow.log_metrics(cv_metrics)

        # ── Naive Mean Baseline ──
        # Dự đoán bằng mean(y_train) — mức tối thiểu model phải vượt qua
        baseline_metrics = naive_mean_baseline(split.y_train, split.y_test)
        mlflow.log_metrics(baseline_metrics)

        input_example = split.X_train.head(3)
        mlflow.sklearn.log_model(model, artifact_path="model", input_example=input_example)

        pointer = {
            "task": "healthcare_forecast",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run.info.run_id,
            "model_uri": f"runs:/{run.info.run_id}/model",
            "tracking_uri": settings.mlflow_tracking_uri,
            "target": args.target,
            "horizon_days": int(args.horizon_days),
            "feature_cols": feature_cols,
            "metrics": metrics,
        }
        write_model_pointer(args.model_pointer, pointer)

        print("Run:", run.info.run_id)
        print("Metrics:", metrics)
        print("Model pointer:", args.model_pointer)


if __name__ == "__main__":
    main()
