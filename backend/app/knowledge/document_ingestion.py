from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.knowledge.chunking import chunk_pages
from app.knowledge.document_parser import parse_document
from app.knowledge.metadata import SourceMetadata

BACKEND_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = BACKEND_DIR / "data" / "knowledge"
REGISTRY_PATH = KNOWLEDGE_DIR / "source_registry.json"
MANIFEST_PATH = KNOWLEDGE_DIR / "ingestion_manifest.json"
RAW_DIR = KNOWLEDGE_DIR / "raw"
PROCESSED_DIR = KNOWLEDGE_DIR / "processed"
REPORT_DIR = KNOWLEDGE_DIR / "reports"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_registry() -> dict[str, Any]:
    registry = _read_json(REGISTRY_PATH, {"sources": []})
    if not isinstance(registry.get("sources"), list):
        raise ValueError("source_registry.json must contain a sources array")
    ids = [row.get("source_id") for row in registry["sources"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source_id values in source registry")
    for row in registry["sources"]:
        SourceMetadata.from_record(row)
    return registry


def _locate_source_file(source: dict[str, Any]) -> Path | None:
    expected = source.get("expected_filename")
    if not expected:
        return None
    matches = list(RAW_DIR.rglob(expected))
    if len(matches) > 1:
        raise ValueError(f"More than one raw file matches {expected}")
    return matches[0] if matches else None


def ingest_source(source: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    metadata = SourceMetadata.from_record(source)
    if not source.get("ingestion_approved", False):
        return {
            "source_id": metadata.source_id,
            "status": "blocked_rights_review",
            "message": "Ingestion is blocked until reuse rights are reviewed and ingestion_approved is explicitly set to true.",
        }

    source_path = _locate_source_file(source)
    if source_path is None:
        return {
            "source_id": metadata.source_id,
            "status": "source_file_missing",
            "expected_filename": source.get("expected_filename"),
            "source_url": source.get("source_url"),
        }

    checksum = _sha256(source_path)
    manifest = _read_json(MANIFEST_PATH, {"documents": []})
    prior = next(
        (row for row in manifest.get("documents", [])
         if row.get("source_id") == metadata.source_id and row.get("sha256") == checksum),
        None,
    )
    if prior and not force:
        return {
            "source_id": metadata.source_id,
            "status": "already_ingested",
            "chunks": prior.get("chunk_count", 0),
            "sha256": checksum,
        }

    pages = parse_document(source_path)
    chunks = chunk_pages(pages)
    if not chunks:
        return {"source_id": metadata.source_id, "status": "no_text_extracted", "pages": len(pages)}

    output_path = PROCESSED_DIR / f"{metadata.source_id}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            record = {
                "source_id": metadata.source_id,
                "title": metadata.title,
                "organization": metadata.organization,
                "document_type": metadata.document_type,
                "domains": list(metadata.domains),
                "jurisdiction": metadata.jurisdiction,
                "publication_date": metadata.publication_date,
                "authority_type": metadata.authority_type,
                "evidence_grade": metadata.evidence_grade,
                "reuse_status": metadata.reuse_status,
                "source_url": metadata.source_url,
                "source_file": source_path.name,
                "source_sha256": checksum,
                **chunk,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    entry = {
        "source_id": metadata.source_id,
        "title": metadata.title,
        "source_file": str(source_path.relative_to(KNOWLEDGE_DIR)),
        "processed_file": str(output_path.relative_to(KNOWLEDGE_DIR)),
        "sha256": checksum,
        "page_count_with_text": len(pages),
        "chunk_count": len(chunks),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "ingested",
        "reuse_status": metadata.reuse_status,
    }
    docs = [row for row in manifest.get("documents", []) if row.get("source_id") != metadata.source_id]
    docs.append(entry)
    manifest["documents"] = docs
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["summary"] = {
        "registered_sources": len(load_registry()["sources"]),
        "ingested_documents": len(docs),
        "note": "Only successfully parsed local files are counted as ingested documents.",
    }
    _write_json(MANIFEST_PATH, manifest)
    return {"source_id": metadata.source_id, "status": "ingested", "pages": len(pages), "chunks": len(chunks), "sha256": checksum, "processed_file": str(output_path)}


def run_ingestion(*, force: bool = False) -> dict[str, Any]:
    registry = load_registry()
    results = [ingest_source(source, force=force) for source in registry["sources"]]
    summary = {
        "registered_sources": len(registry["sources"]),
        "ingested": sum(row["status"] == "ingested" for row in results),
        "already_ingested": sum(row["status"] == "already_ingested" for row in results),
        "blocked_rights_review": sum(row["status"] == "blocked_rights_review" for row in results),
        "source_file_missing": sum(row["status"] == "source_file_missing" for row in results),
        "no_text_extracted": sum(row["status"] == "no_text_extracted" for row in results),
    }
    report = {"run_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "results": results}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(REPORT_DIR / "latest_ingestion_report.json", report)
    return report
