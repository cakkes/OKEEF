import subprocess
from pathlib import Path

import frontmatter

from okeef import para_scan
from okeef.config import Config
from okeef.git_ops import _git_executable


def test_find_candidates_skips_already_okf_and_attachments(bundle_root: Path, config: Config) -> None:
    area_dir = bundle_root / "Areas" / "some-folder"
    area_dir.mkdir(parents=True)

    raw = area_dir / "raw-note.txt"
    raw.write_text("Some hand-filed content.", encoding="utf-8")

    already_okf = area_dir / "already-done.md"
    already_okf.write_text("---\ntype: note\ntitle: Done\n---\n\nbody", encoding="utf-8")

    not_okf_md = area_dir / "plain-note.md"
    not_okf_md.write_text("Just a plain markdown note, no frontmatter.", encoding="utf-8")

    attachment = area_dir / "something.original.pdf"
    attachment.write_bytes(b"%PDF-1.4 fake")

    candidates = para_scan.find_candidates(config)

    assert raw in candidates
    assert not_okf_md in candidates
    assert already_okf not in candidates
    assert attachment not in candidates


def test_scan_writes_in_place_and_commits(repo_root: Path, bundle_root: Path, config: Config) -> None:
    area_dir = bundle_root / "Areas" / "hand-filed"
    area_dir.mkdir(parents=True)
    raw = area_dir / "My Manual Note.txt"
    raw.write_text("Content the user filed by hand.", encoding="utf-8")

    written = para_scan.scan(config)

    assert len(written) == 1
    concept_path = written[0]
    assert concept_path.parent == area_dir  # stayed in the folder the user chose
    assert not raw.exists()  # original replaced

    post = frontmatter.load(concept_path)
    assert post.metadata["type"] == "note"

    git = _git_executable()
    log = subprocess.run(
        [git, "-C", str(repo_root), "log", "--oneline"], capture_output=True, text=True, check=True
    )
    assert "ingest(areas):" in log.stdout
