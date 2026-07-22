#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now
from askinsects.incremental_metadata import update_source_metadata_incrementally
from askinsects.index import SourceIndex
from askinsects.ingest_runner import run_source_ingest
from askinsects.sources.anopheles_uniprot import (
    ANOPHELES_UNIPROT_SOURCE_ID,
    ANOPHELES_UNIPROT_TARGET_TAXA,
    fetch_anopheles_uniprot_records,
)


def _update_metadata(
    artifact_dir: Path,
    *,
    retrieved_at: str,
    outcome: dict[str, object],
    result,
) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    with index.connect() as connection:
        installed_lane_counts = {
            str(row["lane"]): int(row["n"])
            for row in connection.execute(
                "select lane, count(*) as n from records where source=? group by lane",
                (ANOPHELES_UNIPROT_SOURCE_ID,),
            ).fetchall()
        }
        installed_protein_count = int(
            connection.execute(
                "select count(*) as n from records where source=? and record_id like 'anopheles_uniprot:protein:%'",
                (ANOPHELES_UNIPROT_SOURCE_ID,),
            ).fetchone()["n"]
        )
        installed_proteome_count = int(
            connection.execute(
                "select count(*) as n from records where source=? and record_id like 'anopheles_uniprot:proteome:%'",
                (ANOPHELES_UNIPROT_SOURCE_ID,),
            ).fetchone()["n"]
        )
    source_payload = {
        "source": ANOPHELES_UNIPROT_SOURCE_ID,
        "lanes": ["proteins"],
        "lane_counts": installed_lane_counts,
        "record_count": int(outcome["record_count"]),
        "refresh_record_count": int(outcome["refresh_record_count"]),
        "protein_record_count": installed_protein_count,
        "proteome_record_count": installed_proteome_count,
        "source_gap_count": int(outcome["source_gap_count"]),
        "target_taxa": [
            {"species": species, "ncbi_taxonomy_id": taxonomy_id}
            for species, taxonomy_id in result.target_taxa
        ],
        "record_counts_by_taxon": result.record_counts,
        "protein_limit_per_taxon": result.protein_limit_per_taxon,
        "proteome_limit_per_taxon": result.proteome_limit_per_taxon,
        "requested_urls": result.requested_urls,
        "raw_artifacts": result.raw_artifacts,
        "gap_count": len(result.gaps),
        "retrieved_at": retrieved_at,
        "refresh_failed": bool(outcome["refresh_failed"]),
        "preserved_existing": bool(outcome["preserved_existing"]),
        "method": "bounded UniProtKB and proteome REST queries using NCBI-verified taxonomy identifiers for priority Anopheles taxa",
    }
    update_source_metadata_incrementally(
        artifact_dir,
        source_id=ANOPHELES_UNIPROT_SOURCE_ID,
        default_lane="proteins",
        installed_record_count=int(outcome["record_count"]),
        installed_lane_counts=installed_lane_counts,
        source_payload=source_payload,
    )


def ingest_anopheles_uniprot(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    target_taxa: list[tuple[str, int]] | tuple[tuple[str, int], ...] = ANOPHELES_UNIPROT_TARGET_TAXA,
    protein_limit_per_taxon: int = 500,
    proteome_limit_per_taxon: int = 10,
    fetch_json=None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    result = fetch_anopheles_uniprot_records(
        raw_dir=artifact_dir / "raw" / "anopheles_uniprot",
        target_taxa=target_taxa,
        protein_limit_per_taxon=protein_limit_per_taxon,
        proteome_limit_per_taxon=proteome_limit_per_taxon,
        fetch_json=fetch_json,
        retrieved_at=retrieved,
    )
    outcome = run_source_ingest(
        index=index,
        artifact_dir=artifact_dir,
        source_id=ANOPHELES_UNIPROT_SOURCE_ID,
        records=result.records,
        gaps=result.gaps,
        retrieved_at=retrieved,
        raw_artifacts=result.raw_artifacts,
        persist_gap_records=True,
        preserve_existing_fts=True,
    )
    _update_metadata(artifact_dir, retrieved_at=retrieved, outcome=outcome, result=result)
    return {
        **outcome,
        "protein_record_count": sum(record.record_id.startswith("anopheles_uniprot:protein:") for record in result.records),
        "proteome_record_count": sum(record.record_id.startswith("anopheles_uniprot:proteome:") for record in result.records),
        "target_taxa": [
            {"species": species, "ncbi_taxonomy_id": taxonomy_id}
            for species, taxonomy_id in result.target_taxa
        ],
        "record_counts_by_taxon": result.record_counts,
        "protein_limit_per_taxon": result.protein_limit_per_taxon,
        "proteome_limit_per_taxon": result.proteome_limit_per_taxon,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest bounded Anopheles UniProt protein and proteome metadata.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--protein-limit-per-taxon", type=int, default=500)
    parser.add_argument("--proteome-limit-per-taxon", type=int, default=10)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_uniprot(
        artifact_dir=Path(args.artifact_dir),
        protein_limit_per_taxon=args.protein_limit_per_taxon,
        proteome_limit_per_taxon=args.proteome_limit_per_taxon,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
