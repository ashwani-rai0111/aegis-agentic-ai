"""Normalize model/tool confidence values to a 0–1 range."""

from __future__ import annotations


def normalize_confidence(value: float | int | None, default: float = 0.5) -> float:
    """Crew/LLMs sometimes return 0–100; UI expects 0–1."""
    if value is None:
        return default
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    if score > 1.0:
        score = score / 100.0
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score
