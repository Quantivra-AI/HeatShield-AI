
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd


# --------------------------------------------------
# PATHS
# --------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[2]
BIOTWIN_DIR = BACKEND_DIR / "data" / "biotwin"

RAW_DIR = BIOTWIN_DIR / "raw"
PROCESSED_DIR = BIOTWIN_DIR / "processed"
REPORTS_DIR = BIOTWIN_DIR / "reports"

PROSPIE_FILE = RAW_DIR / "prospie_dataset.xlsx"
PHYSIO_FILE = RAW_DIR / "physiological_data.xlsx"


def create_directories():
    for directory in [RAW_DIR, PROCESSED_DIR, REPORTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def normalize_column_name(value):
    if pd.isna(value):
        return None

    name = str(value).strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^\w]+", "_", name)
    return name.strip("_").lower()


def make_unique_columns(columns):
    result = []
    counts = {}

    for column in columns:
        name = column or "unnamed"
        counts[name] = counts.get(name, 0) + 1

        if counts[name] > 1:
            name = f"{name}_{counts[name]}"

        result.append(name)

    return result


def quality_report(df, dataset_name):
    report = {
        "dataset": dataset_name,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_cells": int(df.isna().sum().sum()),
        "missing_percentage": round(
            float(df.isna().sum().sum() / max(df.size, 1) * 100), 2
        ),
        "columns_with_missing_values": {
            str(col): int(count)
            for col, count in df.isna().sum().items()
            if count > 0
        },
        "column_names": [str(col) for col in df.columns],
    }

    return report


# --------------------------------------------------
# DATASET 1: PROSPIE
# --------------------------------------------------

def preprocess_prospie():

    if not PROSPIE_FILE.exists():
        raise FileNotFoundError(
            f"PROSPIE file not found: {PROSPIE_FILE}"
        )

    raw = pd.read_excel(
        PROSPIE_FILE,
        sheet_name="Data",
        header=None
    )

    # First two rows contain grouped and individual headers.
    header_row_1 = raw.iloc[0].tolist()
    header_row_2 = raw.iloc[1].tolist()

    columns = []

    for first, second in zip(header_row_1, header_row_2):
        value = second if pd.notna(second) else first
        columns.append(normalize_column_name(value))

    # Remove completely blank columns.
    keep_indices = [
        index
        for index, column in enumerate(columns)
        if column is not None
    ]

    columns = [columns[index] for index in keep_indices]
    columns = make_unique_columns(columns)

    df = raw.iloc[2:, keep_indices].copy()
    df.columns = columns

    # Remove completely empty rows.
    df = df.dropna(how="all").reset_index(drop=True)

    # 9999 is the dataset's missing-value marker.
    df = df.replace(9999, np.nan)

    # Preserve participant IDs and experimental conditions.
    if "participant" in df.columns:
        df["participant"] = df["participant"].astype("string").str.strip()

    if "condition" in df.columns:
        df["condition"] = pd.to_numeric(
            df["condition"], errors="coerce"
        ).astype("Int64")

    # Convert time values into readable strings.
    if "time" in df.columns:
        df["time"] = df["time"].astype("string")

    # Save processed data.
    output_file = PROCESSED_DIR / "prospie_cleaned.csv"
    df.to_csv(output_file, index=False)

    report = quality_report(df, "PROSPIE")

    report["source_file"] = PROSPIE_FILE.name
    report["missing_value_marker_replaced"] = 9999
    report["processing_notes"] = [
        "Original raw workbook preserved.",
        "Two-row headers normalized.",
        "Completely empty columns excluded.",
        "9999 converted to missing values.",
        "No statistical imputation performed.",
        "Repeated participant measurements preserved."
    ]

    return df, report


# --------------------------------------------------
# DATASET 2: PHYSIOLOGICAL DATA
# --------------------------------------------------


def preprocess_physiological():

    if not PHYSIO_FILE.exists():
        raise FileNotFoundError(
            f"Physiological file not found: {PHYSIO_FILE}"
        )

    raw = pd.read_excel(
        PHYSIO_FILE,
        sheet_name="Heat exposure",
        header=None
    )

    headers = [
        normalize_column_name(value)
        for value in raw.iloc[2].tolist()
    ]

    records = []

    visits = [
        ("pre_acclimation", 3, 13),
        ("post_acclimation", 18, 28),
    ]

    for visit_name, start_row, end_row in visits:

        for row_index in range(start_row, end_row):

            row = raw.iloc[row_index]
            participant = row.iloc[0]

            if pd.isna(participant):
                continue

            record = {
                "participant_id": str(participant).strip(),
                "visit": visit_name,
            }

            # Normothermic measurements
            for col_index in range(1, 12):

                variable = headers[col_index]

                if variable:
                    record[f"normothermic_{variable}"] = (
                        row.iloc[col_index]
                    )

            # Hyperthermic measurements
            for col_index in range(13, 24):

                variable = headers[col_index]

                if variable:
                    record[f"hyperthermic_{variable}"] = (
                        row.iloc[col_index]
                    )

            # Shared exposure measurements
            for col_index in range(25, 28):

                variable = headers[col_index]

                if variable:
                    record[variable] = row.iloc[col_index]

            records.append(record)

    df = pd.DataFrame(records)

    identifier_columns = [
        "participant_id",
        "visit"
    ]

    for column in df.columns:

        if column not in identifier_columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    output_file = (
        PROCESSED_DIR / "physiological_cleaned.csv"
    )

    df.to_csv(output_file, index=False)

    report = quality_report(
        df,
        "Physiological Data"
    )

    report["source_file"] = PHYSIO_FILE.name

    report["processing_notes"] = [
        "One row represents one participant visit.",
        "Normothermic and hyperthermic measurements preserved separately.",
        "Original participant IDs preserved.",
        "Pre and post acclimation visits preserved.",
        "Shared exposure measurements retained.",
        "No missing-value imputation performed.",
        "Raw workbook preserved."
    ]

    report["participants"] = int(
        df["participant_id"].nunique()
    )

    report["visits"] = sorted(
        df["visit"].dropna().unique().tolist()
    )

    report["records_per_visit"] = {
        str(key): int(value)
        for key, value in df["visit"].value_counts().items()
    }

    return df, report



# --------------------------------------------------
# RUN BOTH DATASETS
# --------------------------------------------------

def run_preprocessing():

    create_directories()

    results = {}

    prospie_df, prospie_report = preprocess_prospie()
    results["prospie"] = prospie_report

    physiological_df, physiological_report = (
        preprocess_physiological()
    )
    results["physiological"] = physiological_report

    report_file = REPORTS_DIR / "data_quality_report.json"

    with open(report_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4, ensure_ascii=False)

    print("\n========== BIOTWIN PREPROCESSING ==========")

    print("\nPROSPIE")
    print(f"Rows: {len(prospie_df)}")
    print(f"Columns: {len(prospie_df.columns)}")
    print(f"Participants: {prospie_df['participant'].nunique() if 'participant' in prospie_df else 'Not found'}")

    print("\nPHYSIOLOGICAL DATA")
    print(f"Rows: {len(physiological_df)}")
    print(f"Columns: {len(physiological_df.columns)}")
    print(f"Participants: {physiological_df['participant_id'].nunique()}")

    print("\nFiles saved:")
    print(PROCESSED_DIR / "prospie_cleaned.csv")
    print(PROCESSED_DIR / "physiological_cleaned.csv")
    print(report_file)

    print("\nPreprocessing completed successfully.")


if __name__ == "__main__":
    run_preprocessing()
