"""Renders a Classification + extracted text into a conformant OKF concept document,
and writes it (plus any non-markdown attachment) into the bundle.

render() and write() are kept separate on purpose: Phase 4's review-mode toggle needs
to render a draft without committing it to its final PARA location, so it can stage the
same OKFDoc in _staging/ instead. write() is the only piece that changes between modes.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .models import Classification
from .slug import slugify

# Non-markdown originals are kept as a sibling attachment next to the concept doc;
# .txt/.md sources become the concept doc's body directly, so no attachment is needed.
ATTACHMENT_EXTENSIONS = {".pdf", ".docx"}


@dataclass
class OKFDoc:
    frontmatter: dict
    body: str
    classification: Classification


def render(source_path: Path, text: str, classification: Classification) -> OKFDoc:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter = {
        "type": classification.okf_type,
        "title": classification.title,
        "description": classification.description,
        "tags": classification.tags,
        "timestamp": timestamp,
        "source_file": source_path.name,
        "ingested_by": "okeef-pipeline/0.1",
    }
    body = (
        f"# Summary\n\n{classification.summary}\n\n"
        f"# Content\n\n{text.strip()}\n\n"
        f"# Source\n\nOriginal file: `{source_path.name}`\n"
        f"Ingested: {timestamp}\n"
    )
    return OKFDoc(frontmatter=frontmatter, body=body, classification=classification)


def write(doc: OKFDoc, source_path: Path, bundle_root: Path) -> tuple[Path, Path | None]:
    """Writes the concept doc (and attachment, if any) into its final PARA location,
    and removes the source file if it was sitting in _inbox. Returns
    (concept_path, attachment_path_or_None).
    """
    c = doc.classification
    target_dir = bundle_root / c.para_bucket / c.folder_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    concept_path = _unique_path(target_dir, slugify(c.title), ".md")

    attachment_path = None
    suffix = source_path.suffix.lower()
    if suffix in ATTACHMENT_EXTENSIONS:
        attachment_path = target_dir / f"{concept_path.stem}.original{suffix}"
        shutil.copy2(source_path, attachment_path)
        doc.frontmatter["source_file"] = attachment_path.name

    content = (
        "---\n"
        + yaml.safe_dump(doc.frontmatter, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + doc.body
    )
    concept_path.write_text(content, encoding="utf-8")

    inbox_dir = bundle_root / "_inbox"
    if source_path.parent == inbox_dir and source_path.exists():
        source_path.unlink()

    return concept_path, attachment_path


def _unique_path(target_dir: Path, base_slug: str, suffix: str) -> Path:
    candidate = target_dir / f"{base_slug}{suffix}"
    n = 2
    while candidate.exists():
        candidate = target_dir / f"{base_slug}-{n}{suffix}"
        n += 1
    return candidate
