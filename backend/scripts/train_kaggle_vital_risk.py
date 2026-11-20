"""Tune Random Forest and XGBoost against Kaggle's threshold-derived label.

Metrics describe reproduction of the source High/Low label only. They are not
clinical validation or disease-prediction performance. No patient-level split
is possible unless a stable patient identifier is present in the source file.
"""
from __future__ import annotations
import json, re, warnings
from pathlib import Path
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
    classification_report, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split, RandomizedSearchCV, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from scipy.stats import randint
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "biotwin" / "external" / "kaggle_human_vital_signs" / "human_vital_signs_dataset_2024.csv"
MODEL_DIR = ROOT / "data" / "biotwin" / "models"
ALIASES = {
    "heart_rate_bpm": ["heart rate", "heart_rate", "hr", "heart rate (bpm)"],
    "respiratory_rate_bpm": ["respiratory rate", "respiratory_rate", "resp rate", "resp", "respiratory rate (bpm)"],
    "body_temperature_c": ["body temperature", "body_temperature", "temperature", "temp", "body temperature (c)"],
    "spo2_pct": ["oxygen saturation", "spo2", "spo2 (%)", "oxygen saturation (%)"],
    "systolic_bp_mmhg": ["systolic blood pressure", "systolic bp", "sbp", "systolic blood pressure (mmhg)"],
    "diastolic_bp_mmhg": ["diastolic blood pressure", "diastolic bp", "dbp", "diastolic blood pressure (mmhg)"],
    "derived_bmi": ["derived bmi", "bmi"],
}
TARGETS = ["risk category", "risk_category", "risk", "risk label"]
FEATURES = list(ALIASES)


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def main():
    if not DATA.exists():
        raise SystemExit(f"Dataset missing: {DATA}\nRun: python scripts/download_kaggle_vitals.py")
    raw = pd.read_csv(DATA)
    columns = {norm(c): c for c in raw.columns}
    mapped = {f: next((columns[norm(a)] for a in aliases if norm(a) in columns), None) for f, aliases in ALIASES.items()}
    mapped = {k: v for k, v in mapped.items() if v}
    target_col = next((columns[norm(t)] for t in TARGETS if norm(t) in columns), None)
    missing = [f for f in FEATURES if f not in mapped]
    if missing or target_col is None:
        raise SystemExit(f"Unexpected schema. Missing={missing}; target={target_col}; columns={list(raw.columns)}")

    frame = pd.DataFrame({f: pd.to_numeric(raw[col], errors="coerce") for f, col in mapped.items()})
    labels = raw[target_col].astype(str).str.strip().str.lower()
    y = labels.map({
        "high risk": 1,
        "high": 1,
        "low risk": 0,
        "low": 0
    })
    valid = y.notna() & frame.notna().sum(axis=1).ge(4)
    X, y = frame.loc[valid, FEATURES], y.loc[valid]
    if len(X) < 500 or y.nunique() != 2:
        raise SystemExit(f"Insufficient usable rows or binary labels missing: {len(X)}")

    # Prefer group holdout if a stable participant identifier exists.
    id_col = next((c for c in raw.columns if norm(c) in {"patient id", "participant id", "subject id", "worker id"}), None)
    if id_col and raw.loc[valid, id_col].nunique() > 20:
        groups = raw.loc[valid, id_col].astype(str)
        splitter = GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42)
        tr_idx, te_idx = next(splitter.split(X, y, groups))
        X_train, X_test, y_train, y_test = X.iloc[tr_idx], X.iloc[te_idx], y.iloc[tr_idx], y.iloc[te_idx]
        split_desc = f"group holdout 80/20 by {id_col}"
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)
        split_desc = "stratified random 80/20; independence of records not established"

    # Tune on a bounded subset to keep a 200k-row experiment practical, then refit
    # the selected estimator on the full training partition.
    tune_n = min(60000, len(X_train))
    tune_x = X_train.sample(n=tune_n, random_state=42) if tune_n < len(X_train) else X_train
    tune_y = y_train.loc[tune_x.index]
    cv = 3
    candidates = {}

    rf = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                   ("model", RandomForestClassifier(class_weight="balanced_subsample", random_state=42, n_jobs=-1))])
    rf_search = RandomizedSearchCV(rf, {
        "model__n_estimators": [250, 400, 600],
        "model__max_depth": [None, 12, 20, 30],
        "model__min_samples_split": randint(2, 16),
        "model__min_samples_leaf": randint(1, 8),
        "model__max_features": ["sqrt", 0.8, 1.0],
    }, n_iter=8, scoring="balanced_accuracy", cv=cv, random_state=42, n_jobs=-1, verbose=1, refit=True)
    rf_search.fit(tune_x, tune_y)
    candidates["RandomForest_tuned"] = (rf_search.best_estimator_, float(rf_search.best_score_), rf_search.best_params_)

    xgb = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                    ("model", XGBClassifier(objective="binary:logistic", eval_metric="logloss", tree_method="hist",
                        random_state=42, n_jobs=-1, verbosity=0))])
    xgb_search = RandomizedSearchCV(xgb, {
        "model__n_estimators": [250, 400, 600],
        "model__max_depth": randint(3, 9),
        "model__learning_rate": [0.025, 0.04, 0.06, 0.1],
        "model__subsample": [0.75, 0.85, 1.0],
        "model__colsample_bytree": [0.7, 0.85, 1.0],
        "model__min_child_weight": randint(1, 8),
        "model__reg_lambda": [1, 2, 5, 10],
    }, n_iter=10, scoring="balanced_accuracy", cv=cv, random_state=42, n_jobs=1, verbose=1, refit=True)
    xgb_search.fit(tune_x, tune_y)
    candidates["XGBoost_tuned"] = (xgb_search.best_estimator_, float(xgb_search.best_score_), xgb_search.best_params_)

    evaluated = {}
    for name, (estimator, cv_score, params) in candidates.items():
        estimator.fit(X_train, y_train)
        pred = estimator.predict(X_test)
        high_recall = recall_score(y_test, pred, pos_label=1, zero_division=0)
        metrics = {
            "cv_balanced_accuracy": cv_score,
            "accuracy": float(accuracy_score(y_test, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, pred)),
            "macro_f1": float(f1_score(y_test, pred, average="macro")),
            "high_risk_precision": float(precision_score(y_test, pred, pos_label=1, zero_division=0)),
            "high_risk_recall": float(high_recall),
            "low_risk_recall": float(recall_score(y_test, pred, pos_label=0, zero_division=0)),
            "confusion_matrix_labels_high_low": confusion_matrix(y_test, pred, labels=[1, 0]).tolist(),
            "classification_report": classification_report(y_test, pred, target_names=["High Risk", "Low Risk"], output_dict=True, zero_division=0),
            "best_params": params,
        }
        evaluated[name] = {"estimator": estimator, "metrics": metrics}

    best_name = max(evaluated, key=lambda n: (evaluated[n]["metrics"]["balanced_accuracy"], evaluated[n]["metrics"]["high_risk_recall"], evaluated[n]["metrics"]["macro_f1"]))
    best = evaluated[best_name]
    bundle = {"model": best["estimator"], "feature_columns": FEATURES, "model_name": best_name,
              "label_order": ["High Risk", "Low Risk"]}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_DIR / "kaggle_vital_risk.joblib")
    report = {
        "dataset": "Kaggle Human Vital Sign Dataset", "dataset_slug": "nasirayub2/human-vital-sign-dataset",
        "source_file": DATA.name, "rows_total": int(len(raw)), "rows_used": int(len(X)),
        "feature_columns": FEATURES, "target_column": str(target_col),
        "class_counts": {str(k): int(v) for k, v in y.value_counts().items()}, "split": split_desc,
        "tuning_rows": int(len(tune_x)), "cv_folds": cv, "selection_metric": "balanced_accuracy; tie-break high-risk recall then macro-F1",
        "model_comparison": {n: v["metrics"] for n, v in evaluated.items()},
        "selected_model": best_name, "selected_metrics": best["metrics"],
        "interpretation": "All metrics measure reproduction of the dataset's threshold-derived High Risk/Low Risk label only. They are not clinical validation, disease prediction performance, or proof of generalization to occupational workers.",
        "limitations": ["Source label is threshold-derived, not a clinical outcome.", "No respiratory/cardiac disease outcome labels.", "Repeated or synthetic records may exist; participant independence is unknown unless group split was used.", "Not validated on HeatShield workers or occupational heat outcomes.", "No disease probability is produced."],
    }
    (MODEL_DIR / "kaggle_vital_risk_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "model_comparison"}, indent=2))
    print("\nMODEL COMPARISON:")
    for name, item in evaluated.items():
        m = item["metrics"]
        print(f"{name}: balanced_accuracy={m['balanced_accuracy']:.4f}, high_risk_recall={m['high_risk_recall']:.4f}, macro_f1={m['macro_f1']:.4f}")
    print(f"\nSelected model saved: {MODEL_DIR / 'kaggle_vital_risk.joblib'}")

if __name__ == "__main__":
    main()
