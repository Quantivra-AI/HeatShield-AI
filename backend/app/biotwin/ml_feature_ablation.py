
"""BioTwin feature ablation experiment.

Compares feature groups using nested participant-grouped CV.
Target: mean work-phase core temperature per participant-condition.
This is exploratory contemporaneous estimation, not forecasting.
"""

from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.dummy import DummyRegressor


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = BASE_DIR / "data/biotwin/processed/prospie_cleaned.csv"
REPORT_DIR = BASE_DIR / "data/biotwin/reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "corerectal"
OUTER_SPLITS = 5
INNER_SPLITS = 4
RANDOM_STATE = 42

# Feature groups are defined before examining ablation results.
FEATURE_SETS = {
    "Environmental only": {
        "numeric": [
            "temp", "humidity", "wind", "tamb", "solar_present"
        ],
        "categorical": [],
    },
    "Environmental + workload": {
        "numeric": [
            "temp", "humidity", "wind", "tamb", "solar_present",
            "gradient", "speedkm_hr_1", "ml_kg_min",
        ],
        "categorical": [],
    },
    "Environmental + workload + personal": {
        "numeric": [
            "temp", "humidity", "wind", "tamb", "solar_present",
            "gradient", "speedkm_hr_1", "ml_kg_min",
            "age", "bodymasskg", "heightcm", "bodyfat",
            "vo2peakmlkgmin",
        ],
        "categorical": [],
    },
    "All features + protocol context": {
        "numeric": [
            "temp", "humidity", "wind", "tamb", "solar_present",
            "gradient", "speedkm_hr_1", "ml_kg_min",
            "age", "bodymasskg", "heightcm", "bodyfat",
            "vo2peakmlkgmin",
        ],
        "categorical": ["condition", "clothing"],
    },
}


def load_data():
    df = pd.read_csv(DATA_PATH)

    required = {
        "participant", "condition", "workrest", TARGET,
        "clothing",
    }
    for feature_set in FEATURE_SETS.values():
        required.update(feature_set["numeric"])
        required.update(feature_set["categorical"])

    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    work = df[df["workrest"] == 1].copy()

    numeric_columns = set()
    for feature_set in FEATURE_SETS.values():
        numeric_columns.update(feature_set["numeric"])
    numeric_columns.add(TARGET)

    for col in numeric_columns:
        work[col] = pd.to_numeric(work[col], errors="coerce")

    aggregation = {
        col: "mean" for col in numeric_columns
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
    data["condition"] = data["condition"].astype(str)
    data["clothing"] = data["clothing"].astype("string")

    print("FEATURE ABLATION DATA")
    print("---------------------")
    print("Samples:", len(data))
    print("Participants:", data["participant"].nunique())
    print("Conditions:", data["condition"].nunique())

    return data


def make_pipeline(numeric_features, categorical_features):
    transformers = []

    if numeric_features:
        numeric_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ])
        transformers.append(
            ("numeric", numeric_pipeline, numeric_features)
        )

    if categorical_features:
        categorical_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ])
        transformers.append(
            ("categorical", categorical_pipeline, categorical_features)
        )

    preprocessor = ColumnTransformer(transformers)

    return Pipeline([
        ("preprocessor", preprocessor),
        ("model", Ridge()),
    ])


def metrics(y_true, y_pred):
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def run_experiment():
    warnings.filterwarnings("ignore", category=UserWarning)

    data = load_data()
    y = data[TARGET].astype(float)
    groups = data["participant"]

    outer_cv = GroupKFold(n_splits=OUTER_SPLITS)

    fold_rows = []
    prediction_rows = []
    parameter_rows = []

    # Use identical outer folds for every feature set.
    outer_splits = list(
        outer_cv.split(data, y, groups=groups)
    )

    for fold, (train_idx, test_idx) in enumerate(
        outer_splits, start=1
    ):
        print(f"\nOUTER FOLD {fold}/{OUTER_SPLITS}")

        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]
        groups_train = groups.iloc[train_idx]

        # Global mean baseline.
        dummy = DummyRegressor(strategy="mean")
        dummy.fit(np.zeros((len(train_idx), 1)), y_train)
        dummy_pred = dummy.predict(
            np.zeros((len(test_idx), 1))
        )

        fold_models = {"Dummy baseline": dummy_pred}

        # Condition-aware baseline.
        train_conditions = data.iloc[train_idx]["condition"]
        test_conditions = data.iloc[test_idx]["condition"]

        condition_means = (
            pd.DataFrame({
                "condition": train_conditions.to_numpy(),
                "target": y_train.to_numpy(),
            })
            .groupby("condition")["target"]
            .mean()
        )

        condition_pred = (
            test_conditions.map(condition_means)
            .fillna(float(y_train.mean()))
            .to_numpy()
        )

        fold_models["Condition-aware baseline"] = condition_pred

        for set_name, feature_spec in FEATURE_SETS.items():
            numeric = feature_spec["numeric"]
            categorical = feature_spec["categorical"]
            selected_features = numeric + categorical

            X_train = data.iloc[train_idx][selected_features]
            X_test = data.iloc[test_idx][selected_features]

            pipeline = make_pipeline(numeric, categorical)

            search = GridSearchCV(
                estimator=pipeline,
                param_grid={"model__alpha": [0.1, 1.0, 10.0, 100.0]},
                scoring="neg_mean_absolute_error",
                cv=GroupKFold(n_splits=INNER_SPLITS),
                n_jobs=-1,
                refit=True,
                error_score="raise",
            )

            search.fit(
                X_train,
                y_train,
                groups=groups_train,
            )

            predictions = search.best_estimator_.predict(X_test)
            fold_models[set_name] = predictions

            parameter_rows.append({
                "fold": fold,
                "feature_set": set_name,
                "best_alpha": search.best_params_["model__alpha"],
                "best_inner_cv_mae": -search.best_score_,
            })

            print(
                f"  {set_name}: "
                f"best alpha={search.best_params_['model__alpha']}, "
                f"inner MAE={-search.best_score_:.4f}"
            )

        for model_name, predictions in fold_models.items():
            fold_metrics = metrics(y_test, predictions)

            fold_rows.append({
                "fold": fold,
                "model": model_name,
                "n_test_samples": len(test_idx),
                **fold_metrics,
            })

            for local_pos, pred in enumerate(predictions):
                original_idx = test_idx[local_pos]
                prediction_rows.append({
                    "fold": fold,
                    "participant": groups.iloc[original_idx],
                    "condition": data.iloc[original_idx]["condition"],
                    "actual_core_temp": float(y.iloc[original_idx]),
                    "model": model_name,
                    "predicted_core_temp": float(pred),
                })

            print(
                f"  {model_name}: "
                f"MAE={fold_metrics['mae']:.4f} °C | "
                f"RMSE={fold_metrics['rmse']:.4f} °C | "
                f"R²={fold_metrics['r2']:.4f}"
            )

    predictions_df = pd.DataFrame(prediction_rows)
    folds_df = pd.DataFrame(fold_rows)
    params_df = pd.DataFrame(parameter_rows)

    summary = []

    for model_name, group in predictions_df.groupby("model"):
        result = metrics(
            group["actual_core_temp"],
            group["predicted_core_temp"],
        )
        summary.append({
            "model": model_name,
            "n_oof_predictions": len(group),
            **result,
        })

    summary_df = pd.DataFrame(summary).sort_values("mae")

    predictions_df.to_csv(
        REPORT_DIR / "prospie_feature_ablation_predictions.csv",
        index=False,
    )
    folds_df.to_csv(
        REPORT_DIR / "prospie_feature_ablation_fold_metrics.csv",
        index=False,
    )
    params_df.to_csv(
        REPORT_DIR / "prospie_feature_ablation_parameters.csv",
        index=False,
    )
    summary_df.to_csv(
        REPORT_DIR / "prospie_feature_ablation_summary.csv",
        index=False,
    )

    print("\nFINAL FEATURE ABLATION RESULTS")
    print("------------------------------")
    print(summary_df.to_string(index=False))

    print("\nReports saved in:", REPORT_DIR)


if __name__ == "__main__":
    run_experiment()
