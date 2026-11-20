# HeatShield Global Medical & Occupational Knowledge Library

This package is a separate ingestion foundation. It does not replace or modify the existing BioTwin research RAG.

## Current status

- `data/knowledge/source_registry.json` registers eight international sources.
- `data/knowledge/ingestion_manifest.json` records only files that have actually been parsed.
- No full guideline is claimed to be ingested merely because its URL is registered.
- Full-text ingestion is blocked for sources whose reuse permissions have not been reviewed.
- ISO standards are metadata-only unless a licensed copy is available.

## Add a source document

1. Read `data/knowledge/source_registry.json` and check `ingestion_approved` and `reuse_status`.
2. Obtain the document from the official source under terms that permit the intended processing and storage.
3. Place it under `data/knowledge/raw/` using the exact `expected_filename` in the registry.
4. Run the ingestion command from `backend/`:

```powershell
python -m app.knowledge.ingest
```

To deliberately reprocess an unchanged file:

```powershell
python -m app.knowledge.ingest --force
```

Processed output is page-aware JSONL in `data/knowledge/processed/`. Each chunk preserves the source ID, title, organisation, document type, domains, jurisdiction, publication date, source URL, page number and source-file SHA-256 checksum.

## Supported input formats

- PDF (`pypdf` text extraction)
- HTML (`beautifulsoup4` when installed; a basic tag-stripping fallback exists)
- TXT and Markdown

Scanned PDFs with no selectable text are reported as `no_text_extracted`. OCR is intentionally not automatic: OCR output must be checked before it enters a medical knowledge base.

## Safety and rights controls

- `ingestion_approved` must be explicitly true for a source to be ingested.
- `--force` does not bypass the rights gate.
- Free-to-read does not mean free to bulk reproduce or redistribute.
- Preserve original publication dates and jurisdiction. US or other national guidance is not automatically global law.
- Clinical recommendations, occupational recommendations, technical standards and observational research must remain separately labelled.
- Do not use this library to diagnose workers, change medication, or issue autonomous treatment/fitness-for-work decisions.

## Current limitations

This is the first source-registration and document-ingestion milestone, not a completed global medical library. It does not yet perform retrieval, embeddings, clinical rule extraction, guideline conflict resolution, or LLM-as-a-Judge. Those are later integration stages after the source documents and rights are verified.
