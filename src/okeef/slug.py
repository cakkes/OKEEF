"""Small shared slugify helper used by classify.py and okf_writer.py."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"
