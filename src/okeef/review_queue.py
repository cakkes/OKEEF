"""Implements the AUTO_COMMIT=false review flow: stage_draft() writes a rendered
OKFDoc to _staging/<id>/ instead of filing it, and approve() (called once a human has
reviewed/optionally hand-edited the staged draft) runs it through the exact same
write -> index -> commit tail that AUTO_COMMIT=true uses immediately.

para_bucket/folder_slug are stored as staging-only frontmatter keys (_para_bucket,
_folder_slug) in draft.md itself, so a human reviewing the draft can correct the
proposed filing location just by editing that one file -- no separate tool needed.
They're popped back out (not written to the final concept doc) once approved.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import frontmatter as frontmatter_lib
import yaml

from .models import Classification
from .okf_writer import OKFDoc

DRAFT_FILENAME = "draft.md"
PROPOSAL_FILENAME = "proposal.json"


class StagingError(Exception):
    pass


def stage_draft(doc: OKFDoc, source_path: Path, bundle_root: Path) -> str:
    staging_root = bundle_root / "_staging"
    staging_id = uuid.uuid4().hex[:8]
    staging_dir = staging_root / staging_id
    while staging_dir.exists():
        staging_id = uuid.uuid4().hex[:8]
        staging_dir = staging_root / staging_id
    staging_dir.mkdir(parents=True)

    c = doc.classification
    staged_frontmatter = {**doc.frontmatter, "_para_bucket": c.para_bucket, "_folder_slug": c.folder_slug}
    draft_content = (
        "---\n"
        + yaml.safe_dump(staged_frontmatter, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + doc.body
    )
    (staging_dir / DRAFT_FILENAME).write_text(draft_content, encoding="utf-8")

    proposal = {
        "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "original_filename": source_path.name,
        "confidence": c.confidence,
        "para_bucket": c.para_bucket,
        "folder_slug": c.folder_slug,
        "okf_type": c.okf_type,
        "title": c.title,
    }
    (staging_dir / PROPOSAL_FILENAME).write_text(json.dumps(proposal, indent=2), encoding="utf-8")

    if source_path.exists():
        original_copy = staging_dir / f"original{source_path.suffix.lower()}"
        shutil.move(str(source_path), str(original_copy))

    return staging_id


@dataclass
class StagedDraft:
    doc: OKFDoc
    classification: Classification
    original_source_path: Path


def load_staged(staging_id: str, bundle_root: Path) -> StagedDraft:
    staging_dir = bundle_root / "_staging" / staging_id
    draft_path = staging_dir / DRAFT_FILENAME
    proposal_path = staging_dir / PROPOSAL_FILENAME
    if not draft_path.exists() or not proposal_path.exists():
        raise StagingError(f"No staged draft found for id {staging_id!r}")

    post = frontmatter_lib.load(draft_path)
    metadata = dict(post.metadata)
    para_bucket = metadata.pop("_para_bucket", None)
    folder_slug = metadata.pop("_folder_slug", None)
    if not para_bucket or not folder_slug:
        raise StagingError(
            f"Staged draft {staging_id!r} is missing _para_bucket/_folder_slug frontmatter -- "
            "don't remove these staging-only fields when hand-editing a draft."
        )

    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))

    classification = Classification(
        para_bucket=para_bucket,
        okf_type=metadata.get("type", proposal.get("okf_type", "note")),
        title=metadata.get("title", proposal.get("title", "Untitled")),
        description=metadata.get("description", ""),
        summary="",  # never re-read after the initial render; already embedded in the body
        tags=metadata.get("tags") or ["unclassified"],
        folder_slug=folder_slug,
        confidence=proposal.get("confidence", 0.0),
    )

    doc = OKFDoc(frontmatter=metadata, body=post.content, classification=classification)

    originals = list(staging_dir.glob("original.*"))
    original_source_path = originals[0] if originals else draft_path

    return StagedDraft(doc=doc, classification=classification, original_source_path=original_source_path)


def cleanup_staged(staging_id: str, bundle_root: Path) -> None:
    staging_dir = bundle_root / "_staging" / staging_id
    if staging_dir.exists():
        shutil.rmtree(staging_dir)


def list_staged(bundle_root: Path) -> list[str]:
    staging_root = bundle_root / "_staging"
    if not staging_root.exists():
        return []
    return sorted(
        p.name for p in staging_root.iterdir() if p.is_dir() and (p / DRAFT_FILENAME).exists()
    )
