from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

@dataclass(frozen=True)
class Split:
    X_train: pd.DataFrame
    y_train: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series

def time_holdout_split(
    X: pd.DataFrame,
    y: pd.Series,
    dates: pd.Series,
    *,
    test_days: int = 30,
) -> Split:
    d = pd.to_datetime(dates, errors="coerce")
    cutoff = d.max() - pd.Timedelta(days=int(test_days))
    train_mask = d <= cutoff
    test_mask = ~train_mask

    if train_mask.sum() < 50 or test_mask.sum() < 20:
        idx = int(len(X) * 0.8)
        return Split(
            X_train=X.iloc[:idx],
            y_train=y.iloc[:idx],
            X_test=X.iloc[idx:],
            y_test=y.iloc[idx:],
        )

    return Split(
        X_train=X.loc[train_mask],
        y_train=y.loc[train_mask],
        X_test=X.loc[test_mask],
        y_test=y.loc[test_mask],
    )

def regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr)))
    mae = float(mean_absolute_error(y_true_arr, y_pred_arr))
    r2 = float(r2_score(y_true_arr, y_pred_arr))
    return {"rmse": rmse, "mae": mae, "r2": r2}

def make_supervised_shift(
    df: pd.DataFrame,
    *,
    group_col: str,
    date_col: str,
    target_col: str,
    horizon_days: int,
    feature_cols: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    required = [group_col, date_col, target_col, *feature_cols]
    work = df[required].copy()
    work = work.dropna(subset=[group_col, date_col])
    work = work.sort_values([group_col, date_col])

    y = work.groupby(group_col, sort=False)[target_col].shift(-horizon_days)
    X = work[feature_cols]
    dates = work[date_col]

    mask = y.notna()
    return (
        X.loc[mask].reset_index(drop=True),
        y.loc[mask].reset_index(drop=True),
        dates.loc[mask].reset_index(drop=True),
    )

def make_growth_rate_target(
    df: pd.DataFrame,
    *,
    group_col: str,
    date_col: str,
    base_col: str,
    horizon_days: int,
    feature_cols: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    required = [group_col, date_col, base_col, *feature_cols]
    work = df[required].copy()
    work = work.dropna(subset=[group_col, date_col])
    work = work.sort_values([group_col, date_col])

    future = work.groupby(group_col, sort=False)[base_col].shift(-horizon_days)
    now = work[base_col]
    dates = work[date_col]

    denom = np.maximum(now.to_numpy(dtype=float), 1.0)
    y = (future.to_numpy(dtype=float) - now.to_numpy(dtype=float)) / denom
    y = pd.Series(y, index=work.index, name=f"{base_col}_growth_rate_{horizon_days}d")

    mask = future.notna()
    X = work.loc[mask, feature_cols]
    return X.reset_index(drop=True), y.loc[mask].reset_index(drop=True), dates.loc[mask].reset_index(drop=True)


def cross_val_time_series(
    model,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    n_splits: int = 3,
) -> dict[str, float]:
    """
    Cross-validation với TimeSeriesSplit (train trước - test sau, không random).
    Chạy trên tập train để ước lượng variance của metrics qua nhiều cutoff.
    """
    if len(X) < n_splits * 20:
        return {
            "cv_rmse_mean": float("nan"),
            "cv_rmse_std":  float("nan"),
            "cv_r2_mean":   float("nan"),
            "cv_r2_std":    float("nan"),
        }

    tscv = TimeSeriesSplit(n_splits=n_splits)
    rmse_list, r2_list = [], []

    X_arr = X.reset_index(drop=True)
    y_arr = y.reset_index(drop=True)

    for train_idx, val_idx in tscv.split(X_arr):
        X_tr, X_val = X_arr.iloc[train_idx], X_arr.iloc[val_idx]
        y_tr, y_val = y_arr.iloc[train_idx], y_arr.iloc[val_idx]

        from sklearn.base import clone
        m = clone(model)
        m.fit(X_tr, y_tr)
        preds = m.predict(X_val)

        metrics = regression_metrics(y_val, preds)
        rmse_list.append(metrics["rmse"])
        r2_list.append(metrics["r2"])

    return {
        "cv_rmse_mean": float(np.mean(rmse_list)),
        "cv_rmse_std":  float(np.std(rmse_list)),
        "cv_r2_mean":   float(np.mean(r2_list)),
        "cv_r2_std":    float(np.std(r2_list)),
    }


def naive_mean_baseline(
    y_train: pd.Series,
    y_test: pd.Series,
) -> dict[str, float]:
    """
    Naive Baseline: predict bằng mean(y_train) cho toàn bộ test set.
    Mức tối thiểu mà mọi model ML phải vượt qua.
    """
    mean_pred = float(np.mean(y_train))
    preds = np.full(len(y_test), mean_pred)
    metrics = regression_metrics(y_test, preds)
    return {
        "baseline_rmse": metrics["rmse"],
        "baseline_mae":  metrics["mae"],
        "baseline_r2":   metrics["r2"],
    }
