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


@pytest.fixture(autouse=True)
def stub_classification():
    """Overrides conftest.py's autouse stub with a no-op: this file's entire point is
    to exercise the real classify.classify() against Ollama, so the stub that every
    other test file relies on must not apply here.
    """
    yield


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

    # Bucket choice for a one-off meeting note is a genuine judgment call (Projects/
    # Areas/Resources are all defensible depending on whether the model treats it as
    # part of a tracked project) -- assert well-formedness, not one specific bucket.
    assert result.para_bucket in {"Projects", "Areas", "Resources"}
    assert result.title
    assert len(result.tags) >= 1
