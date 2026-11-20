
"""Dataset-label vital-sign screening for the BioTwin prototype.

This model reproduces the Kaggle dataset's High Risk / Low Risk label from
vital-sign features. The source label is threshold-derived, not a clinical
outcome. It must never be presented as a diagnosis or disease probability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    ROOT / "data" / "biotwin" / "models" / "kaggle_vital_risk.joblib"
)

METRICS_PATH = (
    ROOT / "data" / "biotwin" / "models" / "kaggle_vital_risk_metrics.json"
)

FEATURES = [
    "heart_rate_bpm",
    "respiratory_rate_bpm",
    "body_temperature_c",
    "spo2_pct",
    "systolic_bp_mmhg",
    "diastolic_bp_mmhg",
    "derived_bmi",
]

# Numeric label mapping used during model training.
RISK_LABELS = {
    0: "Low Risk",
    1: "High Risk",
}


def assess_dataset_vital_risk(
    reading: dict[str, Any],
) -> dict[str, Any]:
    """Return dataset-label screening from the trained Kaggle model.

    All seven model features are required.

    BMI can be supplied directly as derived_bmi, or calculated
    from weight_kg and height_m when both are available.

    Skin temperature is deliberately excluded because it is not
    equivalent to the body-temperature field in the source dataset.
    """

    values = dict(reading)

    # Skin temperature cannot substitute for body temperature.
    if str(values.get("temperature_type", "")).lower() == "skin":
        values["body_temperature_c"] = None

    # Calculate BMI only when actual weight and height are supplied.
    if values.get("derived_bmi") is None:
        weight = values.get("weight_kg")
        height = values.get("height_m")

        try:
            if weight is not None and height is not None:
                weight = float(weight)
                height = float(height)

                if weight > 0 and height > 0:
                    values["derived_bmi"] = weight / (height ** 2)

        except (TypeError, ValueError, ZeroDivisionError):
            values["derived_bmi"] = None

    # Check all required model features.
    present = [
        key for key in FEATURES
        if values.get(key) is not None
    ]

    missing = [
        key for key in FEATURES
        if values.get(key) is None
    ]

    if missing:
        return {
            "status": "insufficient_vitals",
            "label_code": None,
            "label": None,
            "features_used": present,
            "missing_features": missing,
            "label_mapping": {
                "0": "Low Risk",
                "1": "High Risk",
            },
            "clinical_diagnosis": False,
            "notice": (
                "The trained Kaggle model requires all seven features, "
                "including BMI. Missing values are not assumed normal. "
                "Provide weight and height to calculate BMI, or supply "
                "derived_bmi directly."
            ),
        }

    # Check model availability.
    if not MODEL_PATH.exists():
        return {
            "status": "dataset_not_downloaded_or_model_not_trained",
            "label_code": None,
            "label": None,
            "features_used": present,
            "missing_features": [],
            "clinical_diagnosis": False,
            "notice": (
                "Kaggle dataset model is not active. Download the "
                "licensed dataset and run the training script. "
                "No dataset prediction was fabricated."
            ),
        }

    try:
        import joblib

        saved = joblib.load(MODEL_PATH)

        # Support tuned model bundle and earlier plain estimator.
        if isinstance(saved, dict) and "model" in saved:
            model = saved["model"]
            model_features = saved.get(
                "feature_columns",
                FEATURES,
            )
            model_name = saved.get(
                "model_name",
                "trained classifier",
            )
        else:
            model = saved
            model_features = FEATURES
            model_name = "legacy RandomForest baseline"

        # Ensure the model's required features are available.
        missing_model_features = [
            key for key in model_features
            if values.get(key) is None
        ]

        if missing_model_features:
            return {
                "status": "insufficient_vitals",
                "label_code": None,
                "label": None,
                "features_used": present,
                "missing_features": missing_model_features,
                "clinical_diagnosis": False,
                "notice": (
                    "Required features for the saved model are missing."
                ),
            }

        # Build model input in its saved feature order.
        
        import pandas as pd

        row = pd.DataFrame(
            [
                {
                    key: float(values[key])
                    for key in model_features
                }
            ],
            columns=model_features,
        )

        raw_prediction = model.predict(row)[0]

        label_code = int(raw_prediction)

        if label_code not in RISK_LABELS:
            raise ValueError(
                f"Unexpected model label code: {label_code}"
            )

        label_name = RISK_LABELS[label_code]

        return {
            "status": "generated",
            "label_code": label_code,
            "label": label_name,
            "label_mapping": {
                "0": "Low Risk",
                "1": "High Risk",
            },
            "features_used": list(model_features),
            "model_name": model_name,
            "prediction_type": (
                "threshold-derived dataset-label screening"
            ),
            "clinical_diagnosis": False,
            "notice": (
                "This reproduces the Kaggle dataset's "
                "threshold-derived High Risk / Low Risk label. "
                "It is not a diagnosis, disease prediction, "
                "calibrated probability, or clinically validated "
                "worker risk score."
            ),
        }

    except Exception as exc:
        return {
            "status": "model_error",
            "label_code": None,
            "label": None,
            "features_used": present,
            "clinical_diagnosis": False,
            "notice": (
                "Dataset model could not run "
                f"({type(exc).__name__}: {exc}); "
                "independent safety screening remains active."
            ),
        }


def model_status() -> dict[str, Any]:
    """Return trained model availability and saved metrics."""

    if not MODEL_PATH.exists():
        return {
            "status": "not_trained",
            "model_available": False,
            "metrics": None,
            "label_mapping": {
                "0": "Low Risk",
                "1": "High Risk",
            },
        }

    metrics = None

    if METRICS_PATH.exists():
        try:
            metrics = json.loads(
                METRICS_PATH.read_text(encoding="utf-8")
            )
        except Exception:
            metrics = None

    return {
        "status": "ready",
        "model_available": True,
        "metrics": metrics,
        "label_mapping": {
            "0": "Low Risk",
            "1": "High Risk",
        },
    }
