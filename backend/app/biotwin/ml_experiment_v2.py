
"""BioTwin ML Experiment v2.

Nested participant-grouped CV for Ridge, Random Forest and XGBoost.
The target is mean work-phase core temperature at participant-condition level.
This is an exploratory estimation experiment, not future forecasting.
"""

from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from xgboost import XGBRegressor


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = BASE_DIR / "data/biotwin/processed/prospie_cleaned.csv"
REPORT_DIR = BASE_DIR / "data/biotwin/reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42
OUTER_SPLITS = 5
INNER_SPLITS = 4

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
    "solar_present",
]

CATEGORICAL_FEATURES = [
    "condition",
    "clothing",
]

TARGET = "corerectal"


def load_experiment_data():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)

    required = [
        "participant",
        "condition",
        "workrest",
        TARGET,
        *NUMERIC_FEATURES,
        *CATEGORICAL_FEATURES,
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Only work-phase observations.
    work = df[df["workrest"] == 1].copy()

    for col in NUMERIC_FEATURES + [TARGET]:
        work[col] = pd.to_numeric(work[col], errors="coerce")

    # One sample per participant-condition.
    # Repeated minute-level records are aggregated within each trial.
    aggregation = {
        col: "mean" for col in NUMERIC_FEATURES + [TARGET]
    }

    aggregation["clothing"] = (
        lambda x: x.dropna().mode().iloc[0]
        if not x.dropna().mode().empty else np.nan
    )

    data = (
        work.groupby(["participant", "condition"], as_index=False)
        .agg(aggregation)
    )

    data = data.dropna(subset=[TARGET]).copy()

    # Keep experimental condition as a categorical protocol identifier.
    data["condition"] = data["condition"].astype(str)
    data["clothing"] = data["clothing"].astype("string")

    feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    X = data[feature_columns].copy()
    y = data[TARGET].astype(float)
    groups = data["participant"].copy()

    if groups.nunique() < OUTER_SPLITS:
        raise ValueError("Not enough participants for outer GroupKFold.")

    print("\nDATASET SUMMARY")
    print("---------------------------")
    print(f"Participant-condition samples: {len(data)}")
    print(f"Unique participants: {groups.nunique()}")
    print(f"Unique conditions: {data['condition'].nunique()}")
    print(f"Target mean: {y.mean():.4f} °C")
    print(f"Target SD: {y.std():.4f} °C")

    return data, X, y, groups


def make_preprocessor(scale_numeric=False):
    numeric_steps = [
        ("imputer", SimpleImputer(strategy="median"))
    ]

    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))

    numeric_pipeline = Pipeline(numeric_steps)

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    return ColumnTransformer([
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
    ])


def build_models():
    models = {}

    ridge = Pipeline([
        ("preprocessor", make_preprocessor(scale_numeric=True)),
        ("model", Ridge()),
    ])

    models["Ridge"] = (
        ridge,
        {
            "model__alpha": [0.1, 1.0, 10.0, 100.0],
        },
    )

    random_forest = Pipeline([
        ("preprocessor", make_preprocessor()),
        ("model", RandomForestRegressor(
            random_state=RANDOM_STATE,
            n_jobs=1,
        )),
    ])

    models["Random Forest"] = (
        random_forest,
        {
            "model__n_estimators": [200],
            "model__max_depth": [3, 5, None],
            "model__min_samples_leaf": [3, 5],
            "model__max_features": [0.7, 1.0],
        },
    )

    xgboost = Pipeline([
        ("preprocessor", make_preprocessor()),
        ("model", XGBRegressor(
            objective="reg:squarederror",
            eval_metric="mae",
            tree_method="hist",
            random_state=RANDOM_STATE,
            n_jobs=1,
            verbosity=0,
        )),
    ])

    models["XGBoost"] = (
        xgboost,
        {
            "model__n_estimators": [50, 100],
            "model__max_depth": [2, 3],
            "model__learning_rate": [0.03, 0.1],
            "model__reg_lambda": [1, 5],
        },
    )

    return models


def calculate_metrics(y_true, y_pred):
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def run_nested_experiment():
    warnings.filterwarnings("ignore", category=UserWarning)

    data, X, y, groups = load_experiment_data()
    models = build_models()

    outer_cv = GroupKFold(n_splits=OUTER_SPLITS)

    predictions = []
    fold_results = []
    selected_params = []

    # Each participant is held out from the complete training/tuning process.
    for fold, (train_idx, test_idx) in enumerate(
        outer_cv.split(X, y, groups), start=1
    ):
        print(f"\nOUTER FOLD {fold}/{OUTER_SPLITS}")

        X_train = X.iloc[train_idx]
        X_test = X.iloc[test_idx]
        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]

        groups_train = groups.iloc[train_idx]

        print(
            f"Train samples: {len(train_idx)} | "
            f"Test samples: {len(test_idx)} | "
            f"Train participants: {groups_train.nunique()}"
        )

        # Baseline 1: training-fold global mean.
        dummy = DummyRegressor(strategy="mean")
        dummy.fit(X_train, y_train)
        dummy_pred = dummy.predict(X_test)

        # Baseline 2: training-fold condition-specific mean.
        # Falls back to the training global mean for an unseen condition.
        train_condition_means = (
            data.iloc[train_idx]
            .assign(target=y_train.to_numpy())
            .groupby("condition")["target"]
            .mean()
            .to_dict()
        )
        global_mean = float(y_train.mean())

        condition_pred = (
            X_test["condition"]
            .map(train_condition_means)
            .fillna(global_mean)
            .to_numpy()
        )

        fold_predictions = {
            "Dummy": dummy_pred,
            "Condition-aware baseline": condition_pred,
        }

        for model_name, (pipeline, param_grid) in models.items():
            print(f"  Tuning {model_name}...")

            inner_cv = GroupKFold(n_splits=INNER_SPLITS)

            search = GridSearchCV(
                estimator=pipeline,
                param_grid=param_grid,
                scoring="neg_mean_absolute_error",
                cv=inner_cv,
                n_jobs=-1,
                refit=True,
                error_score="raise",
            )

            search.fit(
                X_train,
                y_train,
                groups=groups_train,
            )

            test_pred = search.best_estimator_.predict(X_test)
            fold_predictions[model_name] = test_pred

            selected_params.append({
                "fold": fold,
                "model": model_name,
                "best_inner_cv_mae": float(-search.best_score_),
                "best_params": json.dumps(search.best_params_, default=str),
            })

            print(
                f"    Best inner MAE: {-search.best_score_:.4f} °C"
            )

        # Save all outer-fold predictions.
        for model_name, pred in fold_predictions.items():
            for local_idx, prediction in enumerate(pred):
                original_idx = test_idx[local_idx]

                predictions.append({
                    "fold": fold,
                    "participant": groups.iloc[original_idx],
                    "condition": data.iloc[original_idx]["condition"],
                    "actual_core_temp": float(y.iloc[original_idx]),
                    "model": model_name,
                    "predicted_core_temp": float(prediction),
                })

            metrics = calculate_metrics(y_test, pred)

            fold_results.append({
                "fold": fold,
                "model": model_name,
                "n_test_samples": len(y_test),
                **metrics,
            })

            print(
                f"  {model_name}: "
                f"MAE={metrics['mae']:.4f} °C | "
                f"RMSE={metrics['rmse']:.4f} °C | "
                f"R²={metrics['r2']:.4f}"
            )

    prediction_df = pd.DataFrame(predictions)
    fold_df = pd.DataFrame(fold_results)
    params_df = pd.DataFrame(selected_params)

    # Overall metrics from all out-of-fold predictions.
    summary_rows = []

    for model_name, model_df in prediction_df.groupby("model"):
        metrics = calculate_metrics(
            model_df["actual_core_temp"],
            model_df["predicted_core_temp"],
        )

        summary_rows.append({
            "model": model_name,
            "n_oof_predictions": len(model_df),
            **metrics,
        })

    summary_df = pd.DataFrame(summary_rows).sort_values("mae")

    prediction_df.to_csv(
        REPORT_DIR / "prospie_ml_v2_oof_predictions.csv",
        index=False,
    )
    fold_df.to_csv(
        REPORT_DIR / "prospie_ml_v2_fold_metrics.csv",
        index=False,
    )
    params_df.to_csv(
        REPORT_DIR / "prospie_ml_v2_best_parameters.csv",
        index=False,
    )
    summary_df.to_csv(
        REPORT_DIR / "prospie_ml_v2_model_comparison.csv",
        index=False,
    )

    print("\nFINAL OUT-OF-FOLD MODEL COMPARISON")
    print("----------------------------------")
    print(summary_df.to_string(index=False))

    print("\nReports saved in:", REPORT_DIR)


if __name__ == "__main__":
    run_nested_experiment()
