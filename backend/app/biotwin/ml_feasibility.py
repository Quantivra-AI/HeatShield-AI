
from pathlib import Path
import json
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_FILE = BACKEND_DIR / "data" / "biotwin" / "processed" / "prospie_cleaned.csv"
REPORT_DIR = BACKEND_DIR / "data" / "biotwin" / "reports"

TARGETS = [
    "corerectal",
    "δcore",
    "hr",
    "br",
    "sweatproductionl",
]

def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_FILE)

    required = {"participant", "condition"}
    missing_required = required - set(df.columns)
    if missing_required:
        raise ValueError(f"Required columns missing: {missing_required}")

    df["participant"] = df["participant"].astype(str)
    df["condition"] = pd.to_numeric(df["condition"], errors="coerce")

    results = []

    for target in TARGETS:
        if target not in df.columns:
            results.append({
                "target": target,
                "status": "column_not_found",
            })
            continue

        values = pd.to_numeric(df[target], errors="coerce")
        valid = values.notna()
        available = df.loc[valid].copy()

        participant_count = available["participant"].nunique()
        condition_count = available["condition"].nunique()

        participant_coverage = (
            available.groupby("participant").size()
            if not available.empty else pd.Series(dtype=int)
        )

        results.append({
            "target": target,
            "status": "assessed",
            "total_rows": int(len(df)),
            "available_rows": int(valid.sum()),
            "missing_percent": round(float(values.isna().mean() * 100), 2),
            "unique_participants": int(participant_count),
            "unique_conditions": int(condition_count),
            "participants_with_data": int((participant_coverage > 0).sum()),
            "minimum_rows_per_participant": (
                int(participant_coverage.min())
                if not participant_coverage.empty else 0
            ),
            "maximum_rows_per_participant": (
                int(participant_coverage.max())
                if not participant_coverage.empty else 0
            ),
        })

    target_report = pd.DataFrame(results)
    target_report.to_csv(
        REPORT_DIR / "prospie_ml_target_feasibility.csv",
        index=False
    )

    # Candidate feature availability.
    candidate_features = [
        "temp", "humidity", "wind", "tamb",
        "age", "bodymasskg", "heightcm", "bodyfat",
        "vo2peakmlkgmin", "activity_code", "workrest",
        "condition", "solar_present", "gradient",
        "speedkm_hr_1", "ml_kg_min",
        "corerectal", "δcore", "hr", "br",
    ]

    feature_rows = []
    for col in candidate_features:
        if col not in df.columns:
            continue

        values = pd.to_numeric(df[col], errors="coerce")
        feature_rows.append({
            "feature": col,
            "available_rows": int(values.notna().sum()),
            "missing_percent": round(float(values.isna().mean() * 100), 2),
            "unique_values": int(values.nunique()),
        })

    feature_report = pd.DataFrame(feature_rows)
    feature_report.to_csv(
        REPORT_DIR / "prospie_ml_feature_feasibility.csv",
        index=False
    )

    # Participant-level coverage: this is essential for group-based validation.
    participant_report = (
        df.groupby("participant")
        .agg(
            total_records=("condition", "size"),
            conditions_covered=("condition", "nunique"),
        )
        .reset_index()
    )

    participant_report.to_csv(
        REPORT_DIR / "prospie_ml_participant_coverage.csv",
        index=False
    )

    metadata = {
        "dataset": "PROSPIE",
        "rows": int(len(df)),
        "participants": int(df["participant"].nunique()),
        "conditions": sorted(
            int(x) for x in df["condition"].dropna().unique()
        ),
        "validation_recommendation": (
            "Use participant-grouped validation. Never randomly split "
            "minute-level rows across training and test sets."
        ),
        "important_limitations": [
            "Repeated minute-level records are not independent observations.",
            "Participant identity must be used for grouping, not as a predictive feature.",
            "Target and feature missingness must be assessed separately.",
            "Trial-level measurements must not be treated as minute-level measurements.",
            "Public research data must not generate individual worker medical risk scores.",
            "Any model result is exploratory and not a validated safety or clinical tool."
        ],
        "target_results": results,
    }

    with open(
        REPORT_DIR / "prospie_ml_feasibility.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(metadata, file, indent=4, ensure_ascii=False)

    print("\n========== PROSPIE ML FEASIBILITY AUDIT ==========")
    print(f"Rows: {len(df)}")
    print(f"Participants: {df['participant'].nunique()}")
    print(f"Conditions: {df['condition'].nunique()}")

    print("\nTARGET FEASIBILITY")
    print(target_report.to_string(index=False))

    print("\nFEATURE AVAILABILITY")
    print(feature_report.to_string(index=False))

    print("\nPARTICIPANT COVERAGE")
    print(participant_report.describe().to_string())

    print("\nReports saved to:")
    print(REPORT_DIR)


if __name__ == "__main__":
    main()
