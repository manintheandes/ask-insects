#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now, write_json
from askinsects.index import SourceIndex
from askinsects.sources.uniprot_proteins import UNIPROT_PROTEIN_SOURCE_ID, fetch_uniprot_protein_records


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_dedup_gaps(gaps_path: Path, gaps: list[dict[str, object]]) -> int:
    existing = _read_json(gaps_path, [])
    if not isinstance(existing, list):
        existing = []
    combined = [gap for gap in existing if not (isinstance(gap, dict) and gap.get("source") == UNIPROT_PROTEIN_SOURCE_ID)]
    combined.extend(gaps)
    write_json(gaps_path, combined)
    return len(combined)


def _source_record_count(index: SourceIndex) -> int:
    with index.connect() as conn:
        return int(
            conn.execute(
                "select count(*) as n from records where source=?",
                (UNIPROT_PROTEIN_SOURCE_ID,),
            ).fetchone()["n"]
        )


def _update_metadata(artifact_dir: Path, result, retrieved_at: str, *, ok: bool = True, preserved_existing: bool = False) -> dict[str, object]:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    summary = index.summary()
    installed_record_count = _source_record_count(index)
    source_counts = {
        row["source"]: int(row["n"])
        for row in index.sql("select source, count(*) as n from records group by source order by source", limit=1000)
    }
    source_payload = {
        "source": UNIPROT_PROTEIN_SOURCE_ID,
        "requested_urls": result.requested_urls,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": not ok,
        "preserved_existing": preserved_existing,
    }
    gap_count = _append_dedup_gaps(artifact_dir / "gaps.json", result.gaps)
    for filename in ("source_status.json", "source_receipt.json"):
        path = artifact_dir / filename
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        sources = payload.get("sources")
        if isinstance(sources, dict):
            sources[UNIPROT_PROTEIN_SOURCE_ID] = source_payload
        else:
            if not isinstance(sources, list):
                sources = []
            if UNIPROT_PROTEIN_SOURCE_ID not in sources:
                sources.append(UNIPROT_PROTEIN_SOURCE_ID)
        payload["sources"] = sources
        payload["source_counts"] = source_counts
        payload["record_count"] = summary["record_count"]
        payload["species_count"] = summary["species_count"]
        payload["lanes"] = summary["lanes"]
        payload["gap_count"] = gap_count
        payload[UNIPROT_PROTEIN_SOURCE_ID] = source_payload
        write_json(path, payload)
    return {
        "ok": ok,
        "source": UNIPROT_PROTEIN_SOURCE_ID,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "gap_count": len(result.gaps),
        "preserved_existing": preserved_existing,
        "artifact_dir": artifact_dir.as_posix(),
        "lanes": summary["lanes"],
    }


def ingest_uniprot_proteins(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    fetch_json=None,
    retrieved_at: str | None = None,
    protein_limit: int = 250,
    proteome_limit: int = 10,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    result = fetch_uniprot_protein_records(
        raw_dir=artifact_dir / "raw" / "uniprot_proteins",
        fetch_json=fetch_json,
        retrieved_at=retrieved,
        protein_limit=protein_limit,
        proteome_limit=proteome_limit,
    )
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    refresh_failed = not result.records and bool(result.gaps)
    if not refresh_failed:
        index.replace_source_records(UNIPROT_PROTEIN_SOURCE_ID, result.records)
    return _update_metadata(
        artifact_dir,
        result,
        retrieved,
        ok=not refresh_failed,
        preserved_existing=refresh_failed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Aedes aegypti UniProt protein and proteome metadata into Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--protein-limit", type=int, default=250)
    parser.add_argument("--proteome-limit", type=int, default=10)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_uniprot_proteins(
        artifact_dir=Path(args.artifact_dir),
        protein_limit=args.protein_limit,
        proteome_limit=args.proteome_limit,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
