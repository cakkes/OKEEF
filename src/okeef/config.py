"""Loads pipeline configuration from config/config.yaml with .env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# src/okeef/config.py -> parents[2] is the bundle root (D:\OKEEF).
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
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
    openwebui_api_key: str


def load_config(bundle_root: Path | None = None) -> Config:
    root = bundle_root or Path(os.environ.get("OKEEF_ROOT", str(_DEFAULT_ROOT)))
    load_dotenv(root / ".env")

    cfg_path = root / "config" / "config.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    raw = raw or {}
    openwebui = raw.get("openwebui") or {}

    auto_commit = bool(raw.get("auto_commit", True))
    env_auto_commit = os.environ.get("AUTO_COMMIT")
    if env_auto_commit is not None:
        auto_commit = env_auto_commit.strip().lower() in {"1", "true", "yes"}

    return Config(
        bundle_root=root,
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
        # Also per-machine, and a real credential (unlike knowledge_id) -- .env only,
        # never config.yaml.
        openwebui_api_key=os.environ.get("OPENWEBUI_API_KEY", ""),
    )
