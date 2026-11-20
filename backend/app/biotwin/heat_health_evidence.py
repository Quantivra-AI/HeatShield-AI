"""Research-dataset context for supervisor heat-health explanations.

This module surfaces population-level research patterns only. It does not train
or run a clinical prediction model and never maps a research participant to a worker.
"""
from __future__ import annotations
import csv
import math
import os
from pathlib import Path
from statistics import mean, median
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "biotwin"
EXTERNAL = DATA / "external" / "mendeley_firefighter_heat_stress"


@lru_cache(maxsize=24)
def _read_csv(path: Path, limit: int = 10000):
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))[:limit]
    except Exception:
        return []


def _numbers(rows, key):
    out = []
    for row in rows:
        try:
            value = float(row.get(key, ""))
            if math.isfinite(value): out.append(value)
        except (TypeError, ValueError):
            pass
    return out


def _range_summary(rows, key, label, unit=""):
    values = _numbers(rows, key)
    if not values: return None
    suffix = f" {unit}" if unit else ""
    return f"{label}: n={len(values)}, median={median(values):.2f}{suffix}, range={min(values):.2f}–{max(values):.2f}{suffix}"


def build_heat_health_dataset_context(reading: dict, exposure: dict | None = None) -> dict:
    """Return compact, source-attributed evidence derived from bundled project CSVs
    plus an optional downloaded public firefighter dataset.
    """
    sections = []
    sources = []
    counts = {}

    # User/project's own human physiological heat-exposure data (10 healthy adults,
    # repeated pre/post-acclimation visits; 20 rows in cleaned table).
    phys_path = DATA / "processed" / "physiological_cleaned.csv"
    phys = _read_csv(phys_path)
    if phys:
        counts["project_physiological_rows"] = len(phys)
        sources.append({"name": "Project physiological heat-exposure dataset", "file": "backend/data/biotwin/processed/physiological_cleaned.csv", "rows": len(phys), "scope": "10 healthy adults with pre/post heat-exposure physiological measurements; population research, not disease labels"})
        lines = ["Project physiological dataset (healthy adult experimental heat exposure; not a clinical worker cohort):"]
        for key, label, unit in [
            ("hyperthermic_tcore_final__c", "Final core temperature", "°C"),
            ("hyperthermic_hr_final__bpm", "Final heart rate", "bpm"),
            ("heat_exposure_duration__s", "Heat exposure duration", "seconds"),
            ("sweat_rate__l_h", "Sweat rate", "L/hour"),
        ]:
            s = _range_summary(phys, key, label, unit)
            if s: lines.append(s)
        try:
            matches = [r for r in phys if str(r.get("visit", "")).lower() == "pre_acclimation"]
            lines.append(f"Pre-acclimation visit rows available: {len(matches)}; repeated measurements are not independent workers.")
        except Exception: pass
        sections.append("\n".join(lines))

    # Project's Prospie heat-exposure experiment table (155 condition-level records).
    prospie_path = DATA / "reports" / "prospie_ml_experiment_dataset.csv"
    prospie = _read_csv(prospie_path)
    if prospie:
        counts["project_prospie_rows"] = len(prospie)
        sources.append({"name": "Project Prospie heat-exposure experiment dataset", "file": "backend/data/biotwin/reports/prospie_ml_experiment_dataset.csv", "rows": len(prospie), "scope": "experimental condition records with rectal/core temperature and environmental/activity covariates; not disease outcome labels"})
        lines = ["Project Prospie experimental heat-exposure dataset (condition-level research records):"]
        for key, label, unit in [("corerectal", "Rectal/core temperature", "°C"), ("temp", "Ambient temperature", "°C"), ("humidity", "Relative humidity", "%"), ("tamb", "Mean ambient temperature", "°C"), ("age", "Participant age", "years")]:
            s = _range_summary(prospie, key, label, unit)
            if s: lines.append(s)
        # Nearest environment-only patterns; do not treat these as patient matches.
        try:
            t = float(exposure.get("air_temperature_c")) if exposure and exposure.get("air_temperature_c") is not None else None
            h = float(exposure.get("relative_humidity_pct")) if exposure and exposure.get("relative_humidity_pct") is not None else None
            if t is not None and h is not None:
                ranked=[]
                for r in prospie:
                    try:
                        rt,rh=float(r["temp"]),float(r["humidity"])
                        d=((rt-t)/10.0)**2+((rh-h)/25.0)**2
                        ranked.append((d,r))
                    except Exception: pass
                ranked.sort(key=lambda x:x[0])
                if ranked:
                    examples=[]
                    for _,r in ranked[:3]:
                        examples.append(f"ambient {float(r['temp']):.1f}°C, RH {float(r['humidity']):.0f}%, core/rectal {float(r['corerectal']):.2f}°C")
                    lines.append("Closest environmental condition examples (research analogues only, not individual predictions): " + "; ".join(examples))
        except Exception: pass
        sections.append("\n".join(lines))

    # Project's statistically summarized paired findings.
    findings_path = DATA / "reports" / "prospie_physiological_findings.csv"
    findings = _read_csv(findings_path)
    if findings:
        counts["project_physiological_findings"] = len(findings)
        sources.append({"name": "Project Prospie paired physiological findings", "file": "backend/data/biotwin/reports/prospie_physiological_findings.csv", "rows": len(findings), "scope": "paired group-level statistical comparisons; not diagnostic labels"})
        selected=[]
        for r in findings:
            if str(r.get("significant_after_bh", "")).lower() == "true" and str(r.get("metric", "")).lower() in {"hr", "tcore", "ts", "hr_mean", "coretemp"}:
                try: selected.append(r)
                except Exception: pass
        selected=selected[:4]
        if selected:
            lines=["Selected statistically significant project physiological comparisons (group-level):"]
            for r in selected:
                lines.append(f"{r.get('phase')} / {r.get('metric')}: n_pairs={r.get('n_pairs')}, mean change={r.get('mean_change_b_minus_a')}, adjusted p={r.get('p_adjusted_bh')}; interpretation is study-specific.")
            sections.append("\n".join(lines))

    # Optional Kaggle Human Vital Sign Dataset. It is included as a population-level
    # reference summary; model inference is handled separately by vital_risk.py.
    kaggle_path = DATA / "external" / "kaggle_human_vital_signs" / "human_vital_signs_dataset_2024.csv"
    kaggle_rows = _read_csv(kaggle_path, limit=10000)
    if kaggle_rows:
        counts["kaggle_human_vital_sign_rows"] = len(kaggle_rows)
        target_key = next((k for k in kaggle_rows[0].keys() if str(k).strip().lower().replace("_", " ") in {"risk category", "risk"}), None)
        class_counts = {}
        if target_key:
            for row in kaggle_rows:
                label = str(row.get(target_key, "")).strip()
                if label:
                    class_counts[label] = class_counts.get(label, 0) + 1
        sources.append({"name": "Kaggle Human Vital Sign Dataset", "file": "backend/data/biotwin/external/kaggle_human_vital_signs/human_vital_signs_dataset_2024.csv", "rows": len(kaggle_rows), "license": "CC0 reported in published dataset description; verify Kaggle metadata before redistribution", "scope": "High Risk/Low Risk dataset labels derived from vital-sign/body-composition thresholds; not disease outcome labels"})
        lines = ["Kaggle Human Vital Sign Dataset (population-level structured observations; target is dataset-defined High Risk/Low Risk, not diagnosis):", f"Rows loaded for compact context sample: {len(kaggle_rows)} (the full CSV is used by the offline training script)", f"Dataset-label counts in context sample: {class_counts or 'label column not detected'}"]
        for key, label, unit in [("Heart Rate", "Heart rate", "bpm"), ("Respiratory Rate", "Respiratory rate", "breaths/min"), ("Body Temperature", "Body temperature", "°C"), ("Oxygen Saturation", "Oxygen saturation", "%"), ("Systolic Blood Pressure", "Systolic BP", "mmHg"), ("Diastolic Blood Pressure", "Diastolic BP", "mmHg")]:
            summary = _range_summary(kaggle_rows, key, label, unit)
            if summary: lines.append(summary)
        sections.append("\n".join(lines))

    # Optional public Mendeley firefighter data. The included fetch script downloads
    # licensed CC BY 4.0 files into this directory; only use actual CSVs if present.
    public_files = {"Tcore_AM_PM.csv": "continuous core temperature", "HR_RPE_BW.csv": "heart rate, exertion and hydration/body-mass measures", "Skin_Microclimate.csv": "skin temperature and under-PPE microclimate", "Environment_Thermocouples.csv": "environmental heat measurements"}
    pub_lines=[]
    for filename, description in public_files.items():
        rows = _read_csv(EXTERNAL / filename, limit=20000)
        if rows:
            counts[f"public_{filename}"] = len(rows)
            pub_lines.append(f"{filename}: {len(rows)} records ({description}).")
    if pub_lines:
        sources.append({"name": "Circadian Timing and Heat Stress in Firefighters", "doi": "10.17632/7ghxcsd9sz.1", "license": "CC BY 4.0", "files": list(public_files)})
        sections.append("Public Mendeley firefighter dataset (21 male professional firefighters; AM/PM live-fire exposure; CC BY 4.0):\n" + "\n".join(pub_lines))

    if not sections:
        return {"context": "No research CSV evidence was available at runtime. Do not imply dataset support.", "sources": [], "counts": {}}

    context = "\n\n".join(sections)
    context += ("\n\nEVIDENCE USE LIMITS: These are population-level experimental research datasets, not diagnoses, "
                "not a labelled disease-outcome cohort, not a validated individual risk model, and not a direct match to this worker. "
                "Use only as contextual evidence; do not infer disease probability or claim clinical thresholds from dataset ranges.")
    return {"context": context[:9000], "sources": sources, "counts": counts}
