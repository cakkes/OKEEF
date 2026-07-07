"""Classification stage. This is a deterministic stub for Phase 1/2 so the rest of the
pipeline (write/index/commit) can be built and tested without Ollama. Phase 3 replaces
the body of classify() with a real Ollama structured-output call — the signature and
return type (Classification) stay the same, so nothing upstream or downstream changes.
"""

from __future__ import annotations

from pathlib import Path

from .models import Classification
from .slug import slugify


def classify(path: Path, text: str) -> Classification:
    title = _title_from_filename(path)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return Classification(
        para_bucket="Resources",
        okf_type="note",
        title=title,
        description=(first_line[:200] or "No description available."),
        summary=(text.strip()[:400] or "No summary available."),
        tags=["unclassified"],
        folder_slug="unsorted",
        # 0.0 signals "not a real classification" — distinguishes stub output from
        # Phase 3's real model output, which will report its actual confidence.
        confidence=0.0,
    )


def _title_from_filename(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else "Untitled"


__all__ = ["classify", "slugify"]
