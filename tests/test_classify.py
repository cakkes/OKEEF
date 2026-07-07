"""Integration test against the real Ollama server + qwen2.5:3b-instruct. Slow
(a real model call) and requires Ollama running locally with the model pulled --
skipped automatically if the server isn't reachable, rather than failing, since not
every environment running the test suite will have Ollama up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from okeef import classify
from okeef.config import load_config


def _ollama_reachable(host: str) -> bool:
    try:
        requests.get(host, timeout=2)
        return True
    except requests.RequestException:
        return False


@pytest.fixture
def config():
    return load_config()


@pytest.mark.skipif(
    not _ollama_reachable("http://localhost:11434"),
    reason="Ollama server not reachable on localhost:11434",
)
def test_classify_recipe_lands_in_resources(config) -> None:
    text = (
        "Sourdough Starter Feeding Schedule\n\n"
        "Feed the starter 1:1:1 (starter:flour:water) every 24 hours at room "
        "temperature, or every 5-7 days if kept in the fridge. Discard half before "
        "each feeding. Ready to bake with once it doubles in size within 4-6 hours."
    )
    result = classify.classify(Path("sourdough.txt"), text, config)

    assert result.para_bucket in {"Resources", "Areas"}  # reference material, not a deadline-bound project
    assert result.title
    assert result.description
    assert result.summary
    assert 0.0 <= result.confidence <= 1.0
    assert "/" not in result.folder_slug
    assert all(tag == tag.lower() for tag in result.tags)


@pytest.mark.skipif(
    not _ollama_reachable("http://localhost:11434"),
    reason="Ollama server not reachable on localhost:11434",
)
def test_classify_meeting_notes(config) -> None:
    text = (
        "Weekly sync with Alex - 2026-07-01\n\n"
        "Discussed Q3 roadmap. Action items: Alex to draft the proposal by Friday, "
        "Jojo to review budget numbers. Next sync scheduled for next Monday."
    )
    result = classify.classify(Path("weekly-sync-notes.txt"), text, config)

    assert result.para_bucket in {"Projects", "Areas"}
    assert result.title
    assert len(result.tags) >= 1
