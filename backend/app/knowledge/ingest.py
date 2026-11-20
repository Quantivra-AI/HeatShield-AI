from __future__ import annotations

import argparse
import json

from app.knowledge.document_ingestion import run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest approved HeatShield knowledge documents from backend/data/knowledge/raw")
    parser.add_argument("--force", action="store_true", help="Reprocess files even if their checksum was already ingested")
    args = parser.parse_args()
    report = run_ingestion(force=args.force)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
