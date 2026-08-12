from __future__ import annotations

import numpy as np
import pandas as pd


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
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

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
    """
    Target = (future - now) / max(now, 1).
    This avoids division-by-zero and keeps an interpretable "growth rate" scale.
    """
    required = [group_col, date_col, base_col, *feature_cols]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

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
