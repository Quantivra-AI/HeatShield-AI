from __future__ import annotations

import re
from typing import Any


def chunk_pages(
    pages: list[Any],
    *,
    max_chars: int = 1800,
    overlap_chars: int = 220,
) -> list[dict[str, Any]]:
    """Create page-bounded chunks while preserving source page references."""
    if max_chars < 300:
        raise ValueError("max_chars must be at least 300")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    chunks: list[dict[str, Any]] = []
    for page in pages:
        text = re.sub(r"\s+", " ", page.text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind(". ", start + max_chars // 2, end)
                if boundary > start:
                    end = boundary + 1
            content = text[start:end].strip()
            if content:
                chunks.append({
                    "page_start": page.page_number,
                    "page_end": page.page_number,
                    "chunk_index": len(chunks),
                    "content": content,
                })
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_chars)
    return chunks
