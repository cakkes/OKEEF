"""OKEEF command-line entry point. `process-file` is the only command in Phase 1;
`watch`, `approve`, `reindex`, and `resync` are added in their respective build phases.
"""

from __future__ import annotations

from pathlib import Path

import click

from . import pipeline
from .config import load_config


@click.group()
def main() -> None:
    """OKEEF -- local OKF/PARA knowledgebase pipeline."""


@main.command("process-file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def process_file_cmd(path: Path) -> None:
    """Run a single file through extract -> classify -> file -> commit."""
    config = load_config()
    result = pipeline.process_file(path.resolve(), config)
    click.echo(f"Filed: {result.relative_to(config.bundle_root)}")


if __name__ == "__main__":
    main()
