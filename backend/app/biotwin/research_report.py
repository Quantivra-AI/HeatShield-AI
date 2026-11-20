
from pathlib import Path
import json

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[2]

REPORT_DIR = (
    BACKEND_DIR / "data" / "biotwin" / "reports"
)

COMPARISON_FILE = REPORT_DIR / "prospie_paired_comparisons.csv"
QUALITY_FILE = REPORT_DIR / "prospie_analysis_quality.json"

ENVIRONMENTAL_METRICS = [
    "temp",
    "humidity",
    "wind",
    "tamb",
]

PHYSIOLOGICAL_METRICS = [
    "corerectal",
    "δcore",
    "hr",
    "br",
    "sweatproductionl",
    "ts",
    "tc",
    "tp",
    "rpe",
    "sw",
]


def load_reports():
    if not COMPARISON_FILE.exists():
        raise FileNotFoundError(COMPARISON_FILE)

    if not QUALITY_FILE.exists():
        raise FileNotFoundError(QUALITY_FILE)

    comparisons = pd.read_csv(COMPARISON_FILE)

    with open(QUALITY_FILE, encoding="utf-8") as file:
        quality = json.load(file)

    return comparisons, quality


def prepare_category(comparisons, metrics):
    result = comparisons[
        comparisons["metric"].isin(metrics)
    ].copy()

    result["significant_after_bh"] = (
        result["p_adjusted_bh"] < 0.05
    )

    result["sample_size_warning"] = (
        result["n_pairs"] < 10
    )

    result["phase"] = pd.Categorical(
        result["phase"],
        categories=["overall", "work", "rest"],
        ordered=True,
    )

    return result.sort_values(
        ["p_adjusted_bh", "metric", "phase"]
    )


def build_findings_summary(environmental, physiological):
    rows = []

    for category, frame in [
        ("environmental", environmental),
        ("physiological", physiological),
    ]:
        significant = frame[
            frame["significant_after_bh"]
        ]

        rows.append({
            "category": category,
            "total_comparisons": len(frame),
            "bh_significant_rows": len(significant),
            "comparisons_n_below_10": int(
                (frame["n_pairs"] < 10).sum()
            ),
            "unique_metrics_tested": int(
                frame["metric"].nunique()
            ),
        })

    return pd.DataFrame(rows)


def main():
    print("\nLoading PROSPIE research results...")

    comparisons, quality = load_reports()

    environmental = prepare_category(
        comparisons,
        ENVIRONMENTAL_METRICS,
    )

    physiological = prepare_category(
        comparisons,
        PHYSIOLOGICAL_METRICS,
    )

    # Save complete category-specific results.
    environmental.to_csv(
        REPORT_DIR / "prospie_environmental_findings.csv",
        index=False,
    )

    physiological.to_csv(
        REPORT_DIR / "prospie_physiological_findings.csv",
        index=False,
    )

    # Save BH-significant subsets.
    environmental[
        environmental["significant_after_bh"]
    ].to_csv(
        REPORT_DIR / "prospie_environmental_significant.csv",
        index=False,
    )

    physiological[
        physiological["significant_after_bh"]
    ].to_csv(
        REPORT_DIR / "prospie_physiological_significant.csv",
        index=False,
    )

    summary = build_findings_summary(
        environmental,
        physiological,
    )

    summary.to_csv(
        REPORT_DIR / "prospie_research_summary.csv",
        index=False,
    )

    # Preserve missingness information for interpretation.
    warnings = []

    for metric, details in quality["metric_quality"].items():
        if details["missing_percent"] >= 40:
            warnings.append({
                "metric": metric,
                "missing_percent": details["missing_percent"],
                "available_count": details["available_count"],
                "warning": "High missingness; interpret cautiously.",
            })

    warning_df = pd.DataFrame(warnings)

    warning_df.to_csv(
        REPORT_DIR / "prospie_metric_warnings.csv",
        index=False,
    )

    report = {
        "dataset": "PROSPIE",
        "total_comparisons": len(comparisons),
        "environmental_comparisons": len(environmental),
        "physiological_comparisons": len(physiological),
        "environmental_bh_significant": int(
            environmental["significant_after_bh"].sum()
        ),
        "physiological_bh_significant": int(
            physiological["significant_after_bh"].sum()
        ),
        "comparisons_with_fewer_than_10_pairs": int(
            (comparisons["n_pairs"] < 10).sum()
        ),
        "multiple_testing_method": "Benjamini-Hochberg",
        "significance_threshold": 0.05,
        "interpretation": [
            "Exploratory paired comparisons, not causal evidence.",
            "BH adjustment was applied across the complete comparison set.",
            "Overall, work, and rest comparisons may be related.",
            "Low paired sample sizes require caution.",
            "High-missingness metrics should not support broad conclusions.",
            "Population-level findings must not be converted into individual worker medical risk scores.",
        ],
    }

    with open(
        REPORT_DIR / "prospie_research_report.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(report, file, indent=4, ensure_ascii=False)

    print("\n========== RESEARCH REPORT COMPLETE ==========")
    print(summary.to_string(index=False))

    print("\nHigh-missingness metrics:")
    if warning_df.empty:
        print("None")
    else:
        print(warning_df.to_string(index=False))

    print("\nReports saved in:")
    print(REPORT_DIR)


if __name__ == "__main__":
    main()
