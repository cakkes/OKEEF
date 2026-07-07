"""Watches _inbox for new files and runs them through the pipeline.

Uses watchdog's native Observer (Windows ReadDirectoryChangesW under the hood) rather
than polling -- event-driven, near-zero idle cost, the right tradeoff on a laptop.
Two gaps that event-driven watching alone doesn't cover, both handled explicitly:
  - Partial writes: Explorer copy/drag-drop fires multiple events before a file is
    fully written. We debounce per-path and verify size-stability + an exclusive-open
    probe before treating a file as ready.
  - Watcher-was-offline gaps (laptop asleep, watcher crashed, not started yet): a
    synchronous startup catch-up scan sweeps _inbox once before the live Observer
    starts, so nothing dropped during a gap is silently missed.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import extract, pipeline
from .config import Config, load_config

logger = logging.getLogger("okeef.watcher")

IGNORE_SUFFIXES = {".tmp", ".crdownload"}
IGNORE_NAMES = {"desktop.ini", "thumbs.db"}

DEBOUNCE_INTERVAL = 2.0  # seconds of quiescence required before treating a file as ready
STABILITY_SETTLE = 0.2  # seconds between the two size checks within one stability probe
MAX_WAIT = 30.0  # seconds before giving up and quarantining as "never stabilized"


def _should_ignore(path: Path) -> bool:
    name = path.name
    if name.lower() in IGNORE_NAMES:
        return True
    if name.startswith("~$") or name.startswith("."):
        return True
    if path.suffix.lower() in IGNORE_SUFFIXES:
        return True
    return False


def _is_stable(path: Path) -> bool:
    try:
        size1 = path.stat().st_size
    except FileNotFoundError:
        return False

    try:
        with open(path, "rb"):
            pass
    except OSError:
        return False

    # If the file is writable, also probe for an exclusive write-open: a process
    # still copying/writing to it typically holds a share mode that blocks this on
    # Windows. Skip this probe for read-only files, where it would always fail for
    # reasons unrelated to write-in-progress.
    if os.access(path, os.W_OK):
        try:
            with open(path, "r+b"):
                pass
        except OSError:
            return False

    time.sleep(STABILITY_SETTLE)
    try:
        size2 = path.stat().st_size
    except FileNotFoundError:
        return False
    return size1 == size2


def _quarantine(path: Path, config: Config, reason: str) -> None:
    if not path.exists():
        return
    quarantine_dir = config.bundle_root / "_quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    target = quarantine_dir / path.name
    n = 2
    while target.exists():
        target = quarantine_dir / f"{path.stem}-{n}{path.suffix}"
        n += 1

    shutil.move(str(path), str(target))
    (target.parent / f"{target.name}.reason.txt").write_text(reason, encoding="utf-8")
    logger.warning("Quarantined %s: %s", path.name, reason)


def _process(path: Path, config: Config) -> None:
    if not path.exists():
        return
    try:
        result = pipeline.process_file(path, config)
        rel = result.relative_to(config.bundle_root)
        if config.auto_commit:
            logger.info("Ingested %s -> %s", path.name, rel)
        else:
            logger.info("Staged %s for review -> %s", path.name, rel)
    except extract.ExtractionError as exc:
        _quarantine(path, config, str(exc))
    except Exception as exc:  # noqa: BLE001 -- any pipeline failure quarantines, never crashes the watcher
        logger.exception("Failed to process %s", path)
        _quarantine(path, config, f"Unexpected error: {exc}")


class InboxHandler(FileSystemEventHandler):
    def __init__(self, config: Config):
        self.config = config
        self._pending: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        self._handle(event)

    def on_modified(self, event):
        self._handle(event)

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule(Path(event.dest_path))

    def _handle(self, event):
        if event.is_directory:
            return
        self._schedule(Path(event.src_path))

    def _schedule(self, path: Path, waited: float = 0.0) -> None:
        if _should_ignore(path):
            return
        with self._lock:
            existing = self._pending.pop(path, None)
            if existing:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_INTERVAL, self._check_stable, args=(path, waited))
            timer.daemon = True
            self._pending[path] = timer
            timer.start()

    def _check_stable(self, path: Path, waited: float) -> None:
        with self._lock:
            self._pending.pop(path, None)

        if not path.exists() or _should_ignore(path):
            return

        if not _is_stable(path):
            waited += DEBOUNCE_INTERVAL
            if waited >= MAX_WAIT:
                _quarantine(path, self.config, "File never stabilized (still changing after 30s)")
                return
            self._schedule(path, waited)
            return

        _process(path, self.config)


def catch_up_scan(config: Config) -> None:
    inbox = config.bundle_root / "_inbox"
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or _should_ignore(path):
            continue
        if _wait_until_stable(path):
            _process(path, config)
        else:
            _quarantine(path, config, "File never stabilized during startup catch-up scan")


def _wait_until_stable(path: Path, max_wait: float = MAX_WAIT) -> bool:
    waited = 0.0
    while waited < max_wait:
        if not path.exists():
            return False
        if _is_stable(path):
            return True
        time.sleep(DEBOUNCE_INTERVAL)
        waited += DEBOUNCE_INTERVAL
    return False


def _configure_logging(config: Config) -> None:
    logs_dir = config.bundle_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / "watcher.log", encoding="utf-8"),
        ],
    )


def run(config: Config | None = None) -> None:
    config = config or load_config()
    _configure_logging(config)

    inbox = config.bundle_root / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    logger.info("Startup catch-up scan: %s", inbox)
    catch_up_scan(config)

    handler = InboxHandler(config)
    observer = Observer()
    observer.schedule(handler, str(inbox), recursive=False)
    observer.start()
    logger.info("Watching %s", inbox)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    run()
