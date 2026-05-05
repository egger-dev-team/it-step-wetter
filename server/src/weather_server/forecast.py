"""Runtime forecasting service.

Loads the joblib model bundle produced by ``scripts/train_forecast.py`` and
turns recent station readings into a 3-class precipitation forecast for the
next 1..24 hours.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd


WIND_DIRECTION_DEGREES = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
    "UNKNOWN": 0.0,
}

MIN_HISTORY_HOURS = 6


class ForecastError(Exception):
    """Raised when a forecast cannot be produced."""


@dataclass
class HorizonPrediction:
    horizon_hours: int
    label: str
    probabilities: dict[str, float]


class Forecaster:
    """Lazy-loading wrapper around the joblib model bundle."""

    def __init__(self, model_path: Path | str) -> None:
        self._model_path = Path(model_path)
        self._bundle: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if self._bundle is not None:
            return self._bundle
        with self._lock:
            if self._bundle is not None:
                return self._bundle
            if not self._model_path.exists():
                raise ForecastError(
                    f"forecast model not found at {self._model_path}"
                )
            self._bundle = joblib.load(self._model_path)
        return self._bundle

    @property
    def is_available(self) -> bool:
        return self._model_path.exists()

    def metadata(self) -> dict[str, Any]:
        bundle = self._load()
        return {
            "version": bundle.get("version"),
            "horizons": bundle.get("horizons"),
            "class_labels": bundle.get("class_labels"),
            "metadata": bundle.get("metadata", {}),
        }

    def predict(self, rows: Sequence[dict[str, Any]]) -> list[HorizonPrediction]:
        bundle = self._load()
        feature_vec = _build_feature_vector(
            rows, bundle["feature_list"]
        )
        class_labels: list[str] = bundle["class_labels"]
        results: list[HorizonPrediction] = []
        X = feature_vec.reshape(1, -1)
        for h in bundle["horizons"]:
            clf = bundle["models_by_horizon"][h]
            proba = clf.predict_proba(X)[0]
            # Map classifier classes_ back onto the canonical label list.
            probs_by_label = {label: 0.0 for label in class_labels}
            for cls_idx, prob in zip(clf.classes_, proba):
                probs_by_label[class_labels[int(cls_idx)]] = float(prob)
            best_label = max(probs_by_label, key=probs_by_label.get)
            results.append(HorizonPrediction(
                horizon_hours=int(h),
                label=best_label,
                probabilities=probs_by_label,
            ))
        return results


def _wind_to_degrees(direction: str | None) -> float:
    if direction is None:
        return 0.0
    return WIND_DIRECTION_DEGREES.get(direction.strip().upper(), 0.0)


def _build_feature_vector(
    rows: Sequence[dict[str, Any]],
    feature_list: Sequence[str],
) -> np.ndarray:
    """Replicate the training-time feature recipe from recent station rows.

    ``rows`` must be ordered oldest -> newest and span at least
    ``MIN_HISTORY_HOURS`` hours of data.
    """
    if not rows:
        raise ForecastError("no station readings available")

    df = pd.DataFrame(list(rows))
    if "received_at" not in df.columns:
        raise ForecastError("station rows missing received_at")
    df["received_at"] = pd.to_datetime(df["received_at"], utc=True)
    df = df.sort_values("received_at").reset_index(drop=True)

    span_hours = (df["received_at"].iloc[-1]
                  - df["received_at"].iloc[0]).total_seconds() / 3600.0
    if span_hours < MIN_HISTORY_HOURS - 0.5:
        raise ForecastError(
            f"need at least {MIN_HISTORY_HOURS}h of station history; "
            f"got {span_hours:.1f}h"
        )

    df["wind_deg"] = df["windrichtung"].apply(_wind_to_degrees)

    # Resample to hourly to match training cadence; mean for state variables,
    # sum for precipitation. Use the last MIN_HISTORY_HOURS+1 hours.
    df_idx = df.set_index("received_at")
    agg = df_idx.resample("1h").agg({
        "temperatur": "mean",
        "luftfeuchtigkeit": "mean",
        "luftdruck": "mean",
        "niederschlag": "sum",
        "windgeschwindigkeit": "mean",
        "wind_deg": "mean",
        "helligkeit": "mean",
    }).dropna()

    if len(agg) < MIN_HISTORY_HOURS + 1:
        raise ForecastError(
            f"need at least {MIN_HISTORY_HOURS + 1} hourly samples; "
            f"got {len(agg)}"
        )

    last = agg.iloc[-1]
    rad = np.deg2rad(float(last["wind_deg"]))
    now_ts = agg.index[-1].to_pydatetime().astimezone(timezone.utc)

    features = {
        "temperatur": float(last["temperatur"]),
        "luftfeuchtigkeit": float(last["luftfeuchtigkeit"]),
        "luftdruck": float(last["luftdruck"]),
        "niederschlag": float(last["niederschlag"]),
        "windgeschwindigkeit": float(last["windgeschwindigkeit"]),
        "wind_sin": float(np.sin(rad)),
        "wind_cos": float(np.cos(rad)),
        "helligkeit": float(last["helligkeit"]),
        "press_diff_3h": float(last["luftdruck"]
                               - agg["luftdruck"].iloc[-4]),
        "press_diff_6h": float(last["luftdruck"]
                               - agg["luftdruck"].iloc[-7]),
        "temp_diff_3h": float(last["temperatur"]
                              - agg["temperatur"].iloc[-4]),
        "temp_diff_6h": float(last["temperatur"]
                              - agg["temperatur"].iloc[-7]),
        "precip_3h": float(agg["niederschlag"].iloc[-3:].sum()),
        "precip_6h": float(agg["niederschlag"].iloc[-6:].sum()),
        "hour_sin": float(np.sin(2 * np.pi * now_ts.hour / 24.0)),
        "hour_cos": float(np.cos(2 * np.pi * now_ts.hour / 24.0)),
        "doy_sin": float(np.sin(2 * np.pi
                                * now_ts.timetuple().tm_yday / 366.0)),
        "doy_cos": float(np.cos(2 * np.pi
                                * now_ts.timetuple().tm_yday / 366.0)),
    }
    try:
        return np.array([features[name] for name in feature_list],
                        dtype=float)
    except KeyError as exc:
        raise ForecastError(
            f"feature recipe out of sync with model: missing {exc}"
        ) from None


def reference_time_utc() -> datetime:
    return datetime.now(tz=timezone.utc)
