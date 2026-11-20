from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REQUIRED_SOURCE_FIELDS = (
    "source_id", "title", "organization", "document_type", "domains",
    "jurisdiction", "source_url", "reuse_status", "ingestion_approved",
)


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    title: str
    organization: str
    document_type: str
    domains: tuple[str, ...]
    jurisdiction: str
    source_url: str
    publication_date: str | None = None
    authority_type: str | None = None
    evidence_grade: str | None = None
    reuse_status: str = "unknown"

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "SourceMetadata":
        missing = [key for key in REQUIRED_SOURCE_FIELDS if key not in record]
        if missing:
            raise ValueError(f"Source record missing required fields: {', '.join(missing)}")
        return cls(
            source_id=str(record["source_id"]),
            title=str(record["title"]),
            organization=str(record["organization"]),
            document_type=str(record["document_type"]),
            domains=tuple(str(x) for x in record["domains"]),
            jurisdiction=str(record["jurisdiction"]),
            source_url=str(record["source_url"]),
            publication_date=record.get("publication_date"),
            authority_type=record.get("authority_type"),
            evidence_grade=record.get("evidence_grade"),
            reuse_status=str(record["reuse_status"]),
        )
