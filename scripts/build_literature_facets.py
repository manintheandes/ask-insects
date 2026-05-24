#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance


FACET_SOURCE_ID = "aedes_literature_facets"
LEGACY_FACET_SOURCE_IDS = ("mosquito_literature_facets",)

FACET_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "behavior": (
        "host seeking",
        "host-seeking",
        "blood feeding",
        "blood-feeding",
        "biting behavior",
        "feeding behavior",
        "oviposition",
        "mating",
        "flight",
        "circadian",
        "larval behavior",
        "repellent",
        "attractant",
        "odor",
        "olfaction",
        "carbon dioxide",
        "visual cue",
    ),
    "vector_competence": (
        "vector competence",
        "transmission competence",
        "infection rate",
        "dissemination rate",
        "transmission rate",
        "extrinsic incubation",
        "dengue virus",
        "zika virus",
        "chikungunya virus",
        "yellow fever virus",
        "west nile virus",
        "plasmodium",
        "arbovirus",
    ),
    "resistance": (
        "insecticide resistance",
        "pyrethroid resistance",
        "resistance mutation",
        "kdr",
        "knockdown resistance",
        "susceptibility",
        "bioassay",
        "larvicide",
        "adulticide",
        "permethrin",
        "deltamethrin",
        "temephos",
        "metabolic resistance",
        "detoxification",
    ),
    "ecology": (
        "ecology",
        "habitat",
        "larval habitat",
        "breeding site",
        "container",
        "urban",
        "climate",
        "temperature",
        "rainfall",
        "seasonality",
        "range",
        "distribution",
        "environmental suitability",
        "land use",
    ),
    "public_health": (
        "public health",
        "surveillance",
        "outbreak",
        "dengue",
        "zika",
        "chikungunya",
        "yellow fever",
        "west nile",
        "control program",
        "vector control",
        "intervention",
        "risk map",
        "case",
        "incidence",
        "epidemic",
        "arboviral disease",
    ),
}


@dataclass(frozen=True)
class LiteratureSourceRow:
    record_id: str
    title: str
    text: str
    species: str | None
    url: str | None
    source: str
    provenance: dict[str, object]


def _normalize_record_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    haystack = text.lower()
    matches = []
    for term in terms:
        pattern = r"\b" + re.escape(term.lower()).replace(r"\ ", r"[\s-]+") + r"\b"
        if re.search(pattern, haystack):
            matches.append(term)
    return matches


def _snippet(text: str, terms: list[str], limit: int = 420) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    lower = compact.lower()
    positions = [lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0]
    start = max(0, min(positions) - 120) if positions else 0
    snippet = compact[start : start + limit]
    if start > 0:
        snippet = "..." + snippet
    if start + limit < len(compact):
        snippet += "..."
    return snippet


def _load_literature_rows(conn: sqlite3.Connection) -> list[LiteratureSourceRow]:
    rows = conn.execute(
        """
        SELECT record_id, title, text, species, url, source, provenance_json
        FROM records
        WHERE lane = 'literature'
        ORDER BY record_id
        """
    ).fetchall()
    result = []
    for row in rows:
        result.append(
            LiteratureSourceRow(
                record_id=str(row["record_id"]),
                title=str(row["title"]),
                text=str(row["text"]),
                species=row["species"],
                url=row["url"],
                source=str(row["source"]),
                provenance=json.loads(str(row["provenance_json"])),
            )
        )
    return result


def _fts_query_for_term(term: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", term)
    if not tokens:
        return ""
    if len(tokens) == 1:
        return f"{tokens[0]}*"
    return '"' + " ".join(tokens) + '"'


def _load_fulltext_matches(conn: sqlite3.Connection) -> dict[str, dict[str, list[str]]]:
    matches: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for lane, terms in FACET_DEFINITIONS.items():
        for term in terms:
            query = _fts_query_for_term(term)
            if not query:
                continue
            try:
                rows = conn.execute(
                    """
                    SELECT record_id, unit_id
                    FROM literature_fulltext_fts
                    WHERE literature_fulltext_fts MATCH ?
                    LIMIT 50000
                    """,
                    (query,),
                ).fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                record_id = str(row["record_id"])
                unit_id = str(row["unit_id"])
                if term not in matches[record_id][lane]:
                    matches[record_id][lane].append(term)
                units_key = f"{lane}:units"
                if len(matches[record_id][units_key]) < 3 and unit_id not in matches[record_id][units_key]:
                    matches[record_id][units_key].append(unit_id)
    return matches


def build_facet_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> list[EvidenceRecord]:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        literature_rows = _load_literature_rows(conn)
        fulltext_matches = _load_fulltext_matches(conn)

    facet_records: list[EvidenceRecord] = []
    for source_row in literature_rows:
        combined = "\n".join([source_row.title, source_row.text])
        for lane, terms in FACET_DEFINITIONS.items():
            matches = list(dict.fromkeys(_matched_terms(combined, terms) + fulltext_matches.get(source_row.record_id, {}).get(lane, [])))
            if not matches:
                continue
            locator_parts = [f"records#{source_row.record_id}"]
            matching_units = fulltext_matches.get(source_row.record_id, {}).get(f"{lane}:units", [])
            locator_parts.extend(f"literature_fulltext_units#{unit_id}" for unit_id in matching_units)
            source_retrieved_at = str(source_row.provenance.get("retrieved_at") or retrieved_at or "unknown")
            title = f"Literature facet: {lane.replace('_', ' ')} in {source_row.title}"
            text = (
                f"This literature-derived Aedes intelligence facet marks the paper as {lane.replace('_', ' ')} "
                f"evidence because it matched: {', '.join(matches[:8])}. "
                f"Snippet: {_snippet(combined, matches)}"
            )
            provenance = Provenance(
                source_id=FACET_SOURCE_ID,
                locator=";".join(locator_parts),
                retrieved_at=retrieved_at or source_retrieved_at,
                license=str(source_row.provenance.get("license") or "source literature metadata and open full text where available"),
                source_url=source_row.url,
            )
            facet_records.append(
                EvidenceRecord(
                    record_id=f"facet:{lane}:{_normalize_record_id(source_row.record_id)}",
                    lane=lane,
                    source=FACET_SOURCE_ID,
                    title=title,
                    text=text,
                    species=source_row.species,
                    url=source_row.url,
                    media_url=None,
                    provenance=provenance,
                    payload={
                        "facet_lane": lane,
                        "source_record_id": source_row.record_id,
                        "source_record_source": source_row.source,
                        "matched_terms": matches,
                        "matching_fulltext_unit_ids": matching_units,
                    },
                )
            )
    return facet_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _update_status_and_receipt(artifact_dir: Path, records: list[EvidenceRecord]) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    lane_counts = summary["lanes"]
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    facet_lane_counts = {
        lane: count
        for lane, count in lane_counts.items()
        if lane in FACET_DEFINITIONS
    }
    facet_payload = {
        "source": FACET_SOURCE_ID,
        "record_count": len(records),
        "lane_counts": facet_lane_counts,
        "method": "keyword facet extraction from source-grade Aedes literature records and legal full-text units where available",
    }
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if not isinstance(sources, list):
            sources = []
        if FACET_SOURCE_ID not in sources:
            sources.append(FACET_SOURCE_ID)
        sources = [source for source in sources if source not in LEGACY_FACET_SOURCE_IDS]
        payload["sources"] = sources
        payload["record_count"] = summary["record_count"]
        payload["lanes"] = lane_counts
        payload["source_counts"] = source_counts
        payload["aedes_literature_facets"] = facet_payload
        for legacy_source_id in LEGACY_FACET_SOURCE_IDS:
            payload.pop(legacy_source_id, None)
        _write_json(path, payload)


def build_literature_facets(artifact_dir: Path, *, retrieved_at: str | None = None) -> dict[str, object]:
    records = build_facet_records(artifact_dir, retrieved_at=retrieved_at)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    for legacy_source_id in LEGACY_FACET_SOURCE_IDS:
        index.delete_source(legacy_source_id)
    index.delete_source(FACET_SOURCE_ID)
    index.upsert_records(records)
    _update_status_and_receipt(artifact_dir, records)
    return {
        "ok": True,
        "source": FACET_SOURCE_ID,
        "record_count": len(records),
        "lane_counts": dict(sorted((lane, sum(1 for record in records if record.lane == lane)) for lane in FACET_DEFINITIONS)),
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build mosquito intelligence facet records from indexed literature.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = build_literature_facets(Path(args.artifact_dir), retrieved_at=args.retrieved_at)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
