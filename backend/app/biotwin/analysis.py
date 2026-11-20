
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


BASE_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = BASE_DIR / "data" / "biotwin" / "processed"
REPORT_DIR = BASE_DIR / "data" / "biotwin" / "reports"

INPUT_FILE = PROCESSED_DIR / "physiological_cleaned.csv"

VISITS = ["pre_acclimation", "post_acclimation"]

# Multiple-comparison correction: Benjamini-Hochberg
def benjamini_hochberg(p_values):
    p_values = np.asarray(p_values, dtype=float)
    adjusted = np.full(len(p_values), np.nan)

    valid = np.isfinite(p_values)
    if not valid.any():
        return adjusted.tolist()

    values = p_values[valid]
    n = len(values)
    order = np.argsort(values)
    sorted_p = values[order]

    ranked = sorted_p * n / np.arange(1, n + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    ranked = np.clip(ranked, 0, 1)

    restored = np.empty(n)
    restored[order] = ranked
    adjusted[valid] = restored

    return adjusted.tolist()


def analyze_paired_variable(df, column):
    paired = df.pivot(
        index="participant_id",
        columns="visit",
        values=column
    )

    paired = paired.reindex(columns=VISITS).dropna()

    pre = paired["pre_acclimation"].astype(float).to_numpy()
    post = paired["post_acclimation"].astype(float).to_numpy()

    differences = post - pre
    n = len(differences)

    result = {
        "variable": column,
        "n_pairs": n,
        "pre_mean": None,
        "pre_sd": None,
        "post_mean": None,
        "post_sd": None,
        "mean_change_post_minus_pre": None,
        "mean_change_ci_95_lower": None,
        "mean_change_ci_95_upper": None,
        "normality_shapiro_p": None,
        "test_used": None,
        "test_statistic": None,
        "p_value": None,
        "cohens_dz": None,
    }

    if n < 2:
        result["test_used"] = "insufficient_paired_data"
        return result

    mean_change = float(np.mean(differences))
    sd_change = float(np.std(differences, ddof=1))

    result.update({
        "pre_mean": float(np.mean(pre)),
        "pre_sd": float(np.std(pre, ddof=1)),
        "post_mean": float(np.mean(post)),
        "post_sd": float(np.std(post, ddof=1)),
        "mean_change_post_minus_pre": mean_change,
    })

    # 95% confidence interval for the paired mean change
    standard_error = sd_change / np.sqrt(n)
    critical_value = stats.t.ppf(0.975, df=n - 1)

    result["mean_change_ci_95_lower"] = float(
        mean_change - critical_value * standard_error
    )
    result["mean_change_ci_95_upper"] = float(
        mean_change + critical_value * standard_error
    )

    # Standardized paired effect size
    if sd_change > 0:
        result["cohens_dz"] = float(mean_change / sd_change)

    # Identical pre/post values: no difference to test
    if np.allclose(differences, 0):
        result.update({
            "test_used": "no_change",
            "test_statistic": 0.0,
            "p_value": 1.0,
        })
        return result

    # Shapiro-Wilk test on paired differences
    shapiro_p = float(stats.shapiro(differences).pvalue)
    result["normality_shapiro_p"] = shapiro_p

    # Choose test based on distribution of paired differences
    if shapiro_p >= 0.05:
        test = stats.ttest_rel(post, pre)
        result["test_used"] = "paired_t_test"
        result["test_statistic"] = float(test.statistic)
        result["p_value"] = float(test.pvalue)
    else:
        test = stats.wilcoxon(
            post,
            pre,
            zero_method="wilcox",
            alternative="two-sided"
        )
        result["test_used"] = "wilcoxon_signed_rank"
        result["test_statistic"] = float(test.statistic)
        result["p_value"] = float(test.pvalue)

    return result


def run_analysis():
    print("\n========== BIOTWIN PHYSIOLOGICAL ANALYSIS ==========")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {INPUT_FILE}. Run preprocessing first."
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_FILE)

    required = {"participant_id", "visit"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    if df.duplicated(["participant_id", "visit"]).any():
        raise ValueError(
            "Duplicate participant/visit records found. "
            "Resolve duplicates before paired analysis."
        )

    if set(df["visit"].dropna().unique()) != set(VISITS):
        raise ValueError(
            f"Expected visits: {VISITS}. "
            f"Found: {df['visit'].dropna().unique().tolist()}"
        )

    # Identify numeric measurements, excluding participant identifier
    numeric_columns = [
        col for col in df.select_dtypes(include=np.number).columns
        if col != "participant_id"
    ]

    if not numeric_columns:
        raise ValueError("No numeric measurement columns found.")

    # Validate that every participant has both visits
    visit_counts = df.groupby("participant_id")["visit"].nunique()
    complete_participants = visit_counts[visit_counts == 2].index
    analysis_df = df[df["participant_id"].isin(complete_participants)].copy()

    print(f"Total records: {len(df)}")
    print(f"Participants: {df['participant_id'].nunique()}")
    print(f"Complete paired participants: {len(complete_participants)}")
    print(f"Numeric measurements: {len(numeric_columns)}")

    results = []

    for column in numeric_columns:
        result = analyze_paired_variable(analysis_df, column)
        results.append(result)

    results_df = pd.DataFrame(results)

    # Correct p-values across all tested measurements
    results_df["p_value_adjusted_bh"] = benjamini_hochberg(
        results_df["p_value"].tolist()
    )

    results_df["exploratory_significance_p05"] = (
        results_df["p_value"] < 0.05
    )
    results_df["exploratory_significance_bh05"] = (
        results_df["p_value_adjusted_bh"] < 0.05
    )

    # Save detailed statistical results
    csv_path = REPORT_DIR / "physiological_paired_analysis.csv"
    results_df.to_csv(csv_path, index=False)

    # Save structured JSON report
    report = {
        "analysis": "Paired pre/post heat acclimation comparison",
        "dataset": INPUT_FILE.name,
        "total_records": int(len(df)),
        "total_participants": int(df["participant_id"].nunique()),
        "complete_paired_participants": int(len(complete_participants)),
        "sample_size_note": (
            "Exploratory analysis with a small sample. "
            "Results are not clinical conclusions or validated worker-risk predictions."
        ),
        "visit_comparison": {
            "before": "pre_acclimation",
            "after": "post_acclimation",
            "change_definition": "post_acclimation minus pre_acclimation",
        },
        "multiple_testing": "Benjamini-Hochberg false discovery rate correction",
        "results": results_df.replace(
            {np.nan: None}
        ).to_dict(orient="records"),
    }

    json_path = REPORT_DIR / "physiological_paired_analysis.json"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, allow_nan=False)

    print("\n========== ANALYSIS SUMMARY ==========")

    display_columns = [
        "variable",
        "n_pairs",
        "mean_change_post_minus_pre",
        "test_used",
        "p_value",
        "p_value_adjusted_bh",
    ]

    print(
        results_df[display_columns].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}"
        )
    )

    print("\nReports saved:")
    print(csv_path)
    print(json_path)

    print("\nAnalysis completed successfully.")


if __name__ == "__main__":
    run_analysis()
