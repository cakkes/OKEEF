from pathlib import Path

import frontmatter
import pytest

from okeef import pipeline
from okeef.config import Config


@pytest.fixture
def bundle_root(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    for bucket in ["Projects", "Areas", "Resources", "Archives"]:
        (root / bucket).mkdir(parents=True)
        (root / bucket / "index.md").write_text(
            f"# {bucket}\n\n<!-- OKEEF:AUTO-INDEX:START -->\n<!-- OKEEF:AUTO-INDEX:END -->\n",
            encoding="utf-8",
        )
    (root / "_inbox").mkdir()
    root_index = (
        "---\nokf_version: \"0.1\"\ntitle: Test Bundle\n---\n\n# Test Bundle\n"
    )
    (root / "index.md").write_text(root_index, encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    return root


@pytest.fixture
def config(bundle_root: Path) -> Config:
    return Config(
        bundle_root=bundle_root,
        auto_commit=False,  # keep the test independent of git
        para_buckets=["Projects", "Areas", "Resources", "Archives"],
        classify_model="stub",
        embed_model="stub",
        ollama_host="http://localhost:11434",
        chunk_size=800,
        chunk_overlap=150,
        openwebui_base_url="http://localhost:8080",
        openwebui_knowledge_id="",
    )


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


def test_duplicate_titles_get_unique_filenames(bundle_root: Path, config: Config) -> None:
    for i in range(2):
        source = bundle_root / "_inbox" / f"dup{i}.txt"
        source.write_text("Same Title\ncontent", encoding="utf-8")
        # force identical classification output by reusing the same filename stem
        source = source.rename(bundle_root / "_inbox" / "dup.txt")
        pipeline.process_file(source, config)

    written = sorted((bundle_root / "Resources" / "unsorted").glob("dup*.md"))
    assert len(written) == 2
