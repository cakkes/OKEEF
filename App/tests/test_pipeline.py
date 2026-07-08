from pathlib import Path

import frontmatter

from okeef import pipeline
from okeef.config import Config


def test_process_file_writes_conformant_okf_doc(bundle_root: Path, config: Config) -> None:
    source = bundle_root / "_inbox" / "My Test Note.txt"
    source.write_text("This is the first line.\n\nMore content here.", encoding="utf-8")

    result = pipeline.process_file(source, config)

    assert result.exists()
    assert result.parent == bundle_root / "Resources" / "unsorted"
    assert not source.exists()  # moved out of _inbox

    post = frontmatter.load(result)
    assert post.metadata["type"] == "note"
    assert post.metadata["title"] == "My Test Note"
    assert "timestamp" in post.metadata
    assert "This is the first line." in post.content


def test_process_file_updates_indexes_and_log(bundle_root: Path, config: Config) -> None:
    source = bundle_root / "_inbox" / "note.txt"
    source.write_text("Hello world.", encoding="utf-8")

    result = pipeline.process_file(source, config)

    resources_index = (bundle_root / "Resources" / "index.md").read_text(encoding="utf-8")
    assert "unsorted" in resources_index

    unsorted_index = (bundle_root / "Resources" / "unsorted" / "index.md").read_text(
        encoding="utf-8"
    )
    assert result.name in unsorted_index or "Note" in unsorted_index

    log_content = (bundle_root / "log.md").read_text(encoding="utf-8")
    assert "Note" in log_content
    assert "Resources/note" in log_content


def test_process_file_commits_to_git(bundle_root: Path, config: Config) -> None:
    import subprocess

    from okeef.git_ops import _git_executable

    source = bundle_root / "_inbox" / "committed-note.txt"
    source.write_text("Content to be committed.", encoding="utf-8")

    pipeline.process_file(source, config)

    git = _git_executable()
    log = subprocess.run(
        [git, "-C", str(bundle_root), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ingest(resources): Committed Note" in log.stdout


def test_duplicate_titles_get_unique_filenames(bundle_root: Path, config: Config) -> None:
    for i in range(2):
        source = bundle_root / "_inbox" / f"dup{i}.txt"
        source.write_text("Same Title\ncontent", encoding="utf-8")
        # force identical classification output by reusing the same filename stem
        source = source.rename(bundle_root / "_inbox" / "dup.txt")
        pipeline.process_file(source, config)

    written = sorted((bundle_root / "Resources" / "unsorted").glob("dup*.md"))
    assert len(written) == 2
