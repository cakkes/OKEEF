"""Scans the PARA folders for files a human filed by hand (bypassing _inbox) that
were never run through the pipeline, and OKF-ifies them in place.

Unlike the _inbox flow, placement here is never reclassified: whatever bucket/
folder the human already put the file in is where the resulting concept doc stays
(see okf_writer.write_in_place()). The classifier still runs, just to generate
title/description/tags/type, not to decide where the file belongs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import frontmatter

from . import classify, extract, okf_writer, pipeline, watcher
from .config import Config

logger = logging.getLogger("okeef.para_scan")


def find_candidates(config: Config) -> list[Path]:
    """Recursively walks each PARA bucket for files that look like they've never
    been through the pipeline: a supported extension, not index.md/log.md, not an
    existing '<slug>.original.ext' attachment sibling, and -- for .md files -- no
    `type` frontmatter key (the one OKF-required field; okf_writer.render() always
    writes it, so its absence reliably means "never processed").
    """
    candidates: list[Path] = []
    for bucket in config.para_buckets:
        bucket_dir = config.bundle_root / bucket
        if not bucket_dir.exists():
            continue
        for path in sorted(bucket_dir.rglob("*")):
            if not path.is_file() or path.name in {"index.md", "log.md"}:
                continue
            if path.suffix.lower() not in extract.SUPPORTED_EXTENSIONS:
                continue
            if path.stem.endswith(".original"):
                continue  # an existing concept doc's attachment sibling
            if path.suffix.lower() == ".md" and _already_okf(path):
                continue
            candidates.append(path)
    return candidates


def _already_okf(path: Path) -> bool:
    try:
        return "type" in frontmatter.load(path).metadata
    except Exception:
        return False


def scan(config: Config) -> list[Path]:
    """OKF-ifies every candidate in place and commits (+ attempts sync) each one
    via the same pipeline.finalize() tail the _inbox flow uses. Always writes and
    commits immediately -- scanned files don't participate in the AUTO_COMMIT=false
    staging flow, which has no notion of "write in place".
    """
    written: list[Path] = []
    for source_path in find_candidates(config):
        try:
            text = extract.extract_text(source_path)
            classification = classify.classify(source_path, text, config)
            # Placement is never reclassified (see module docstring), so the commit
            # message should reflect the bucket the file actually landed in, not
            # whatever bucket the classifier guessed.
            actual_bucket = source_path.relative_to(config.bundle_root).parts[0]
            classification = classification.model_copy(update={"para_bucket": actual_bucket})
            doc = okf_writer.render(source_path, text, classification)
            concept_path, attachment_path = okf_writer.write_in_place(doc, source_path)
            touched = [concept_path] + ([attachment_path] if attachment_path else [])
            pipeline.finalize(touched, concept_path, classification, config, commit=True)
            written.append(concept_path)
        except extract.ExtractionError as exc:
            watcher._quarantine(source_path, config, str(exc))
        except Exception as exc:  # noqa: BLE001 -- one bad file shouldn't abort the whole scan
            logger.exception("Failed to process %s", source_path)
            watcher._quarantine(source_path, config, f"Unexpected error: {exc}")
    return written
