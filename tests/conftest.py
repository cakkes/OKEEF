import subprocess
from pathlib import Path

import pytest

from okeef.config import Config
from okeef.git_ops import _git_executable
from okeef.models import Classification


@pytest.fixture(autouse=True)
def stub_classification(monkeypatch):
    """Most tests exercise extract/write/index/commit/staging, not the real Ollama
    call (that's covered separately in test_classify.py, which is slow and needs
    Ollama running). Replicates the Phase 1/2 deterministic stub's behavior exactly.
    """

    def _fake_classify(path: Path, text: str, config: Config) -> Classification:
        title = path.stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled"
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        return Classification(
            para_bucket="Resources",
            okf_type="note",
            title=title,
            description=first_line[:200] or "No description available.",
            summary=text.strip()[:400] or "No summary available.",
            tags=["unclassified"],
            folder_slug="unsorted",
            confidence=0.0,
        )

    monkeypatch.setattr("okeef.classify.classify", _fake_classify)


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
    (root / "_staging").mkdir()
    root_index = "---\nokf_version: \"0.1\"\ntitle: Test Bundle\n---\n\n# Test Bundle\n"
    (root / "index.md").write_text(root_index, encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")

    # A real (throwaway, tmp_path-isolated) git repo, since Phase 4 onward tests
    # exercise the actual commit path rather than skipping it.
    git = _git_executable()
    subprocess.run([git, "-C", str(root), "init"], check=True, capture_output=True)
    subprocess.run(
        [git, "-C", str(root), "config", "user.name", "Test User"], check=True, capture_output=True
    )
    subprocess.run(
        [git, "-C", str(root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    return root


@pytest.fixture
def config(bundle_root: Path) -> Config:
    return Config(
        bundle_root=bundle_root,
        auto_commit=True,
        para_buckets=["Projects", "Areas", "Resources", "Archives"],
        classify_model="stub",
        embed_model="stub",
        ollama_host="http://localhost:11434",
        chunk_size=800,
        chunk_overlap=150,
        openwebui_base_url="http://localhost:8080",
        openwebui_knowledge_id="",
        openwebui_api_key="",
    )
