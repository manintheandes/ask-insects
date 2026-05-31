from __future__ import annotations

import re


def resolve_species(value: object, *, scope: str | None = None) -> str | None:
    """Return the row's own species, never a fabricated default.

    - Present row value -> cleaned string (wins over scope).
    - Absent + no scope -> None (do not invent a species).
    - Absent + scope given -> scope (only for sources genuinely pinned to one
      species by their query; the caller documents why at the call site).
    """
    if not isinstance(value, str):
        value = ""
    text = re.sub(r"\s+", " ", value).strip()
    if text:
        return text
    return (scope.strip() or None) if scope else None
