from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import Ridge
from sklearn.dummy import DummyRegressor
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


warnings.filterwarnings("ignore", category=UserWarning)

# --------------------------------------------------
# Paths and configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

DATA_PATH = (
    BASE_DIR
    / "data"
    / "biotwin"
    / "processed"
    / "prospie_cleaned.csv"
)

REPORT_DIR = (
    BASE_DIR
    / "data"
    / "biotwin"
    / "reports"
)

REPORT_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "corerectal"
GROUP_COLUMN = "participant"
CONDITION_COLUMN = "condition"

ALPHA_GRID = {
    "model__alpha": [0.1, 1.0, 10.0, 100.0]
}

OUTER_SPLITS = 5
INNER_SPLITS = 4


# --------------------------------------------------
# Feature configurations
# --------------------------------------------------

ENVIRONMENTAL = [
    "temp",
    "humidity",
    "wind",
    "tamb",
    "solar_present",
]

WORKLOAD = [
    "gradient",
    "speedkm_hr_1",
    "ml_kg_min",
]

PERSONAL = [
    "age",
    "bodymasskg",
    "heightcm",
    "bodyfat",
    "vo2peakmlkgmin",
]

FEATURE_CONFIGS = {
    "Condition only": {
        "numeric": [],
        "categorical": ["condition"],
    },
    "Environmental + condition": {
        "numeric": ENVIRONMENTAL,
        "categorical": ["condition"],
    },
    "Environmental + workload + condition": {
        "numeric": ENVIRONMENTAL + WORKLOAD,
        "categorical": ["condition"],
    },
    "All features + condition": {
        "numeric": ENVIRONMENTAL + WORKLOAD + PERSONAL,
        "categorical": ["condition", "clothing"],
    },
}


# --------------------------------------------------
# Load and prepare data
# --------------------------------------------------

def load_data():

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_PATH}"
        )

    df = pd.read_csv(DATA_PATH)

    required = [
        "workrest",
        GROUP_COLUMN,
        CONDITION_COLUMN,
        TARGET,
        "clothing",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # Work phase only
    df = df[df["workrest"] == 1].copy()

    # Keep only rows with a valid target
    df[TARGET] = pd.to_numeric(
        df[TARGET], errors="coerce"
    )

    df = df.dropna(
        subset=[GROUP_COLUMN, CONDITION_COLUMN, TARGET]
    )

    numeric_features = list(dict.fromkeys(
        ENVIRONMENTAL + WORKLOAD + PERSONAL + [TARGET]
    ))

    for col in numeric_features:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col], errors="coerce"
            )

    # One row per participant-condition.
    # Repeated minute-level measurements are aggregated.
    aggregation = {
        col: "mean"
        for col in numeric_features
        if col in df.columns
    }

    aggregation["clothing"] = "first"

    data = (
        df.groupby(
            [GROUP_COLUMN, CONDITION_COLUMN],
            as_index=False
        )
        .agg(aggregation)
    )

    data[CONDITION_COLUMN] = (
        data[CONDITION_COLUMN].astype(str)
    )

    data["clothing"] = (
        data["clothing"].astype(str)
    )

    return data


# --------------------------------------------------
# Model pipeline
# --------------------------------------------------

def build_pipeline(numeric_features, categorical_features):

    transformers = []

    if numeric_features:
        numeric_pipeline = Pipeline([
            (
                "imputer",
                SimpleImputer(strategy="median")
            ),
            (
                "scaler",
                StandardScaler()
            ),
        ])

        transformers.append(
            ("numeric", numeric_pipeline, numeric_features)
        )

    if categorical_features:
        categorical_pipeline = Pipeline([
            (
                "imputer",
                SimpleImputer(strategy="most_frequent")
            ),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore")
            ),
        ])

        transformers.append(
            (
                "categorical",
                categorical_pipeline,
                categorical_features
            )
        )

    preprocessing = ColumnTransformer(
        transformers=transformers,
        remainder="drop"
    )

    return Pipeline([
        ("preprocessing", preprocessing),
        ("model", Ridge()),
    ])


# --------------------------------------------------
# Metrics
# --------------------------------------------------

def calculate_metrics(actual, predicted):

    return {
        "MAE": mean_absolute_error(actual, predicted),
        "RMSE": np.sqrt(
            mean_squared_error(actual, predicted)
        ),
        "R2": r2_score(actual, predicted),
    }


# --------------------------------------------------
# Condition-aware baseline
# --------------------------------------------------

def condition_baseline(train_df, test_df):

    global_mean = train_df[TARGET].mean()

    condition_means = (
        train_df.groupby(CONDITION_COLUMN)[TARGET]
        .mean()
        .to_dict()
    )

    return np.array([
        condition_means.get(condition, global_mean)
        for condition in test_df[CONDITION_COLUMN]
    ])


# --------------------------------------------------
# Nested participant-grouped CV
# --------------------------------------------------

def run_experiment(data):

    all_predictions = []
    fold_metrics = []
    best_parameters = []

    outer_cv = GroupKFold(
        n_splits=OUTER_SPLITS
    )

    y = data[TARGET].to_numpy()
    groups = data[GROUP_COLUMN].to_numpy()

    print("\nDataset information")
    print("-------------------")
    print(f"Participant-condition samples: {len(data)}")
    print(f"Unique participants: {data[GROUP_COLUMN].nunique()}")
    print(f"Conditions: {data[CONDITION_COLUMN].nunique()}")

    for fold, (train_idx, test_idx) in enumerate(
        outer_cv.split(data, y, groups),
        start=1
    ):

        train_df = data.iloc[train_idx].copy()
        test_df = data.iloc[test_idx].copy()

        X_train = train_df.drop(
            columns=[TARGET, GROUP_COLUMN]
        )

        X_test = test_df.drop(
            columns=[TARGET, GROUP_COLUMN]
        )

        y_train = train_df[TARGET].to_numpy()
        y_test = test_df[TARGET].to_numpy()

        train_groups = train_df[GROUP_COLUMN].to_numpy()

        print(f"\nOuter fold {fold}/{OUTER_SPLITS}")
        print(
            f"Train participants: {len(np.unique(train_groups))}"
        )
        print(
            f"Test participants: {test_df[GROUP_COLUMN].nunique()}"
        )

        # ------------------------------
        # Baseline 1: global mean
        # ------------------------------

        dummy = DummyRegressor(strategy="mean")
        dummy.fit(
            np.zeros((len(y_train), 1)),
            y_train
        )

        dummy_predictions = dummy.predict(
            np.zeros((len(y_test), 1))
        )

        # ------------------------------
        # Baseline 2: condition mean
        # ------------------------------

        condition_predictions = condition_baseline(
            train_df,
            test_df
        )

        baseline_models = {
            "Dummy baseline": dummy_predictions,
            "Condition-aware baseline": condition_predictions,
        }

        for model_name, predictions in baseline_models.items():

            metrics = calculate_metrics(
                y_test,
                predictions
            )

            fold_metrics.append({
                "fold": fold,
                "model": model_name,
                **metrics,
            })

            for i, prediction in enumerate(predictions):
                all_predictions.append({
                    "fold": fold,
                    "model": model_name,
                    "participant": test_df.iloc[i][GROUP_COLUMN],
                    "condition": test_df.iloc[i][CONDITION_COLUMN],
                    "actual": y_test[i],
                    "predicted": prediction,
                })

        # ------------------------------
        # Ridge models with nested CV
        # ------------------------------

        for config_name, config in FEATURE_CONFIGS.items():

            numeric_features = config["numeric"]
            categorical_features = config["categorical"]

            selected_features = (
                numeric_features + categorical_features
            )

            missing_features = [
                col for col in selected_features
                if col not in X_train.columns
            ]

            if missing_features:
                raise ValueError(
                    f"{config_name}: missing features "
                    f"{missing_features}"
                )

            X_train_selected = X_train[selected_features]
            X_test_selected = X_test[selected_features]

            pipeline = build_pipeline(
                numeric_features,
                categorical_features
            )

            inner_cv = GroupKFold(
                n_splits=INNER_SPLITS
            )

            search = GridSearchCV(
                estimator=pipeline,
                param_grid=ALPHA_GRID,
                scoring="neg_mean_absolute_error",
                cv=inner_cv,
                n_jobs=-1,
                refit=True,
            )

            search.fit(
                X_train_selected,
                y_train,
                groups=train_groups
            )

            predictions = search.predict(
                X_test_selected
            )

            metrics = calculate_metrics(
                y_test,
                predictions
            )

            model_name = config_name

            fold_metrics.append({
                "fold": fold,
                "model": model_name,
                **metrics,
            })

            best_parameters.append({
                "fold": fold,
                "model": model_name,
                "best_alpha": search.best_params_[
                    "model__alpha"
                ],
                "inner_cv_best_mae": -search.best_score_,
            })

            for i, prediction in enumerate(predictions):
                all_predictions.append({
                    "fold": fold,
                    "model": model_name,
                    "participant": test_df.iloc[i][GROUP_COLUMN],
                    "condition": test_df.iloc[i][CONDITION_COLUMN],
                    "actual": y_test[i],
                    "predicted": prediction,
                })

            print(
                f"{config_name}: "
                f"MAE={metrics['MAE']:.4f}, "
                f"RMSE={metrics['RMSE']:.4f}, "
                f"R2={metrics['R2']:.4f}, "
                f"alpha={search.best_params_['model__alpha']}"
            )

    return (
        pd.DataFrame(all_predictions),
        pd.DataFrame(fold_metrics),
        pd.DataFrame(best_parameters),
    )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    print("Loading PROSPIE dataset...")
    data = load_data()

    predictions, folds, parameters = run_experiment(
        data
    )

    # Overall out-of-fold summary
    summary_rows = []

    for model_name, group in predictions.groupby("model"):

        metrics = calculate_metrics(
            group["actual"],
            group["predicted"]
        )

        summary_rows.append({
            "model": model_name,
            **metrics,
            "samples": len(group),
            "participants": group["participant"].nunique(),
        })

    summary = (
        pd.DataFrame(summary_rows)
        .sort_values("MAE")
        .reset_index(drop=True)
    )

    # Save reports
    predictions.to_csv(
        REPORT_DIR / "prospie_protocol_ablation_predictions.csv",
        index=False
    )

    folds.to_csv(
        REPORT_DIR / "prospie_protocol_ablation_fold_metrics.csv",
        index=False
    )

    parameters.to_csv(
        REPORT_DIR / "prospie_protocol_ablation_parameters.csv",
        index=False
    )

    summary.to_csv(
        REPORT_DIR / "prospie_protocol_ablation_summary.csv",
        index=False
    )

    metadata = {
        "experiment": "PROSPIE Protocol Context Ablation",
        "target": TARGET,
        "samples": len(data),
        "participants": int(data[GROUP_COLUMN].nunique()),
        "conditions": int(data[CONDITION_COLUMN].nunique()),
        "outer_splits": OUTER_SPLITS,
        "inner_splits": INNER_SPLITS,
        "validation": "Nested GroupKFold by participant",
        "target_definition": (
            "Mean work-phase rectal core temperature "
            "per participant-condition"
        ),
        "limitations": [
            "Exploratory analysis only.",
            "Condition is an experimental protocol identifier.",
            "Results do not establish generalisation to new workplaces.",
            "The target is contemporaneous work-phase temperature, "
            "not future heat-risk forecasting.",
            "The dataset contains a small number of independent participants."
        ],
    }

    with open(
        REPORT_DIR / "prospie_protocol_ablation_metadata.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            metadata,
            file,
            indent=4
        )

    print("\n" + "=" * 65)
    print("PROTOCOL ABLATION — OVERALL RESULTS")
    print("=" * 65)

    print(
        summary.to_string(
            index=False,
            float_format=lambda x: f"{x:.6f}"
        )
    )

    print("\nReports saved in:")
    print(REPORT_DIR)


if __name__ == "__main__":
    main()