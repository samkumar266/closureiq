"""Helpers for deterministic flip-list construction."""

from __future__ import annotations

from .types import Flip


def deduplicate_flips(flips: list[Flip]) -> list[Flip]:
    """Keep the first occurrence in deterministic input order."""
    seen: set[tuple[str, str, str | None]] = set()
    result: list[Flip] = []
    for flip in flips:
        key = (flip.change, flip.resulting_posture.value, flip.note)
        if key not in seen:
            seen.add(key)
            result.append(flip)
    return result
