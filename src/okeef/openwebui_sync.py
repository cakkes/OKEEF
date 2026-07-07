"""Pushes a concept doc into Open WebUI's Knowledge collection via its REST API,
called right after each git commit. Preferred over Open WebUI's client-side "Sync
Directory" UI action (needs a human at the browser) and over the bulk oikb CLI tool
(better suited to one-time imports) for incremental, per-file pushes from the pipeline.

Authenticates by signing in with the admin account (WEBUI_ADMIN_EMAIL/PASSWORD),
getting a session JWT, rather than using a generated API key: API keys were found
not to reliably survive an Open WebUI restart on the installed version (the
ENABLE_API_KEYS setting and/or the stored key itself would silently reset), while
sign-in is simple and robust, and reuses credentials already needed for the
headless admin bootstrap.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

from .config import Config

_POLL_INTERVAL = 1.0
_POLL_TIMEOUT = 60.0


class SyncError(Exception):
    pass


def _check_configured(config: Config) -> None:
    if not config.openwebui_admin_email or not config.openwebui_admin_password:
        raise SyncError(
            "Open WebUI admin credentials are not configured "
            "(set WEBUI_ADMIN_EMAIL/WEBUI_ADMIN_PASSWORD in .env)"
        )
    if not config.openwebui_knowledge_id:
        raise SyncError("openwebui_knowledge_id is not configured (set OPENWEBUI_KNOWLEDGE_ID in .env)")


def _sign_in(config: Config) -> str:
    resp = requests.post(
        f"{config.openwebui_base_url}/api/v1/auths/signin",
        json={"email": config.openwebui_admin_email, "password": config.openwebui_admin_password},
        timeout=15,
    )
    if resp.status_code != 200:
        raise SyncError(f"Open WebUI sign-in failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]


def sync_file(concept_path: Path, config: Config) -> str:
    """Uploads concept_path to Open WebUI, waits for it to finish processing
    (chunking + embedding), and attaches it to the configured Knowledge collection.
    Returns the Open WebUI file_id.
    """
    _check_configured(config)
    token = _sign_in(config)
    return _sync_with_token(concept_path, config, token)


def _sync_with_token(concept_path: Path, config: Config, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    file_id = _upload_file(concept_path, config, headers)
    _wait_for_processing(file_id, config, headers)
    _attach_to_knowledge(file_id, config, headers)
    return file_id


def _upload_file(concept_path: Path, config: Config, headers: dict) -> str:
    url = f"{config.openwebui_base_url}/api/v1/files/"
    with open(concept_path, "rb") as fh:
        files = {"file": (concept_path.name, fh, "text/markdown")}
        resp = requests.post(url, headers=headers, files=files, timeout=30)
    if resp.status_code != 200:
        raise SyncError(f"Upload failed for {concept_path.name}: {resp.status_code} {resp.text}")
    return resp.json()["id"]


def _wait_for_processing(file_id: str, config: Config, headers: dict) -> None:
    url = f"{config.openwebui_base_url}/api/v1/files/{file_id}/process/status"
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            status = resp.json().get("status")
            if status == "completed":
                return
            if status == "failed":
                raise SyncError(f"Open WebUI failed to process file {file_id}")
        time.sleep(_POLL_INTERVAL)
    raise SyncError(f"Timed out waiting for Open WebUI to process file {file_id}")


def _attach_to_knowledge(file_id: str, config: Config, headers: dict) -> None:
    url = f"{config.openwebui_base_url}/api/v1/knowledge/{config.openwebui_knowledge_id}/file/add"
    resp = requests.post(url, headers=headers, json={"file_id": file_id}, timeout=30)
    if resp.status_code != 200:
        raise SyncError(f"Failed to attach file {file_id} to knowledge collection: {resp.status_code} {resp.text}")


def resync_all(config: Config) -> list[Path]:
    """Syncs every concept doc under the PARA bucket folders (Projects/Areas/
    Resources/Archives) to Open WebUI. Used both for the initial backfill of content
    ingested before Open WebUI was set up, and as a general maintenance re-sync (e.g.
    after Open WebUI's data dir was wiped/rebuilt).

    Deliberately scoped to just the PARA buckets rather than rglob-ing the whole
    bundle_root: .venv/.venv-webui (which live inside the bundle root) contain
    thousands of unrelated .md files from installed Python packages.

    Signs in once and reuses the token across every file, rather than calling
    sync_file() per file (which would sign in per file) -- resync can process many
    files in one run.
    """
    _check_configured(config)
    token = _sign_in(config)

    synced = []
    for bucket in config.para_buckets:
        bucket_dir = config.bundle_root / bucket
        if not bucket_dir.exists():
            continue
        for path in sorted(bucket_dir.rglob("*.md")):
            if path.name in {"index.md", "log.md"}:
                continue
            _sync_with_token(path, config, token)
            synced.append(path)
    return synced
