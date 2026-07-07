"""Shared data model for a classification result, produced by classify.py
(stubbed in Phase 1, backed by Ollama structured output from Phase 3 onward)
and consumed by okf_writer.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ParaBucket = Literal["Projects", "Areas", "Resources", "Archives"]


class Classification(BaseModel):
    para_bucket: ParaBucket
    okf_type: str
    title: str
    description: str
    summary: str
    tags: list[str]
    folder_slug: str
    confidence: float = Field(ge=0.0, le=1.0)
