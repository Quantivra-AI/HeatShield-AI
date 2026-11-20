"""Download the CC BY 4.0 Mendeley firefighter heat-stress dataset.
Run from backend: python scripts/download_heat_health_dataset.py
Requires outbound internet access. Files are used as population-level research context only.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

DATASET_ID = "7ghxcsd9sz"
VERSION = "1"
API = "https://api.data.mendeley.com"
OUT = Path(__file__).resolve().parents[1] / "data" / "biotwin" / "external" / "mendeley_firefighter_heat_stress"


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "HeatShieldAI-ResearchPrototype/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url, target):
    req = urllib.request.Request(url, headers={"User-Agent": "HeatShieldAI-ResearchPrototype/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as output:
        output.write(response.read())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metadata = get_json(f"{API}/datasets/{DATASET_ID}?version={VERSION}")
    files = metadata.get("files") or []
    if not files:
        files = get_json(f"{API}/datasets/publics/{DATASET_ID}/files?version={VERSION}&$limit=100")
    if isinstance(files, dict): files = files.get("results", [])
    wanted = {"Tcore_AM_PM.csv", "HR_RPE_BW.csv", "Skin_Microclimate.csv", "Environment_Thermocouples.csv", "Summary_Table1.xlsx", "Metadata_StudyDesign.pdf"}
    downloaded = []
    for item in files:
        name = item.get("filename") or item.get("name")
        file_id = item.get("id")
        if name not in wanted or not file_id:
            continue
        details = get_json(f"{API}/datasets/publics/{DATASET_ID}/files/{file_id}?version={VERSION}")
        url = (details.get("content_details") or {}).get("download_url")
        if not url:
            url = f"{API}/datasets/{DATASET_ID}/files/{file_id}/file_downloaded?version={VERSION}"
        target = OUT / name
        download(url, target)
        downloaded.append({"filename": name, "bytes": target.stat().st_size})
    if not downloaded:
        raise RuntimeError("No dataset files downloaded. Check Mendeley Data API availability or download the dataset manually from https://data.mendeley.com/datasets/7ghxcsd9sz/1")
    manifest = {
        "dataset": "Circadian Timing and Heat Stress in Firefighters",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "doi": "10.17632/7ghxcsd9sz.1",
        "license": "CC BY 4.0",
        "citation": "Mauvieux B., Markov A., Besnard S., Touitou Y., Edwards B.J. (2025). Circadian modulation of core temperature and thermoregulatory strain during live-fire compartment exposure in firefighters. Mendeley Data, 7ghxcsd9sz.1.",
        "source_url": "https://data.mendeley.com/datasets/7ghxcsd9sz/1",
        "downloaded_files": downloaded,
        "usage_limit": "Population-level experimental evidence only; not a diagnostic dataset or validated individual disease-risk model."
    }
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"Dataset download failed: {exc}", file=sys.stderr)
        sys.exit(1)
