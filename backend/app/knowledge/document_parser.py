from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class ParsedPage:
    page_number: int
    text: str


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()



def _is_non_content_page(text: str) -> bool:
    """Exclude obvious contents, abbreviation and decorative pages."""
    normalized = re.sub(r"\s+", " ", text).strip()
    lower = normalized.lower()

    # Contents pages with dotted leaders or numerous page references.
    has_contents_heading = bool(
        re.search(r"\b(?:table of )?contents\b", lower[:250])
    )

    dotted_leaders = len(re.findall(r"\.{2,}", normalized))
    page_references = len(
        re.findall(r"\b\d{1,3}\b", normalized)
    )

    if has_contents_heading and (
        dotted_leaders >= 2 or page_references >= 4
    ):
        return True

    # Abbreviation-only pages.
    has_abbreviation_heading = bool(
        re.search(
            r"\b(?:list of )?abbreviations\b",
            lower[:180],
        )
    )

    if has_abbreviation_heading and len(normalized) < 2500:
        return True

    # Report structure / chapter overview pages.
    if (
        "structure of the report" in lower[:350]
        and "chapter" in lower
        and "part a" in lower
    ):
        return True

    # Decorative section divider pages.
    if (
        len(normalized) < 160
        and (
            "what do we know?" in lower
            or "where do we go next?" in lower
            or re.search(r"\bpart [a-z]\b", lower)
        )
    ):
        return True

    # Short image-caption-only pages.
    has_image_credit = bool(
        re.search(
            r"(?:©|copyright|istockphoto|dreamstime|shutterstock|getty images)",
            lower,
        )
    )

    if has_image_credit and len(normalized) < 500:
        return True

    return False


def parse_document(path: Path) -> list[ParsedPage]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF parsing requires pypdf. Install backend requirements.") from exc
        reader = PdfReader(str(path))
        pages = []
        
        for index, page in enumerate(reader.pages, start=1):
            text = _clean_text(page.extract_text() or "")

            if not text:
                continue

            if _is_non_content_page(text):
                continue

            pages.append(ParsedPage(page_number=index, text=text))

        if not pages:
            raise ValueError(
                f"No extractable text found in {path.name}. It may be scanned; OCR is not enabled."
            )
        return pages

    if suffix in {".txt", ".md"}:
        text = _clean_text(path.read_text(encoding="utf-8", errors="replace"))
        return [ParsedPage(page_number=1, text=text)] if text else []

    if suffix in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(raw, "html.parser").get_text("\n")
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", raw)
        text = _clean_text(text)
        return [ParsedPage(page_number=1, text=text)] if text else []

    raise ValueError(f"Unsupported document type: {suffix}. Supported: PDF, HTML, TXT, MD.")
