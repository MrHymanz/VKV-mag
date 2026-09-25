from __future__ import annotations


def apply_correction(text: str, start: int, length: int, replacement: str) -> str:
    """Vervangt een tekstfragment op basis van exacte offset en lengte."""
    start = max(0, int(start))
    length = max(0, int(length))
    end = min(len(text), start + length)
    start = min(start, len(text))
    return text[:start] + replacement + text[end:]
