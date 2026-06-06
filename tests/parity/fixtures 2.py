from __future__ import annotations

import importlib
import json
import pkgutil
from dataclasses import dataclass
from typing import Callable

from . import cases as _cases_pkg


@dataclass(frozen=True)
class ParityCase:
    source_id: str
    # run() MUST use deterministic fake fetchers AND a fixed retrieved_at
    # (no live timestamps like datetime.utcnow()), so its output is
    # byte-reproducible across runs.
    run: Callable[[], tuple[list, list]]  # returns (records, gaps)
    # When set, every occurrence of this path in serialized string values is
    # replaced with "<raw_dir>" so goldens are machine-independent.
    raw_dir: str | None = None


# Modules that failed to import, as (module_name, repr(exc)) pairs. A broken
# case must be attributable, not a total blackout of the whole harness.
IMPORT_ERRORS: list[tuple[str, str]] = []

LANE_CASES: list[ParityCase] = []
for _m in pkgutil.iter_modules(_cases_pkg.__path__):
    try:
        _mod = importlib.import_module(f"{_cases_pkg.__name__}.{_m.name}")
    except Exception as exc:  # noqa: BLE001 - isolate one bad case from the rest
        IMPORT_ERRORS.append((_m.name, repr(exc)))
        continue
    case = getattr(_mod, "CASE", None)
    if isinstance(case, ParityCase):
        LANE_CASES.append(case)
LANE_CASES.sort(key=lambda c: c.source_id)


def _redact(value, raw_dir: str):
    if isinstance(value, str):
        return value.replace(raw_dir, "<raw_dir>")
    if isinstance(value, dict):
        return {key: _redact(item, raw_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, raw_dir) for item in value]
    return value


def _serialize(records, gaps, *, raw_dir=None):
    payload = {
        "records": sorted(
            (
                {
                    "record_id": r.record_id, "lane": r.lane, "source": r.source,
                    "title": r.title, "text": r.text, "species": r.species,
                    "url": r.url, "media_url": r.media_url,
                    "payload": r.payload, "provenance": r.provenance.to_dict(),
                }
                for r in records
            ),
            key=lambda d: d["record_id"],
        ),
        "gaps": sorted((dict(g) for g in gaps), key=lambda d: json.dumps(d, sort_keys=True)),
    }
    if raw_dir:
        payload = _redact(payload, raw_dir)
    return payload
