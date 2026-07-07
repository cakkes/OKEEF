"""OKEEF command-line entry point. `reindex` and `resync` are added in later phases."""

from __future__ import annotations

from pathlib import Path

import click

from . import pipeline, review_queue, watcher
from .config import load_config


@click.group()
def main() -> None:
    """OKEEF -- local OKF/PARA knowledgebase pipeline."""


@main.command("process-file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def process_file_cmd(path: Path) -> None:
    """Run a single file through extract -> classify -> file/stage -> commit."""
    config = load_config()
    result = pipeline.process_file(path.resolve(), config)
    if config.auto_commit:
        click.echo(f"Filed: {result.relative_to(config.bundle_root)}")
    else:
        staging_id = result.name
        click.echo(
            f"Staged for review: {staging_id}\n"
            f"  Review/edit: _staging/{staging_id}/draft.md\n"
            f"  Then run: okeef approve {staging_id}"
        )


@main.command("watch")
def watch_cmd() -> None:
    """Run the startup catch-up scan, then watch _inbox for new files (foreground; Ctrl+C to stop)."""
    watcher.run()


@main.command("list-staged")
def list_staged_cmd() -> None:
    """List drafts waiting for review in _staging/ (only relevant when AUTO_COMMIT=false)."""
    config = load_config()
    ids = review_queue.list_staged(config.bundle_root)
    if not ids:
        click.echo("Nothing staged for review.")
        return
    for staging_id in ids:
        staged = review_queue.load_staged(staging_id, config.bundle_root)
        c = staged.classification
        click.echo(
            f"{staging_id}  {c.para_bucket}/{c.folder_slug}  {c.title!r}  (confidence {c.confidence:.2f})"
        )


@main.command("approve")
@click.argument("staging_id")
@click.option("--approved-by", default=None, help="Name to record in the commit trailer.")
def approve_cmd(staging_id: str, approved_by: str | None) -> None:
    """File and commit a staged draft from _staging/<id>/ after reviewing it."""
    config = load_config()
    result = pipeline.approve(staging_id, config, approved_by=approved_by)
    click.echo(f"Filed: {result.relative_to(config.bundle_root)}")


if __name__ == "__main__":
    main()
