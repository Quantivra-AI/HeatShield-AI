from pathlib import Path
import tempfile
import unittest

from app.knowledge.chunking import chunk_pages
from app.knowledge.document_parser import ParsedPage
from app.knowledge.metadata import SourceMetadata
from app.biotwin.knowledge_base import _expand_query, retrieve_evidence


class KnowledgePipelineTests(unittest.TestCase):
    def test_chunking_preserves_page_numbers(self):
        pages = [ParsedPage(page_number=7, text=("Evidence sentence. " * 180))]
        chunks = chunk_pages(pages, max_chars=500, overlap_chars=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(row["page_start"] == 7 and row["page_end"] == 7 for row in chunks))
        self.assertTrue(all(row["content"] for row in chunks))

    def test_source_metadata_requires_core_fields(self):
        record = {
            "source_id": "TEST-1", "title": "Test", "organization": "Test Org",
            "document_type": "clinical_guideline", "domains": ["heat"],
            "jurisdiction": "international", "source_url": "https://example.org",
            "reuse_status": "CC-BY-4.0", "ingestion_approved": True,
        }
        metadata = SourceMetadata.from_record(record)
        self.assertEqual(metadata.source_id, "TEST-1")
        self.assertEqual(metadata.domains, ("heat",))

    def test_clinical_query_expansion_includes_emergency_terms(self):
        expanded = _expand_query(
            "workplace heat-related illness emergency preparedness and buddy system"
        ).lower()
        self.assertIn("aggressive cooling", expanded)
        self.assertIn("periodic observation", expanded)
        self.assertIn("heat exhaustion", expanded)

    def test_workplace_heat_illness_query_retrieves_core_evidence(self):
        question = (
            "What workplace procedures are recommended for recognizing, preventing, "
            "and responding to occupational heat-related illness? Using only retrieved "
            "evidence, distinguish routine prevention and early recognition from "
            "emergency first aid and clinical treatment. Cover worker education, "
            "symptom recognition, buddy systems, emergency preparedness, escalation "
            "to medical care, and follow-up where supported. Explain the difference "
            "between heat exhaustion and suspected heat stroke only where the retrieved "
            "evidence provides sufficient detail. Preserve source-specific conditions "
            "and return-to-work evidence."
        )
        results = retrieve_evidence(question, top_k=12)
        refs = {
            (item["source"], item.get("page_start"))
            for item in results
        }
        self.assertIn(("NIOSH-2016-106", 111), refs)
        self.assertIn(("WHO-WMO-WORKPLACE-HEAT-2025", 44), refs)
        self.assertIn(("WHO-WMO-WORKPLACE-HEAT-2025", 66), refs)

    def test_plain_text_parser(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text("Heat exposure requires controls.\n\nWorkers need training.", encoding="utf-8")
            from app.knowledge.document_parser import parse_document
            pages = parse_document(path)
            self.assertEqual(len(pages), 1)
            self.assertIn("Workers need training", pages[0].text)


if __name__ == "__main__":
    unittest.main()
