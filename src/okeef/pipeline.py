"""Orchestrates extract -> classify -> render -> write/stage -> index -> commit.

finalize() is the seam the review-mode "approve" flow reuses: once a draft has been
written to its final PARA location, the index/commit tail is identical regardless of
whether it got there via AUTO_COMMIT=true (immediate, in process_file) or via a human
approving a staged draft (approve()). Only the code that decides *when* to call
write()/finalize() -- and whether to route through _staging/ first -- differs.
"""

from __future__ import annotations

from pathlib import Path

from . import bundle_index, classify, extract, git_ops, okf_writer, review_queue
from .config import Config
from .models import Classification


def process_file(source_path: Path, config: Config) -> Path:
    """Returns the final concept doc path when AUTO_COMMIT=true, or the _staging/<id>/
    directory when AUTO_COMMIT=false (nothing is filed/committed until approve()).
    """
    text = extract.extract_text(source_path)
    classification = classify.classify(source_path, text, config)
    doc = okf_writer.render(source_path, text, classification)

    if not config.auto_commit:
        staging_id = review_queue.stage_draft(doc, source_path, config.bundle_root)
        return config.bundle_root / "_staging" / staging_id

    concept_path, attachment_path = okf_writer.write(doc, source_path, config.bundle_root)
    written = [concept_path] + ([attachment_path] if attachment_path else [])
    return finalize(written, concept_path, classification, config, commit=True)


def approve(staging_id: str, config: Config, approved_by: str | None = None) -> Path:
    """Files and commits a draft that was staged under AUTO_COMMIT=false, after a
    human has reviewed it (and optionally hand-edited _staging/<id>/draft.md).
    """
    staged = review_queue.load_staged(staging_id, config.bundle_root)
    concept_path, attachment_path = okf_writer.write(
        staged.doc, staged.original_source_path, config.bundle_root
    )
    written = [concept_path] + ([attachment_path] if attachment_path else [])
    extra_trailers = {"Reviewed": "true"}
    if approved_by:
        extra_trailers["Approved-By"] = approved_by
    result = finalize(
        written, concept_path, staged.classification, config, commit=True, extra_trailers=extra_trailers
    )
    review_queue.cleanup_staged(staging_id, config.bundle_root)
    return result


def finalize(
    written_paths: list[Path],
    concept_path: Path,
    classification: Classification,
    config: Config,
    commit: bool,
    extra_trailers: dict[str, str] | None = None,
) -> Path:
    index_paths = bundle_index.update_after_write(concept_path, config.bundle_root, classification)
    if commit:
        message = _commit_message(classification, concept_path, extra_trailers or {})
        git_ops.commit_files(config.bundle_root, written_paths + index_paths, message)
    return concept_path


def _commit_message(
    classification: Classification, concept_path: Path, extra_trailers: dict[str, str]
) -> str:
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
    for key, value in extra_trailers.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
