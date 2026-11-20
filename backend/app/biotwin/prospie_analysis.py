
from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BACKEND_DIR
    / "data"
    / "biotwin"
    / "processed"
    / "prospie_cleaned.csv"
)

REPORT_DIR = (
    BACKEND_DIR
    / "data"
    / "biotwin"
    / "reports"
)

REPORT_DIR.mkdir(parents=True, exist_ok=True)

METRICS = [
    "corerectal",
    "δcore",
    "hr",
    "sweatproductionl",
    "temp",
    "humidity",
    "wind",
    "tamb",
    "br",
    "ts",
    "tc",
    "tp",
    "rpe",
    "sw",
]

# Comparisons are based on the study's documented
# condition descriptions. They are exploratory,
# not automatically causal comparisons.
CONDITION_COMPARISONS = [
    (1, 2),
    (1, 3),
    (6, 7),
    (6, 8),
    (6, 9),
    (6, 10),
    (6, 11),
    (7, 8),
    (9, 10),
]

PHASES = {
    "overall": None,
    "work": 1,
    "rest": 2,
}


# ---------------------------------------------------------
# Load and validate data
# ---------------------------------------------------------

def load_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"PROSPIE dataset not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required = {
        "condition",
        "participant",
        "activity_code",
        "workrest",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Required columns missing: {sorted(missing)}"
        )

    for column in METRICS:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column], errors="coerce"
            )

    df["condition"] = pd.to_numeric(
        df["condition"], errors="coerce"
    )

    df["participant"] = pd.to_numeric(
        df["participant"], errors="coerce"
    )

    df["workrest"] = pd.to_numeric(
        df["workrest"], errors="coerce"
    )

    df["activity_code"] = pd.to_numeric(
        df["activity_code"], errors="coerce"
    )

    return df


# ---------------------------------------------------------
# Participant-condition summaries
# ---------------------------------------------------------

def build_participant_summaries(df):
    available_metrics = [
        column for column in METRICS
        if column in df.columns
    ]

    records = []

    for (condition, participant), group in df.groupby(
        ["condition", "participant"],
        dropna=True
    ):
        phase_groups = {
            "overall": group,
            "work": group[group["workrest"] == 1],
            "rest": group[group["workrest"] == 2],
        }

        for phase_name, phase_df in phase_groups.items():

            if phase_df.empty:
                continue

            row = {
                "condition": int(condition),
                "participant": int(participant),
                "phase": phase_name,
                "n_records": int(len(phase_df)),
            }

            for metric in available_metrics:
                # Sweat production is a trial-level value,
                # not a minute-level work/rest measurement.
                if metric == "sweatproductionl" and phase_name != "overall":
                    row[f"{metric}_mean"] = np.nan
                    row[f"{metric}_sd"] = np.nan
                    row[f"{metric}_n"] = 0
                    continue

                values = phase_df[metric].dropna()

                row[f"{metric}_mean"] = (
                    float(values.mean())
                    if not values.empty else np.nan
                )

                row[f"{metric}_sd"] = (
                    float(values.std())
                    if len(values) > 1 else np.nan
                )

                row[f"{metric}_n"] = int(len(values))

            # Preserve trial-completion information.
            activity_codes = set(
                phase_df["activity_code"].dropna().tolist()
            )

            row["thermal_intolerance_event"] = int(
                2 in activity_codes
            )

            row["core_temperature_stop_event"] = int(
                3 in activity_codes
            )

            records.append(row)

    return pd.DataFrame(records)

def build_activity_event_summaries(df):
    """
    Summarize measurements by original PROSPIE activity/event code.
    Event codes are retained separately from work/rest categories.
    """

    available_metrics = [
        metric for metric in METRICS
        if metric in df.columns
    ]

    rows = []

    for (condition, participant, activity_code), group in df.groupby(
        ["condition", "participant", "activity_code"],
        dropna=True
    ):
        row = {
            "condition": int(condition),
            "participant": int(participant),
            "activity_code": int(activity_code),
            "n_records": int(len(group)),
        }

        for metric in available_metrics:
            # Sweat production is a trial-level value.
            # Do not repeat it as an event-specific measurement.
            if metric == "sweatproductionl":
                continue

            values = group[metric].dropna()

            row[f"{metric}_mean"] = (
                float(values.mean()) if not values.empty else np.nan
            )
            row[f"{metric}_sd"] = (
                float(values.std()) if len(values) > 1 else np.nan
            )
            row[f"{metric}_n"] = int(len(values))

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------
# Condition-level descriptive summaries
# Each participant contributes one summary value.
# ---------------------------------------------------------

def build_condition_summaries(participant_df):
    rows = []

    for (condition, phase), group in participant_df.groupby(
        ["condition", "phase"]
    ):
        row = {
            "condition": int(condition),
            "phase": phase,
            "n_participants": int(group["participant"].nunique()),
        }

        for metric in METRICS:
            # Do not compare trial-level sweat production by work/rest phase.
            if metric == "sweatproductionl" and phase != "overall":
                continue
            column = f"{metric}_mean"

            if column not in group.columns:
                continue

            values = group[column].dropna()

            row[f"{metric}_participant_mean"] = (
                float(values.mean())
                if not values.empty else np.nan
            )

            row[f"{metric}_participant_sd"] = (
                float(values.std())
                if len(values) > 1 else np.nan
            )

            row[f"{metric}_participants_available"] = int(
                len(values)
            )

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------
# Benjamini-Hochberg correction
# ---------------------------------------------------------

def benjamini_hochberg(p_values):
    p_values = np.asarray(p_values, dtype=float)
    adjusted = np.full(len(p_values), np.nan)

    valid_indices = np.where(np.isfinite(p_values))[0]

    if len(valid_indices) == 0:
        return adjusted

    valid_p = p_values[valid_indices]
    order = np.argsort(valid_p)
    sorted_p = valid_p[order]

    n = len(sorted_p)

    corrected = sorted_p * n / np.arange(1, n + 1)
    corrected = np.minimum.accumulate(corrected[::-1])[::-1]
    corrected = np.clip(corrected, 0, 1)

    original_order = np.empty(n)
    original_order[order] = corrected

    adjusted[valid_indices] = original_order

    return adjusted


# ---------------------------------------------------------
# Paired condition comparisons
# ---------------------------------------------------------

def paired_comparison(a, b):
    paired = pd.concat(
        [a.rename("a"), b.rename("b")],
        axis=1
    ).dropna()

    n = len(paired)

    if n < 5:
        return None

    differences = (
        paired["b"] - paired["a"]
    ).to_numpy(dtype=float)

    mean_difference = float(np.mean(differences))
    sd_difference = float(np.std(differences, ddof=1))

    if sd_difference == 0:
        effect_size = np.nan
    else:
        effect_size = mean_difference / sd_difference

    if np.allclose(differences, 0):
        test_name = "no_change"
        statistic = 0.0
        p_value = 1.0

    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            if n >= 3:
                shapiro_p = stats.shapiro(differences).pvalue
            else:
                shapiro_p = np.nan

        if np.isfinite(shapiro_p) and shapiro_p >= 0.05:
            result = stats.ttest_rel(
                paired["b"],
                paired["a"]
            )
            test_name = "paired_t_test"
        else:
            result = stats.wilcoxon(
                paired["b"],
                paired["a"],
                zero_method="wilcox"
            )
            test_name = "wilcoxon_signed_rank"

        statistic = float(result.statistic)
        p_value = float(result.pvalue)

    # Descriptive t-based confidence interval for the
    # paired mean difference. It is not a Wilcoxon CI.
    standard_error = stats.sem(differences)

    if np.isfinite(standard_error):
        critical_value = stats.t.ppf(
            0.975, df=n - 1
        )

        ci_lower = (
            mean_difference
            - critical_value * standard_error
        )

        ci_upper = (
            mean_difference
            + critical_value * standard_error
        )
    else:
        ci_lower = np.nan
        ci_upper = np.nan

    return {
        "n_pairs": int(n),
        "mean_condition_a": float(paired["a"].mean()),
        "mean_condition_b": float(paired["b"].mean()),
        "mean_change_b_minus_a": mean_difference,
        "ci95_lower_t_based": float(ci_lower),
        "ci95_upper_t_based": float(ci_upper),
        "test": test_name,
        "statistic": statistic,
        "p_value": p_value,
        "cohens_dz": (
            float(effect_size)
            if np.isfinite(effect_size) else None
        ),
    }


def run_condition_comparisons(participant_df):
    rows = []

    for phase in PHASES:

        phase_df = participant_df[
            participant_df["phase"] == phase
        ]

        for condition_a, condition_b in CONDITION_COMPARISONS:

            data_a = phase_df[
                phase_df["condition"] == condition_a
            ]

            data_b = phase_df[
                phase_df["condition"] == condition_b
            ]

            for metric in METRICS:
                column = f"{metric}_mean"

                if (
                    column not in phase_df.columns
                    or data_a.empty
                    or data_b.empty
                ):
                    continue

                a = data_a.set_index("participant")[column]
                b = data_b.set_index("participant")[column]

                result = paired_comparison(a, b)

                if result is None:
                    continue

                rows.append({
                    "phase": phase,
                    "condition_a": condition_a,
                    "condition_b": condition_b,
                    "metric": metric,
                    **result,
                })

    results = pd.DataFrame(rows)

    if not results.empty:
        results["p_adjusted_bh"] = (
            benjamini_hochberg(results["p_value"])
        )

    return results


# ---------------------------------------------------------
# Data quality and coverage report
# ---------------------------------------------------------

def build_quality_report(df, participant_df):
    metric_quality = {}

    for metric in METRICS:
        if metric not in df.columns:
            continue

        metric_quality[metric] = {
            "missing_count": int(df[metric].isna().sum()),
            "missing_percent": round(
                float(df[metric].isna().mean() * 100), 2
            ),
            "available_count": int(df[metric].notna().sum()),
        }

    return {
        "dataset": "PROSPIE",
        "source_file": INPUT_FILE.name,
        "total_records": int(len(df)),
        "unique_participants": int(
            df["participant"].nunique()
        ),
        "conditions": sorted(
            int(x) for x in df["condition"].dropna().unique()
        ),
        "duplicate_participant_condition_time_records": (
            int(
                df.duplicated(
                    ["participant", "condition", "time"]
                ).sum()
            )
            if "time" in df.columns else None
        ),
        "participant_condition_phase_rows": int(
            len(participant_df)
        ),
        "metric_quality": metric_quality,
        "interpretation": (
            "Exploratory research analysis. "
            "Repeated minute-level measurements are summarized "
            "within participants before paired comparisons. "
            "Incomplete trials are retained."
        ),
    }


# ---------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------

def main():
    print("\nLoading PROSPIE dataset...")
    df = load_data()

    print(f"Records loaded: {len(df):,}")
    print(
        f"Participants: {df['participant'].nunique()}"
    )
    print(
        f"Conditions: {sorted(df['condition'].dropna().unique().tolist())}"
    )

    print("\nBuilding participant-level summaries...")
    participant_df = build_participant_summaries(df)

    print("\nBuilding original activity-event summaries...")
    event_df = build_activity_event_summaries(df)

    event_path = (
        REPORT_DIR / "prospie_activity_event_summaries.csv"
    )

    event_df.to_csv(event_path, index=False)

    print(f"Activity-event summary rows: {len(event_df):,}")
    print(event_path)

    participant_path = (
        REPORT_DIR / "prospie_participant_summaries.csv"
    )

    participant_df.to_csv(
        participant_path,
        index=False
    )

    print("\nBuilding condition-level summaries...")
    condition_df = build_condition_summaries(
        participant_df
    )

    condition_path = (
        REPORT_DIR / "prospie_condition_summaries.csv"
    )

    condition_df.to_csv(
        condition_path,
        index=False
    )

    print("\nRunning exploratory paired comparisons...")
    comparison_df = run_condition_comparisons(
        participant_df
    )

    comparison_path = (
        REPORT_DIR / "prospie_paired_comparisons.csv"
    )

    comparison_df.to_csv(
        comparison_path,
        index=False
    )

    print("\nGenerating data quality report...")
    quality = build_quality_report(
        df,
        participant_df
    )

    quality_path = (
        REPORT_DIR / "prospie_analysis_quality.json"
    )

    with open(quality_path, "w", encoding="utf-8") as file:
        json.dump(
            quality,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n========== PROSPIE ANALYSIS COMPLETE ==========")
    print(f"Raw records: {len(df):,}")
    print(
        f"Participants: {df['participant'].nunique()}"
    )
    print(
        f"Participant summary rows: {len(participant_df):,}"
    )
    print(
        f"Condition summary rows: {len(condition_df):,}"
    )
    print(
        f"Paired comparisons: {len(comparison_df):,}"
    )

    print("\nGenerated reports:")
    print(participant_path)
    print(condition_path)
    print(comparison_path)
    print(quality_path)

    if not comparison_df.empty:
        significant = comparison_df[
            comparison_df["p_adjusted_bh"] < 0.05
        ]

        print(
            "\nComparisons with BH-adjusted p < 0.05:"
        )

        if significant.empty:
            print("None")
        else:
            print(
                significant[
                    [
                        "phase",
                        "condition_a",
                        "condition_b",
                        "metric",
                        "n_pairs",
                        "mean_change_b_minus_a",
                        "p_value",
                        "p_adjusted_bh",
                    ]
                ].to_string(index=False)
            )


if __name__ == "__main__":
    main()
