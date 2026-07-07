"""Orchestrates extract -> classify -> render -> write -> index -> commit.

finalize() is the seam Phase 4's review-mode "approve" flow will reuse: once a draft
has been written to its final PARA location, the index/commit tail is identical
regardless of whether it got there via AUTO_COMMIT=true (immediate) or via a human
approving a staged draft. Only the code that decides *when* to call write()/finalize()
differs between the two modes.
"""

from __future__ import annotations

from pathlib import Path

from . import bundle_index, classify, extract, git_ops, okf_writer
from .config import Config
from .models import Classification


def process_file(source_path: Path, config: Config) -> Path:
    text = extract.extract_text(source_path)
    classification = classify.classify(source_path, text)
    doc = okf_writer.render(source_path, text, classification)
    concept_path, attachment_path = okf_writer.write(doc, source_path, config.bundle_root)
    written = [concept_path] + ([attachment_path] if attachment_path else [])
    return finalize(written, concept_path, classification, config)


def finalize(
    written_paths: list[Path],
    concept_path: Path,
    classification: Classification,
    config: Config,
) -> Path:
    index_paths = bundle_index.update_after_write(concept_path, config.bundle_root, classification)
    if config.auto_commit:
        message = _commit_message(classification, concept_path)
        git_ops.commit_files(config.bundle_root, written_paths + index_paths, message)
    return concept_path


def _commit_message(classification: Classification, concept_path: Path) -> str:
    bucket = classification.para_bucket.lower()
    lines = [
        f"ingest({bucket}): {classification.title}",
        "",
        f"Type: {classification.okf_type}",
        f"Tags: {', '.join(classification.tags)}",
        f"Confidence: {classification.confidence}",
        "",
        f"Source-File: {concept_path.name}",
        "Ingested-By: okeef-pipeline/0.1",
    ]
    return "\n".join(lines)
