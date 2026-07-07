import dataclasses
from pathlib import Path

import pytest

from okeef import openwebui_sync
from okeef.config import Config


@pytest.fixture
def sync_config(config: Config) -> Config:
    return dataclasses.replace(
        config,
        openwebui_api_key="test-api-key",
        openwebui_knowledge_id="test-knowledge-id",
    )


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json_data


def test_sync_file_success(tmp_path: Path, sync_config: Config, monkeypatch) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("---\ntitle: Note\n---\n\nbody", encoding="utf-8")

    calls = []

    def fake_post(url, headers=None, files=None, json=None, timeout=None):
        calls.append(("POST", url, files is not None, json))
        if url.endswith("/api/v1/files/"):
            return _FakeResponse(200, {"id": "file-123"})
        if url.endswith("/file/add"):
            return _FakeResponse(200, {"id": "test-knowledge-id"})
        raise AssertionError(f"unexpected POST {url}")

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, None, None))
        return _FakeResponse(200, {"status": "completed"})

    monkeypatch.setattr(openwebui_sync.requests, "post", fake_post)
    monkeypatch.setattr(openwebui_sync.requests, "get", fake_get)

    file_id = openwebui_sync.sync_file(concept_path, sync_config)

    assert file_id == "file-123"
    assert calls[0] == ("POST", "http://localhost:8080/api/v1/files/", True, None)
    assert calls[1][0] == "GET"
    assert calls[2] == (
        "POST",
        "http://localhost:8080/api/v1/knowledge/test-knowledge-id/file/add",
        False,
        {"file_id": "file-123"},
    )


def test_sync_file_raises_without_credentials(tmp_path: Path, config: Config) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("content", encoding="utf-8")

    with pytest.raises(openwebui_sync.SyncError):
        openwebui_sync.sync_file(concept_path, config)  # api_key/knowledge_id empty


def test_sync_file_raises_on_processing_failure(tmp_path: Path, sync_config: Config, monkeypatch) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("content", encoding="utf-8")

    monkeypatch.setattr(
        openwebui_sync.requests, "post", lambda *a, **k: _FakeResponse(200, {"id": "file-123"})
    )
    monkeypatch.setattr(
        openwebui_sync.requests, "get", lambda *a, **k: _FakeResponse(200, {"status": "failed"})
    )

    with pytest.raises(openwebui_sync.SyncError):
        openwebui_sync.sync_file(concept_path, sync_config)


def test_resync_all_skips_reserved_files_and_dirs(bundle_root: Path, sync_config: Config, monkeypatch) -> None:
    concept = bundle_root / "Resources" / "note.md"
    concept.write_text("---\ntitle: Note\n---\n\nbody", encoding="utf-8")

    staged = bundle_root / "_staging" / "abc123"
    staged.mkdir(parents=True)
    (staged / "draft.md").write_text("---\ntitle: Draft\n---\n\nbody", encoding="utf-8")

    synced_paths = []
    monkeypatch.setattr(openwebui_sync, "sync_file", lambda path, cfg: synced_paths.append(path) or "id")

    result = openwebui_sync.resync_all(sync_config)

    assert concept in result
    assert all("index.md" not in str(p) and "log.md" not in str(p) for p in result)
    assert all("_staging" not in str(p) for p in result)


def test_resync_all_does_not_walk_venv_or_bundle_root(bundle_root: Path, sync_config: Config, monkeypatch) -> None:
    # Regression test: resync_all() must not rglob the whole bundle_root, since
    # .venv/.venv-webui live inside it and contain thousands of unrelated .md files
    # from installed packages (this actually happened and polluted a real Knowledge
    # collection with LICENSE.md / pytest-cache content during development).
    venv_md = bundle_root / ".venv" / "Lib" / "site-packages" / "somepkg" / "LICENSE.md"
    venv_md.parent.mkdir(parents=True)
    venv_md.write_text("MIT License text", encoding="utf-8")

    root_level_md = bundle_root / "README.md"
    root_level_md.write_text("not a concept doc", encoding="utf-8")

    synced_paths = []
    monkeypatch.setattr(openwebui_sync, "sync_file", lambda path, cfg: synced_paths.append(path) or "id")

    result = openwebui_sync.resync_all(sync_config)

    assert venv_md not in result
    assert root_level_md not in result
    assert synced_paths == result
