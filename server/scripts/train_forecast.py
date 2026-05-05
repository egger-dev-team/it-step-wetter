"""Train a 24h precipitation-type forecaster from Open-Meteo archive data.

Builds 3-class targets (none / rain / snow) at horizons +1, +3, +6, +12, +24 h
from hourly history data, fits one classifier per horizon, and saves a single
joblib bundle that can be loaded by the API at inference time.

Usage:

    python scripts/train_forecast.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)


HORIZONS = [1, 3, 6, 12, 24]
CLASS_LABELS = ["none", "rain", "snow"]

PRECIP_THRESHOLD_MM = 0.1  # hourly precipitation considered "precipitating"
SNOW_TEMP_C = 1.0          # fallback snow threshold when snowfall not reported

FEATURE_COLUMNS = [
    "temperatur",
    "luftfeuchtigkeit",
    "luftdruck",
    "niederschlag",
    "windgeschwindigkeit",
    "wind_sin",
    "wind_cos",
    "helligkeit",
    "press_diff_3h",
    "press_diff_6h",
    "temp_diff_3h",
    "temp_diff_6h",
    "precip_3h",
    "precip_6h",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
]


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=here / "data" / "history"
        / "openmeteo_47.5217_12.4342_2016-01-01_2025-12-31.csv",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=here / "data" / "models" / "forecast_v1.joblib",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=here / "data" / "models" / "forecast_v1.metrics.json",
    )
    parser.add_argument(
        "--validation-months",
        type=int,
        default=12,
        help="Most recent N months held out for validation.",
    )
    return parser.parse_args()


def label_precip(precip_mm: float, snowfall_cm: float, temp_c: float) -> int:
    """Return class index: 0=none, 1=rain, 2=snow."""
    if precip_mm < PRECIP_THRESHOLD_MM:
        return 0
    if snowfall_cm and snowfall_cm > 0.0:
        return 2
    if temp_c <= SNOW_TEMP_C:
        return 2
    return 1


# Map Open-Meteo wind direction in degrees to a 16-point compass code, then
# encode via sin/cos of the original degrees (preferred -- preserves order).
def build_features_and_targets(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)

    # Rename to the station's German names so the same recipe works at runtime.
    df = df.rename(columns={
        "temperature_2m": "temperatur",
        "relative_humidity_2m": "luftfeuchtigkeit",
        "surface_pressure": "luftdruck",
        "precipitation": "niederschlag",
        "wind_speed_10m": "windgeschwindigkeit",
        "wind_direction_10m": "wind_deg",
        "shortwave_radiation": "helligkeit",
    })

    # Encode wind direction in degrees as sin/cos.
    rad = np.deg2rad(df["wind_deg"].fillna(0.0))
    df["wind_sin"] = np.sin(rad)
    df["wind_cos"] = np.cos(rad)

    # Tendencies and rolling sums.
    df["press_diff_3h"] = df["luftdruck"] - df["luftdruck"].shift(3)
    df["press_diff_6h"] = df["luftdruck"] - df["luftdruck"].shift(6)
    df["temp_diff_3h"] = df["temperatur"] - df["temperatur"].shift(3)
    df["temp_diff_6h"] = df["temperatur"] - df["temperatur"].shift(6)
    df["precip_3h"] = (df["niederschlag"]
                       .rolling(window=3, min_periods=1).sum())
    df["precip_6h"] = (df["niederschlag"]
                       .rolling(window=6, min_periods=1).sum())

    # Calendar features.
    hour = df["time"].dt.hour
    doy = df["time"].dt.dayofyear
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    df["doy_sin"] = np.sin(2 * np.pi * doy / 366.0)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 366.0)

    # Targets at each horizon: shift labels backwards in time so row t carries
    # the label for time t+h.
    snowfall = df.get("snowfall", pd.Series(0.0, index=df.index)).fillna(0.0)
    labels_now = [
        label_precip(p, s, t)
        for p, s, t in zip(
            df["niederschlag"].fillna(0.0).to_numpy(),
            snowfall.to_numpy(),
            df["temperatur"].fillna(0.0).to_numpy(),
        )
    ]
    df["label_now"] = labels_now
    for h in HORIZONS:
        df[f"y_{h}h"] = df["label_now"].shift(-h)

    return df


def train_one(model_data: pd.DataFrame, horizon: int) -> tuple[
        HistGradientBoostingClassifier, dict, np.ndarray]:
    target_col = f"y_{horizon}h"
    cols = FEATURE_COLUMNS + [target_col]
    df = model_data.dropna(subset=cols).copy()
    df[target_col] = df[target_col].astype(int)

    split_idx = df["__split_idx"].to_numpy()
    train_mask = split_idx == 0
    val_mask = split_idx == 1

    X_train = df.loc[train_mask, FEATURE_COLUMNS].to_numpy()
    y_train = df.loc[train_mask, target_col].to_numpy()
    X_val = df.loc[val_mask, FEATURE_COLUMNS].to_numpy()
    y_val = df.loc[val_mask, target_col].to_numpy()

    clf = HistGradientBoostingClassifier(
        max_iter=400,
        learning_rate=0.05,
        max_depth=None,
        max_leaf_nodes=63,
        l2_regularization=1.0,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_val)

    metrics = {
        "horizon_hours": horizon,
        "n_train": int(train_mask.sum()),
        "n_val": int(val_mask.sum()),
        "accuracy": float((y_pred == y_val).mean()),
        "macro_f1": float(f1_score(y_val, y_pred, average="macro",
                                   labels=[0, 1, 2], zero_division=0)),
        "majority_class_baseline_acc": float(
            (y_val == int(np.bincount(y_train, minlength=3).argmax())).mean()
        ),
        "classification_report": classification_report(
            y_val, y_pred, labels=[0, 1, 2], target_names=CLASS_LABELS,
            output_dict=True, zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(
            y_val, y_pred, labels=[0, 1, 2]
        ).tolist(),
        "class_distribution_train": np.bincount(
            y_train, minlength=3).tolist(),
        "class_distribution_val": np.bincount(
            y_val, minlength=3).tolist(),
    }
    return clf, metrics, clf.classes_


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    print(f"Loading {args.input}")
    raw = pd.read_csv(args.input)
    print(f"  {len(raw):,} rows")

    feats = build_features_and_targets(raw)

    # Time-based split: last N months used for validation.
    cutoff = (feats["time"].max()
              - pd.DateOffset(months=args.validation_months))
    feats["__split_idx"] = (feats["time"] >= cutoff).astype(int)
    print(f"Validation cutoff: {cutoff.isoformat()}")

    models: dict[int, HistGradientBoostingClassifier] = {}
    all_metrics: dict = {"horizons": {}}
    for h in HORIZONS:
        print(f"\nTraining horizon +{h}h ...")
        clf, metrics, classes = train_one(feats, h)
        models[h] = clf
        all_metrics["horizons"][str(h)] = metrics
        print(f"  acc={metrics['accuracy']:.3f}  "
              f"macro_f1={metrics['macro_f1']:.3f}  "
              f"baseline_acc={metrics['majority_class_baseline_acc']:.3f}  "
              f"n_val={metrics['n_val']}")

    bundle = {
        "version": 1,
        "horizons": HORIZONS,
        "feature_list": FEATURE_COLUMNS,
        "class_labels": CLASS_LABELS,
        "models_by_horizon": models,
        "metadata": {
            "input": str(args.input),
            "validation_cutoff": cutoff.isoformat(),
            "n_rows": len(feats),
            "precip_threshold_mm": PRECIP_THRESHOLD_MM,
            "snow_temp_c": SNOW_TEMP_C,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out, compress=3)
    print(f"\nSaved model bundle to {args.out}")

    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(all_metrics, indent=2))
    print(f"Saved metrics to {args.metrics}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
