from __future__ import annotations

import argparse
from datetime import datetime, timezone

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data_silver import load_policy_silver
from .features import make_growth_rate_target
from .mlflow_utils import configure_mlflow, write_model_pointer
from .settings import load_settings
from .train_common import regression_metrics, time_holdout_split, cross_val_time_series, naive_mean_baseline


def _build_model(algorithm: str, feature_cols: list[str]) -> Pipeline:


    if algorithm == "linear":
        estimator = LinearRegression()
        scaler = StandardScaler()
    elif algorithm == "gbrt":
        estimator = HistGradientBoostingRegressor(
            max_depth=6,
            learning_rate=0.05,
            max_iter=600,
            random_state=42,
        )
        scaler = "passthrough"
    else:
        raise ValueError("algorithm must be one of: linear, gbrt")

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
                feature_cols,
            )
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline(steps=[("pre", pre), ("model", estimator)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Train + log MLflow for policy effectiveness task.")
    parser.add_argument("--horizon-days", type=int, default=14, choices=[14])
    parser.add_argument("--algorithm", choices=["linear", "gbrt"], default="gbrt")
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--experiment", default="policy_effectiveness")
    parser.add_argument("--model-pointer", default="ml/models/policy_latest.json")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD (optional)")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD (optional)")
    parser.add_argument("--limit-rows", type=int, default=None, help="Optional SQL LIMIT")
    args = parser.parse_args()

    settings = load_settings()
    if args.tracking_uri:
        settings = settings.__class__(**{**settings.__dict__, "mlflow_tracking_uri": args.tracking_uri})

    configure_mlflow(settings)
    mlflow.set_experiment(args.experiment)

    # ── Feature Columns theo Algorithm ──
    # LINEAR: chỉ dùng stringency_index (composite) + vaccination_rate
    #   → tránh Multicollinearity vì stringency = f(school + workplace + stayhome)
    # GBRT: dùng full 5 features (tree không bị ảnh hưởng bởi multicollinearity)
    if args.algorithm == "linear":
        feature_cols = [
            "stringency_index",    # Tổng hợp đủ signal, không trùng lặp
            "vaccination_rate",    # Context tiêm vaccine
        ]
    else:  # gbrt
        feature_cols = [
            "school_closing",
            "workplace_closing",
            "stay_at_home_requirements",
            "stringency_index",
            "vaccination_rate",
        ]
    dataset = load_policy_silver(
        settings,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    df = dataset.df

    X, y, dates = make_growth_rate_target(
        df,
        group_col="location_key",
        date_col="date",
        base_col="new_confirmed",
        horizon_days=int(args.horizon_days),
        feature_cols=feature_cols,
    )

    split = time_holdout_split(X, y, dates, test_days=int(args.test_days))
    model = _build_model(args.algorithm, feature_cols=feature_cols)

    with mlflow.start_run(run_name=f"{args.algorithm}_growth_{args.horizon_days}d") as run:
        mlflow.set_tags(
            {
                "task": "policy_effectiveness",
                "target": f"new_confirmed_growth_rate_{int(args.horizon_days)}d",
                "horizon_days": int(args.horizon_days),
                "algorithm": args.algorithm,
                "data_source": dataset.source,
            }
        )
        mlflow.log_params(
            {
                "feature_cols": ",".join(feature_cols),
                "test_days": int(args.test_days),
                "target_definition": "(new_confirmed[t+h]-new_confirmed[t])/max(new_confirmed[t],1)",
            }
        )

        model.fit(split.X_train, split.y_train)
        preds = model.predict(split.X_test)
        metrics = regression_metrics(split.y_test, preds)
        mlflow.log_metrics(metrics)

        # ── Cross-Validation (TimeSeriesSplit k=3) ──
        cv_metrics = cross_val_time_series(model, split.X_train, split.y_train, n_splits=3)
        mlflow.log_metrics(cv_metrics)

        # ── Naive Mean Baseline ──
        baseline_metrics = naive_mean_baseline(split.y_train, split.y_test)
        mlflow.log_metrics(baseline_metrics)

        input_example = split.X_train.head(3)
        mlflow.sklearn.log_model(model, artifact_path="model", input_example=input_example)

        pointer = {
            "task": "policy_effectiveness",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run.info.run_id,
            "model_uri": f"runs:/{run.info.run_id}/model",
            "tracking_uri": settings.mlflow_tracking_uri,
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
