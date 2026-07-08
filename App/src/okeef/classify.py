"""Classification stage: a single Ollama structured-output call per file, replacing
the Phase 1/2 deterministic stub. Kept to one call (not a chain) to minimize round
trips against a model running on a 4GB-VRAM GPU. classify()'s return type
(Classification) is unchanged from the stub, so nothing else in the pipeline needed
to change.
"""

from __future__ import annotations

import json
from pathlib import Path

import ollama

from .config import Config
from .models import Classification
from .slug import slugify

_SUGGESTED_TYPES = (
    "note, reference, howto, meeting-notes, article-summary, person, "
    "project-charter, log-entry, recipe, contact, idea"
)

_SYSTEM_PROMPT = f"""You are a filing assistant for a personal knowledgebase organized \
with the PARA method and written as Open Knowledge Format (OKF) documents.

Given a file's name and its extracted text content, decide:

- para_bucket: exactly one of "Projects", "Areas", "Resources", "Archives".
  - Projects: an active effort with a specific, time-bound outcome or deadline
    (e.g. "Q3 website redesign", "plan summer 2026 trip").
  - Areas: an ongoing responsibility with no end date (e.g. health, finances, a job role).
  - Resources: reference material or a topic of interest, not tied to an active effort or
    responsibility (e.g. a recipe, an article summary, notes on a technology).
  - Archives: only if the content itself clearly signals it is already inactive,
    completed, or historical.
  When genuinely unsure, prefer "Resources" -- it is the safe default.
- okf_type: a short free-text label for what kind of thing this is. Suggested (not
  exhaustive) vocabulary: {_SUGGESTED_TYPES}. Use your own label if none fit well.
- title: a concise, human-readable title (not the raw filename).
- description: one sentence, at most 200 characters, summarizing what this is.
- summary: 2-4 sentences summarizing the key content.
- tags: 3-7 short lowercase tags, single words or short hyphenated phrases.
- folder_slug: ONE short kebab-case word or phrase for a subfolder under the PARA
  bucket, e.g. "recipes", "acme-project", "health". No slashes, no nested paths.
  Group related content under the same folder_slug when the topic is clear.
- confidence: your confidence in this classification, from 0.0 to 1.0.

Respond with only the structured fields."""

_HEAD_CHARS = 3000
_TAIL_CHARS = 1000


def classify(path: Path, text: str, config: Config) -> Classification:
    client = ollama.Client(host=config.ollama_host)
    response = client.chat(
        model=config.classify_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Filename: {path.name}\n\nContent:\n{_truncate(text)}"},
        ],
        format=Classification.model_json_schema(),
        options={"temperature": 0.1},
        keep_alive="5m",
    )
    data = json.loads(response.message.content)
    return _sanitize(Classification.model_validate(data))


def _truncate(text: str, head_chars: int = _HEAD_CHARS, tail_chars: int = _TAIL_CHARS) -> str:
    if len(text) <= head_chars + tail_chars:
        return text
    return text[:head_chars] + "\n...[truncated]...\n" + text[-tail_chars:]


def _sanitize(c: Classification) -> Classification:
    # Safety net beyond prompting: the model doesn't always follow formatting
    # instructions exactly (e.g. Title Case tags, slashes in folder_slug).
    return c.model_copy(
        update={
            "folder_slug": slugify(c.folder_slug) or "general",
            "tags": [t.strip().lower() for t in c.tags if t.strip()] or ["unclassified"],
            "title": c.title.strip() or "Untitled",
        }
    )
