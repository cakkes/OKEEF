"""Maintains index.md (per-folder, auto-generated section) and the bundle-root log.md
after a concept doc is written. Regenerates every ancestor folder's index up to the
bundle root, since a newly-created subfolder needs to appear in its parent's listing too.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from .models import Classification

_AUTO_START = "<!-- OKEEF:AUTO-INDEX:START -->"
_AUTO_END = "<!-- OKEEF:AUTO-INDEX:END -->"
_AUTO_BLOCK_RE = re.compile(
    re.escape(_AUTO_START) + r".*?" + re.escape(_AUTO_END), re.DOTALL
)


def update_after_write(
    concept_path: Path, bundle_root: Path, classification: Classification
) -> list[Path]:
    """Regenerates index.md for concept_path's folder and every ancestor up to
    bundle_root, then appends a log.md entry. Returns every file touched.
    """
    # The bundle-root index.md is hand-curated (it's the only file allowed to declare
    # okf_version, and typically carries prose like "# Sections"/"# How this bundle is
    # built") -- so ancestor regeneration stops one level below it, never touching it.
    touched: list[Path] = []
    folder = concept_path.parent
    while folder != bundle_root:
        touched.append(_regenerate_index(folder, bundle_root))
        folder = folder.parent

    touched.append(_append_log(bundle_root, concept_path, classification))
    return touched


def _regenerate_index(folder: Path, bundle_root: Path) -> Path:
    index_path = folder / "index.md"
    if not index_path.exists():
        title = folder.name.replace("-", " ").replace("_", " ").title()
        index_path.write_text(
            f"# {title}\n\n{_AUTO_START}\n{_AUTO_END}\n", encoding="utf-8"
        )

    content = index_path.read_text(encoding="utf-8")
    entries = _collect_entries(folder, bundle_root)
    block = _AUTO_START + ("\n" + "\n".join(entries) + "\n" if entries else "\n") + _AUTO_END

    if _AUTO_BLOCK_RE.search(content):
        new_content = _AUTO_BLOCK_RE.sub(lambda _match: block, content)
    else:
        new_content = content.rstrip() + f"\n\n{block}\n"

    index_path.write_text(new_content, encoding="utf-8")
    return index_path


def _collect_entries(folder: Path, bundle_root: Path) -> list[str]:
    entries = []
    for child in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if child.name in {"index.md", "log.md"} or child.name.startswith("."):
            continue
        if child.is_dir():
            child_index = child / "index.md"
            if child_index.exists():
                label = _first_h1(child_index) or child.name
                entries.append(f"* [{label}]({_bundle_link(child_index, bundle_root)})")
        elif child.suffix == ".md":
            post = frontmatter.load(child)
            title = post.metadata.get("title", child.stem)
            description = post.metadata.get("description", "")
            suffix = f" - {description}" if description else ""
            entries.append(f"* [{title}]({_bundle_link(child, bundle_root)}){suffix}")
    return entries


def _first_h1(index_path: Path) -> str | None:
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _bundle_link(path: Path, bundle_root: Path) -> str:
    return f"/{path.relative_to(bundle_root).as_posix()}"


def _append_log(bundle_root: Path, concept_path: Path, classification: Classification) -> Path:
    log_path = bundle_root / "log.md"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    heading = f"## {today}"
    rel = _bundle_link(concept_path, bundle_root)
    entry = f"* **Creation**: [{classification.title}]({rel}) ({classification.para_bucket}/{classification.okf_type})"

    content = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Log\n"
    lines = content.splitlines()

    if heading in lines:
        idx = lines.index(heading)
        lines.insert(idx + 1, entry)
    else:
        insert_at = 1 if lines and lines[0].startswith("# ") else 0
        # skip a blank line right after the H1, if present
        if insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        lines[insert_at:insert_at] = [heading, entry, ""]

    log_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return log_path
