import dataclasses
from pathlib import Path

import pytest

from okeef import openwebui_sync
from okeef.config import Config


@pytest.fixture
def sync_config(config: Config) -> Config:
    return dataclasses.replace(
        config,
        openwebui_admin_email="admin@example.com",
        openwebui_admin_password="hunter2",
        openwebui_knowledge_id="test-knowledge-id",
    )


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json_data


def _install_fakes(monkeypatch, upload_status="completed"):
    calls = []

    def fake_post(url, headers=None, files=None, json=None, timeout=None):
        calls.append(("POST", url, files is not None, json))
        if url.endswith("/api/v1/auths/signin"):
            return _FakeResponse(200, {"token": "session-token-abc"})
        if url.endswith("/api/v1/files/"):
            return _FakeResponse(200, {"id": "file-123"})
        if url.endswith("/file/add"):
            return _FakeResponse(200, {"id": "test-knowledge-id"})
        raise AssertionError(f"unexpected POST {url}")

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, None, None))
        return _FakeResponse(200, {"status": upload_status})

    monkeypatch.setattr(openwebui_sync.requests, "post", fake_post)
    monkeypatch.setattr(openwebui_sync.requests, "get", fake_get)
    return calls


def test_sync_file_success(tmp_path: Path, sync_config: Config, monkeypatch) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("---\ntitle: Note\n---\n\nbody", encoding="utf-8")

    calls = _install_fakes(monkeypatch)

    file_id = openwebui_sync.sync_file(concept_path, sync_config)

    assert file_id == "file-123"
    assert calls[0] == (
        "POST",
        "http://localhost:8080/api/v1/auths/signin",
        False,
        {"email": "admin@example.com", "password": "hunter2"},
    )
    assert calls[1] == ("POST", "http://localhost:8080/api/v1/files/", True, None)
    assert calls[2][0] == "GET"
    assert calls[3] == (
        "POST",
        "http://localhost:8080/api/v1/knowledge/test-knowledge-id/file/add",
        False,
        {"file_id": "file-123"},
    )


def test_sync_file_raises_without_credentials(tmp_path: Path, config: Config) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("content", encoding="utf-8")

    with pytest.raises(openwebui_sync.SyncError):
        openwebui_sync.sync_file(concept_path, config)  # admin email/password/knowledge_id all empty


def test_sync_file_raises_on_bad_signin(tmp_path: Path, sync_config: Config, monkeypatch) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("content", encoding="utf-8")

    monkeypatch.setattr(
        openwebui_sync.requests,
        "post",
        lambda *a, **k: _FakeResponse(401, text='{"detail":"invalid credentials"}'),
    )

    with pytest.raises(openwebui_sync.SyncError):
        openwebui_sync.sync_file(concept_path, sync_config)


def test_sync_file_raises_on_processing_failure(tmp_path: Path, sync_config: Config, monkeypatch) -> None:
    concept_path = tmp_path / "note.md"
    concept_path.write_text("content", encoding="utf-8")

    _install_fakes(monkeypatch, upload_status="failed")

    with pytest.raises(openwebui_sync.SyncError):
        openwebui_sync.sync_file(concept_path, sync_config)


def test_resync_all_signs_in_once_and_reuses_token(
    bundle_root: Path, sync_config: Config, monkeypatch
) -> None:
    concept = bundle_root / "Resources" / "note.md"
    concept.write_text("---\ntitle: Note\n---\n\nbody", encoding="utf-8")

    staged = bundle_root / "_staging" / "abc123"
    staged.mkdir(parents=True)
    (staged / "draft.md").write_text("---\ntitle: Draft\n---\n\nbody", encoding="utf-8")

    sign_in_calls = []
    monkeypatch.setattr(
        openwebui_sync, "_sign_in", lambda cfg: sign_in_calls.append(1) or "token-xyz"
    )
    synced_with = []
    monkeypatch.setattr(
        openwebui_sync,
        "_sync_with_token",
        lambda path, cfg, token: synced_with.append((path, token)) or "id",
    )

    result = openwebui_sync.resync_all(sync_config)

    assert len(sign_in_calls) == 1  # signed in once, not per-file
    assert concept in result
    assert all(token == "token-xyz" for _, token in synced_with)
    assert all("index.md" not in str(p) and "log.md" not in str(p) for p in result)
    assert all("_staging" not in str(p) for p in result)


def test_resync_all_does_not_walk_venv_or_bundle_root(
    bundle_root: Path, sync_config: Config, monkeypatch
) -> None:
    # Regression test: resync_all() must not rglob the whole bundle_root, since
    # .venv/.venv-webui live inside it and contain thousands of unrelated .md files
    # from installed packages (this actually happened and polluted a real Knowledge
    # collection with LICENSE.md / pytest-cache content during development).
    venv_md = bundle_root / ".venv" / "Lib" / "site-packages" / "somepkg" / "LICENSE.md"
    venv_md.parent.mkdir(parents=True)
    venv_md.write_text("MIT License text", encoding="utf-8")

    root_level_md = bundle_root / "README.md"
    root_level_md.write_text("not a concept doc", encoding="utf-8")

    monkeypatch.setattr(openwebui_sync, "_sign_in", lambda cfg: "token-xyz")
    synced_paths = []
    monkeypatch.setattr(
        openwebui_sync,
        "_sync_with_token",
        lambda path, cfg, token: synced_paths.append(path) or "id",
    )

    result = openwebui_sync.resync_all(sync_config)

    assert venv_md not in result
    assert root_level_md not in result
    assert synced_paths == result
