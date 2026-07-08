"""Loads pipeline configuration from config/config.yaml with .env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# App/src/okeef/config.py -> parents[2] is the app root (D:\OKEEF\App). repo_root
# (the git top level, holding both App/ and Knowledgebase/) is its parent.
_DEFAULT_APP_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    repo_root: Path
    app_root: Path
    bundle_root: Path
    auto_commit: bool
    para_buckets: list[str]
    classify_model: str
    embed_model: str
    ollama_host: str
    chunk_size: int
    chunk_overlap: int
    openwebui_base_url: str
    openwebui_knowledge_id: str
    openwebui_admin_email: str
    openwebui_admin_password: str


def load_config(app_root: Path | None = None) -> Config:
    root = app_root or Path(os.environ.get("OKEEF_APP_ROOT", str(_DEFAULT_APP_ROOT)))
    repo_root = root.parent
    bundle_root = repo_root / "Knowledgebase"

    # utf-8-sig tolerates a leading BOM (harmless if absent) -- PowerShell's
    # `Set-Content -Encoding utf8` writes one by default, which otherwise silently
    # corrupts the first key's name and makes it invisible to os.environ.get().
    load_dotenv(root / ".env", encoding="utf-8-sig")

    cfg_path = root / "config" / "config.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    raw = raw or {}
    openwebui = raw.get("openwebui") or {}

    auto_commit = bool(raw.get("auto_commit", True))
    env_auto_commit = os.environ.get("AUTO_COMMIT")
    if env_auto_commit is not None:
        auto_commit = env_auto_commit.strip().lower() in {"1", "true", "yes"}

    return Config(
        repo_root=repo_root,
        app_root=root,
        bundle_root=bundle_root,
        auto_commit=auto_commit,
        para_buckets=raw.get("para_buckets") or ["Projects", "Areas", "Resources", "Archives"],
        classify_model=raw.get("classify_model", "qwen2.5:3b-instruct"),
        embed_model=raw.get("embed_model", "nomic-embed-text"),
        ollama_host=raw.get("ollama_host", "http://localhost:11434"),
        chunk_size=int(raw.get("chunk_size", 800)),
        chunk_overlap=int(raw.get("chunk_overlap", 150)),
        openwebui_base_url=openwebui.get("base_url", "http://localhost:8080"),
        # knowledge_id is a per-machine value (each Open WebUI instance generates its
        # own Knowledge collection UUID on first setup), so it comes from .env
        # (machine-specific, gitignored) rather than the shared config.yaml.
        openwebui_knowledge_id=os.environ.get(
            "OPENWEBUI_KNOWLEDGE_ID", openwebui.get("knowledge_id", "")
        ),
        # Sync signs in with the admin account itself (session JWT, ~4 week expiry by
        # Open WebUI's default) rather than using a generated API key -- API keys were
        # found not to reliably survive an Open WebUI restart in the installed version
        # (ENABLE_API_KEYS and/or the stored key itself resets), while sign-in is
        # simple and robust since these are the same credentials used to headlessly
        # bootstrap the admin account in the first place.
        openwebui_admin_email=os.environ.get("WEBUI_ADMIN_EMAIL", ""),
        openwebui_admin_password=os.environ.get("WEBUI_ADMIN_PASSWORD", ""),
    )
