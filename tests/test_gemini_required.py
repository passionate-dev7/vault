"""Gemini must be load-bearing in VAULT, not decorative.

VAULT's premise is "machine-measured, not estimated": ffmpeg and ClickHouse produce
every number, and Gemini decides what to do about them. A deterministic fallback
emitting the same shape would make the model removable, which is the exact mistake
recorded in the previous hackathon postmortem.

Note the module auto-loads .env, so unsetting environment variables does NOT prove
the guard works. These tests patch the client factory directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import triage as t  # noqa: E402


def test_triage_refuses_without_a_model(monkeypatch):
    monkeypatch.setattr(t, "_gemini", lambda: None)
    with pytest.raises(t.GeminiRequired):
        t.run_triage()


def test_a_failed_model_call_surfaces_instead_of_degrading(monkeypatch):
    """A model error must not quietly become a hand-written plan."""

    class Boom:
        class models:
            @staticmethod
            def generate_content(**kw):
                raise RuntimeError("simulated model outage")

    monkeypatch.setattr(t, "_gemini", lambda: Boom())
    with pytest.raises(t.GeminiRequired):
        t.run_triage()


def test_no_deterministic_fallback_remains_in_the_module():
    """Guard against the fallback being quietly reintroduced later."""
    assert not hasattr(t, "_deterministic_triage"), (
        "a deterministic triage fallback is back; it makes Gemini removable"
    )
    source = Path(t.__file__).read_text(encoding="utf-8")
    assert "Deterministic fallback (no Gemini credentials)" not in source
