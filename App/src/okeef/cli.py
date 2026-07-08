"""OKEEF command-line entry point. `reindex` is added in a later phase."""

from __future__ import annotations

from pathlib import Path

import click

from . import openwebui_sync, para_scan, pipeline, review_queue, watcher
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
    ids = review_queue.list_staged(config.app_root)
    if not ids:
        click.echo("Nothing staged for review.")
        return
    for staging_id in ids:
        staged = review_queue.load_staged(staging_id, config.app_root)
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


@main.command("scan-para")
def scan_para_cmd() -> None:
    """Scan the PARA folders for hand-added files never run through the pipeline,
    and OKF-ify them in place (bucket/folder as filed by hand, not reclassified)."""
    config = load_config()
    written = para_scan.scan(config)
    if not written:
        click.echo("Nothing to process.")
        return
    for path in written:
        click.echo(f"Filed: {path.relative_to(config.bundle_root)}")


@main.command("resync")
def resync_cmd() -> None:
    """Bulk re-sync every concept doc in the bundle to Open WebUI's Knowledge collection."""
    config = load_config()
    synced = openwebui_sync.resync_all(config)
    click.echo(f"Synced {len(synced)} file(s).")


if __name__ == "__main__":
    main()
