from __future__ import annotations

import json
from pathlib import Path

from askinsects.records import EvidenceRecord, Provenance


FIXTURE_RETRIEVED_AT = "2026-05-23T00:00:00Z"
FIXTURE_SOURCE_ID = "mosquito_v1_fixtures"


def load_fixture_records(path: Path) -> list[EvidenceRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: list[EvidenceRecord] = []
    for item in payload:
        record_id = str(item["record_id"])
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane=str(item["lane"]),
                source=FIXTURE_SOURCE_ID,
                title=str(item["title"]),
                text=str(item["text"]),
                species=item.get("species"),
                url=item.get("url"),
                media_url=item.get("media_url"),
                provenance=Provenance(
                    source_id=FIXTURE_SOURCE_ID,
                    locator=f"{path.as_posix()}#{record_id}",
                    retrieved_at=FIXTURE_RETRIEVED_AT,
                    license=item.get("license"),
                    source_url=item.get("url"),
                ),
            )
        )
    return records
