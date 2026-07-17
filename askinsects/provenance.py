from __future__ import annotations

from pathlib import Path


def public_provenance_locator(locator: str, source_id: str) -> str:
    path_text, separator, fragment = str(locator or "").partition("#")
    path = Path(path_text)
    if not path.is_absolute():
        return str(locator or "")
    parts = path.parts
    for anchor in ("artifacts", "raw", "sources", "config", "public"):
        if anchor in parts:
            relative = "/".join(parts[parts.index(anchor) :])
            break
    else:
        relative = f"sources/{source_id}/{path.name}"
    return relative + (f"#{fragment}" if separator else "")
