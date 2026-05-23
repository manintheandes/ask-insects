from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class Provenance:
    source_id: str
    locator: str
    retrieved_at: str
    license: str | None = None
    source_url: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "retrieved_at": self.retrieved_at,
            "license": self.license,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str | None]) -> "Provenance":
        return cls(
            source_id=str(payload["source_id"]),
            locator=str(payload["locator"]),
            retrieved_at=str(payload["retrieved_at"]),
            license=payload.get("license"),
            source_url=payload.get("source_url"),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    lane: str
    source: str
    title: str
    text: str
    species: str | None
    url: str | None
    media_url: str | None
    provenance: Provenance

    def to_row(self) -> dict[str, str | None]:
        return {
            "record_id": self.record_id,
            "lane": self.lane,
            "source": self.source,
            "title": self.title,
            "text": self.text,
            "species": self.species,
            "url": self.url,
            "media_url": self.media_url,
            "provenance_json": json.dumps(self.provenance.to_dict(), sort_keys=True),
        }

    @classmethod
    def from_row(cls, row: dict[str, str | None]) -> "EvidenceRecord":
        provenance = Provenance.from_dict(json.loads(str(row["provenance_json"])))
        return cls(
            record_id=str(row["record_id"]),
            lane=str(row["lane"]),
            source=str(row["source"]),
            title=str(row["title"]),
            text=str(row["text"]),
            species=row.get("species"),
            url=row.get("url"),
            media_url=row.get("media_url"),
            provenance=provenance,
        )
