import dataclasses
import subprocess
from pathlib import Path

import frontmatter

from okeef import pipeline, review_queue
from okeef.config import Config
from okeef.git_ops import _git_executable


def test_process_file_stages_instead_of_filing(bundle_root: Path, config: Config) -> None:
    review_config = dataclasses.replace(config, auto_commit=False)
    source = bundle_root / "_inbox" / "Draft Note.txt"
    source.write_text("Some draft content.", encoding="utf-8")

    result = pipeline.process_file(source, review_config)

    assert result.parent == bundle_root / "_staging"
    assert not source.exists()  # moved out of _inbox into staging
    assert (result / "draft.md").exists()
    assert (result / "proposal.json").exists()
    assert list(result.glob("original.*"))

    # nothing filed yet, nothing committed
    assert not (bundle_root / "Resources" / "unsorted").exists()
    git = _git_executable()
    log = subprocess.run(
        [git, "-C", str(bundle_root), "log", "--oneline"], capture_output=True, text=True
    )
    assert log.stdout.strip() == ""  # no commits yet


def test_approve_files_and_commits_staged_draft(bundle_root: Path, config: Config) -> None:
    review_config = dataclasses.replace(config, auto_commit=False)
    source = bundle_root / "_inbox" / "Draft Note.txt"
    source.write_text("Some draft content.", encoding="utf-8")
    staging_dir = pipeline.process_file(source, review_config)
    staging_id = staging_dir.name

    result = pipeline.approve(staging_id, review_config, approved_by="tester")

    assert result.exists()
    assert result.parent == bundle_root / "Resources" / "unsorted"
    assert not staging_dir.exists()  # cleaned up after approval

    post = frontmatter.load(result)
    assert post.metadata["title"] == "Draft Note"

    git = _git_executable()
    log = subprocess.run(
        [git, "-C", str(bundle_root), "log", "-1", "--format=%B"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Reviewed: true" in log.stdout
    assert "Approved-By: tester" in log.stdout


def test_hand_edited_title_and_bucket_are_respected_on_approve(
    bundle_root: Path, config: Config
) -> None:
    review_config = dataclasses.replace(config, auto_commit=False)
    source = bundle_root / "_inbox" / "Draft Note.txt"
    source.write_text("Some draft content.", encoding="utf-8")
    staging_dir = pipeline.process_file(source, review_config)
    staging_id = staging_dir.name

    draft_path = staging_dir / "draft.md"
    content = draft_path.read_text(encoding="utf-8")
    content = content.replace("title: Draft Note", "title: Corrected Title")
    content = content.replace("_para_bucket: Resources", "_para_bucket: Areas")
    draft_path.write_text(content, encoding="utf-8")

    result = pipeline.approve(staging_id, review_config)

    assert result.parent == bundle_root / "Areas" / "unsorted"
    post = frontmatter.load(result)
    assert post.metadata["title"] == "Corrected Title"


def test_list_staged(bundle_root: Path, config: Config) -> None:
    review_config = dataclasses.replace(config, auto_commit=False)
    for name in ["one.txt", "two.txt"]:
        source = bundle_root / "_inbox" / name
        source.write_text("content", encoding="utf-8")
        pipeline.process_file(source, review_config)

    ids = review_queue.list_staged(bundle_root)
    assert len(ids) == 2
