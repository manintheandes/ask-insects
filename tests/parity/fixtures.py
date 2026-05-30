from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ParityCase:
    source_id: str
    # run() MUST use deterministic fake fetchers AND a fixed retrieved_at
    # (no live timestamps like datetime.utcnow()), so its output is
    # byte-reproducible across runs.
    run: Callable[[], tuple[list, list]]  # returns (records, gaps)


# Populated one entry per migrated lane (see migration tasks).
LANE_CASES: list[ParityCase] = []


def _serialize(records, gaps):
    return {
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
