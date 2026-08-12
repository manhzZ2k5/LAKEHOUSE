from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
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
    if len(X) != len(y) or len(X) != len(dates):
        raise ValueError("X, y, and dates must have the same length.")

    d = pd.to_datetime(dates, errors="coerce")
    if d.isna().any():
        raise ValueError("dates contains NaT after coercion.")

    cutoff = d.max() - pd.Timedelta(days=int(test_days))
    train_mask = d <= cutoff
    test_mask = ~train_mask

    if train_mask.sum() < 50 or test_mask.sum() < 20:
        # Fallback: 80/20 split if the time window is too short.
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


def cross_val_time_series(
    model,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    n_splits: int = 3,
) -> dict[str, float]:
    """
    Cross-validation với TimeSeriesSplit (không random, luôn train trước - test sau).

    Dùng để ước lượng variance của model metrics qua nhiều cutoff khác nhau.
    Không thay thế holdout split — chạy song song để bổ sung thông tin.

    Args:
        model: sklearn-compatible Pipeline (chưa fit).
        X, y: Full training features & labels (chỉ dùng phần train của holdout split).
        n_splits: Số fold, mặc định 3.

    Returns:
        dict với cv_rmse_mean, cv_rmse_std, cv_r2_mean, cv_r2_std
    """
    if len(X) < n_splits * 20:
        # Không đủ data để CV có ý nghĩa
        return {
            "cv_rmse_mean": -1.0,
            "cv_rmse_std":  -1.0,
            "cv_r2_mean":   -1.0,
            "cv_r2_std":    -1.0,
        }

    tscv = TimeSeriesSplit(n_splits=n_splits)
    rmse_list, r2_list = [], []

    X_arr = X.reset_index(drop=True)
    y_arr = y.reset_index(drop=True)

    for train_idx, val_idx in tscv.split(X_arr):
        X_tr, X_val = X_arr.iloc[train_idx], X_arr.iloc[val_idx]
        y_tr, y_val = y_arr.iloc[train_idx], y_arr.iloc[val_idx]

        # Clone-fit để không làm ô nhiễm model gốc
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
    Naive Baseline: dự đoán bằng mean của tập train cho toàn bộ tập test.

    Đây là mức tối thiểu mà bất kỳ model ML nào cũng phải vượt qua.
    Nếu model không tốt hơn baseline → model chưa học được gì có ích.

    Returns:
        dict với baseline_rmse, baseline_mae, baseline_r2
    """
    mean_pred = float(np.mean(y_train))
    preds = np.full(len(y_test), mean_pred)
    metrics = regression_metrics(y_test, preds)
    return {
        "baseline_rmse": metrics["rmse"],
        "baseline_mae":  metrics["mae"],
        "baseline_r2":   metrics["r2"],
    }
