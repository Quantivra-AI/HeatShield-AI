
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.dummy import DummyRegressor

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_FILE = BACKEND_DIR / "data" / "biotwin" / "processed" / "prospie_cleaned.csv"
REPORT_DIR = BACKEND_DIR / "data" / "biotwin" / "reports"

NUMERIC_FEATURES = [
    "temp",
    "humidity",
    "wind",
    "tamb",
    "age",
    "bodymasskg",
    "heightcm",
    "bodyfat",
    "vo2peakmlkgmin",
    "gradient",
    "speedkm_hr_1",
    "ml_kg_min",
]

CATEGORICAL_FEATURES = [
    "activity_code",
    "solar_present",
    "clothing",
]

TARGET = "corerectal"


def build_experiment_dataset(df):
    required = [
        "participant",
        "condition",
        "workrest",
        TARGET,
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    df["workrest"] = pd.to_numeric(df["workrest"], errors="coerce")
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")

    work = df[
        (df["workrest"] == 1) &
        df[TARGET].notna()
    ].copy()

    available_numeric = [
        col for col in NUMERIC_FEATURES
        if col in work.columns
    ]
    available_categorical = [
        col for col in CATEGORICAL_FEATURES
        if col in work.columns
    ]

    # Aggregate repeated minute-level observations.
    aggregation = {
        TARGET: "mean",
        **{col: "mean" for col in available_numeric},
        **{col: lambda x: (
            x.mode().iloc[0] if not x.mode().empty else np.nan
        ) for col in available_categorical},
    }

    grouped = (
        work.groupby(["participant", "condition"], as_index=False)
        .agg(aggregation)
    )

    return grouped, available_numeric, available_categorical


def build_pipeline(numeric_features, categorical_features, model):
    transformers = []

    if numeric_features:
        numeric_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
        ])
        transformers.append(
            ("numeric", numeric_pipeline, numeric_features)
        )

    if categorical_features:
        categorical_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore")),
        ])
        transformers.append(
            ("categorical", categorical_pipeline, categorical_features)
        )

    preprocessing = ColumnTransformer(transformers)

    return Pipeline([
        ("preprocessing", preprocessing),
        ("model", model),
    ])


def evaluate_model(name, pipeline, X, y, groups, cv):
    predictions = cross_val_predict(
        pipeline,
        X,
        y,
        groups=groups,
        cv=cv,
        n_jobs=-1,
    )

    return {
        "model": name,
        "mae_celsius": float(mean_absolute_error(y, predictions)),
        "rmse_celsius": float(np.sqrt(mean_squared_error(y, predictions))),
        "r2": float(r2_score(y, predictions)),
        "samples": int(len(y)),
        "participants": int(groups.nunique()),
    }, predictions


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_FILE)
    dataset, numeric_features, categorical_features = (
        build_experiment_dataset(df)
    )

    dataset = dataset.dropna(subset=[TARGET]).copy()

    if dataset["participant"].nunique() < 5:
        raise ValueError("Not enough participants for grouped validation.")

    if len(dataset) < 10:
        raise ValueError("Not enough participant-condition samples.")

    groups = dataset["participant"]
    y = dataset[TARGET].astype(float)

    feature_columns = numeric_features + categorical_features
    X = dataset[feature_columns].copy()

    for col in numeric_features:
        X[col] = pd.to_numeric(X[col], errors="coerce")

    for col in categorical_features:
        X[col] = X[col].astype("string")

    cv = GroupKFold(n_splits=5)

    models = [
        (
            "Dummy mean baseline",
            DummyRegressor(strategy="mean"),
        ),
        (
            "Random Forest",
            RandomForestRegressor(
                n_estimators=300,
                max_depth=5,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ]

    results = []
    prediction_output = dataset[
        ["participant", "condition", TARGET]
    ].copy()

    for name, model in models:
        pipeline = build_pipeline(
            numeric_features,
            categorical_features,
            model,
        )

        metrics, predictions = evaluate_model(
            name, pipeline, X, y, groups, cv
        )

        results.append(metrics)
        prediction_output[name] = predictions

    results_df = pd.DataFrame(results)

    dataset.to_csv(
        REPORT_DIR / "prospie_ml_experiment_dataset.csv",
        index=False,
    )
    results_df.to_csv(
        REPORT_DIR / "prospie_ml_baseline_results.csv",
        index=False,
    )
    prediction_output.to_csv(
        REPORT_DIR / "prospie_ml_oof_predictions.csv",
        index=False,
    )

    print("\n========== PROSPIE BASELINE ML EXPERIMENT ==========")
    print(f"Minute-level source rows: {len(df)}")
    print(f"Participant-condition samples: {len(dataset)}")
    print(f"Unique participants: {groups.nunique()}")
    print("Validation: 5-fold GroupKFold by participant")
    print(f"Target: Mean work-phase {TARGET}")
    print(f"Features: {feature_columns}")

    print("\nMODEL RESULTS")
    print(results_df.to_string(index=False))

    print("\nReports saved to:")
    print(REPORT_DIR)


if __name__ == "__main__":
    main()
