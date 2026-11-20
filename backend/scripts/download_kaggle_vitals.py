"""Download the public Kaggle Human Vital Sign Dataset using kagglehub.

Install kagglehub first. Kaggle may require account authentication/acceptance
of dataset terms depending on account and platform policy.
"""
from pathlib import Path
import shutil
import sys

DATASET = "nasirayub2/human-vital-sign-dataset"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "biotwin" / "external" / "kaggle_human_vital_signs"
TARGET = OUT / "human_vital_signs_dataset_2024.csv"


def main():
    try:
        import kagglehub
    except ImportError as exc:
        raise SystemExit("Install kagglehub first: pip install kagglehub") from exc
    OUT.mkdir(parents=True, exist_ok=True)
    source_dir = Path(kagglehub.dataset_download(DATASET))
    candidates = list(source_dir.rglob("*.csv"))
    preferred = [p for p in candidates if p.name.lower() == "human_vital_signs_dataset_2024.csv"]
    if not preferred:
        preferred = [p for p in candidates if "vital" in p.name.lower() and "sign" in p.name.lower()]
    if not preferred:
        raise SystemExit(f"No expected vital-sign CSV found in downloaded dataset. CSV files: {[p.name for p in candidates]}")
    shutil.copy2(preferred[0], TARGET)
    print(f"Dataset copied to: {TARGET}")
    print("Next: python scripts/train_kaggle_vital_risk.py")

if __name__ == "__main__":
    main()
