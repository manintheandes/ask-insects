#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, utc_now
from askinsects.incremental_metadata import update_source_metadata_incrementally
from askinsects.gaps import gap_records_from_dicts
from askinsects.index import SourceIndex
from askinsects.sources.anopheles_ncbi_assemblies import ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID
from askinsects.sources.anopheles_ncbi_genome_features import (
    ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
    fetch_anopheles_ncbi_genome_features,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _installed_assembly_receipts(index: SourceIndex) -> dict[str, dict[str, object]]:
    receipts: dict[str, dict[str, object]] = {}
    with index.connect() as connection:
        count_rows = connection.execute(
            """
            SELECT json_extract(p.payload_json, '$.assembly_accession') AS assembly_accession,
                   r.species, r.lane, count(*) AS n
            FROM records r
            JOIN record_payloads p ON p.record_id=r.record_id
            WHERE r.source=?
              AND json_extract(p.payload_json, '$.assembly_accession') IS NOT NULL
              AND coalesce(json_extract(p.payload_json, '$.atom_type'), '') <> 'source_gap'
            GROUP BY assembly_accession, r.species, r.lane
            ORDER BY assembly_accession, r.lane
            """,
            (ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,),
        ).fetchall()
        provenance_rows = connection.execute(
            """
            SELECT json_extract(p.payload_json, '$.assembly_accession') AS assembly_accession,
                   json_extract(r.provenance_json, '$.locator') AS locator,
                   json_extract(r.provenance_json, '$.source_url') AS source_url,
                   json_extract(r.provenance_json, '$.retrieved_at') AS retrieved_at,
                   json_extract(p.payload_json, '$.raw_counts_locator') AS secondary_locator,
                   json_extract(p.payload_json, '$.raw_source_url') AS secondary_source_url
            FROM records r
            JOIN record_payloads p ON p.record_id=r.record_id
            WHERE r.source=?
              AND json_extract(p.payload_json, '$.assembly_accession') IS NOT NULL
              AND coalesce(json_extract(p.payload_json, '$.atom_type'), '') <> 'source_gap'
            GROUP BY assembly_accession, locator, source_url, retrieved_at, secondary_locator, secondary_source_url
            ORDER BY assembly_accession, locator
            """,
            (ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,),
        ).fetchall()
    for row in count_rows:
        accession = str(row["assembly_accession"])
        receipt = receipts.setdefault(accession, {
            "assembly_accession": accession,
            "species": row["species"],
            "record_count": 0,
            "lane_counts": {},
            "source_urls": [],
            "raw_artifacts": [],
            "sha256": {},
            "retrieved_at": [],
        })
        count = int(row["n"])
        receipt["record_count"] = int(receipt["record_count"]) + count
        receipt["lane_counts"][str(row["lane"])] = count
    for row in provenance_rows:
        accession = str(row["assembly_accession"])
        receipt = receipts.get(accession)
        if receipt is None:
            continue
        for source_url in (str(row["source_url"] or ""), str(row["secondary_source_url"] or "")):
            if source_url and source_url not in receipt["source_urls"]:
                receipt["source_urls"].append(source_url)
        retrieved_value = str(row["retrieved_at"] or "")
        if retrieved_value and retrieved_value not in receipt["retrieved_at"]:
            receipt["retrieved_at"].append(retrieved_value)
        for locator in (str(row["locator"] or ""), str(row["secondary_locator"] or "")):
            raw_path_value = locator.split("#", 1)[0]
            raw_path = Path(raw_path_value)
            if raw_path_value and raw_path.exists() and raw_path_value not in receipt["raw_artifacts"]:
                receipt["raw_artifacts"].append(raw_path_value)
                receipt["sha256"][raw_path.name] = _sha256(raw_path)
    return receipts


def _select_reference_assembly(index: SourceIndex, species: str) -> dict[str, str]:
    with index.connect() as connection:
        rows = connection.execute(
            """
            SELECT p.payload_json
            FROM records r
            JOIN record_payloads p ON p.record_id=r.record_id
            WHERE r.source=? AND r.lane='genome_assemblies' AND lower(r.species)=lower(?)
            """,
            (ANOPHELES_NCBI_ASSEMBLIES_SOURCE_ID, species),
        ).fetchall()
    candidates: list[dict[str, object]] = []
    for row in rows:
        payload = json.loads(str(row["payload_json"]))
        if isinstance(payload, dict) and (payload.get("refseq_ftp") or payload.get("genbank_ftp")):
            candidates.append(payload)
    if not candidates:
        raise ValueError(f"No downloadable indexed NCBI assembly found for {species}; ingest anopheles_ncbi_assemblies first")
    level_rank = {"complete genome": 0, "chromosome": 1, "scaffold": 2, "contig": 3}
    candidates.sort(key=lambda payload: (
        0 if "reference genome" in str(payload.get("refseq_category", "")).lower() else 1,
        level_rank.get(str(payload.get("assembly_level", "")).lower(), 9),
        str(payload.get("release_date", "")),
    ))
    selected = candidates[0]
    return {
        "assembly_accession": str(selected["assembly_accession"]),
        "assembly_ftp": str(selected.get("refseq_ftp") or selected.get("genbank_ftp")),
        "species": str(selected.get("species") or species),
    }


def ingest_anopheles_ncbi_genome_features(
    *, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, species: str = "Anopheles gambiae",
    assembly_accession: str | None = None, assembly_ftp: str | None = None,
    retrieved_at: str | None = None,
) -> dict[str, object]:
    retrieved = retrieved_at or utc_now()
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    if assembly_accession and assembly_ftp:
        selected = {"assembly_accession": assembly_accession, "assembly_ftp": assembly_ftp, "species": species}
    else:
        selected = _select_reference_assembly(index, species)
    result = fetch_anopheles_ncbi_genome_features(
        raw_dir=artifact_dir / "raw" / "anopheles_ncbi_genome_features" / selected["assembly_accession"],
        assembly_accession=selected["assembly_accession"], species=selected["species"],
        assembly_ftp=selected["assembly_ftp"], retrieved_at=retrieved,
    )
    non_gap_records = list(result.records)
    refresh_failed = not non_gap_records
    scoped_records = [
        *non_gap_records,
        *gap_records_from_dicts(
            ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
            result.gaps,
            retrieved_at=retrieved,
        ),
    ]
    if scoped_records:
        index.replace_source_records_in_scope(
            ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
            scoped_records,
            record_id_prefix=f"anopheles_ncbi_genome:{selected['assembly_accession']}:",
            payload_field="assembly_accession",
            payload_value=selected["assembly_accession"],
            preserve_existing_fts=True,
        )
    with index.connect() as connection:
        installed_record_count = int(connection.execute(
            "select count(*) as n from records where source=?",
            (ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,),
        ).fetchone()["n"])
    outcome = {
        "ok": not refresh_failed,
        "source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
        "refresh_failed": refresh_failed,
        "preserved_existing": refresh_failed and installed_record_count > 0,
        "record_count": installed_record_count,
        "refresh_record_count": len(result.records),
        "source_gap_count": len(result.gaps),
        "retrieved_at": retrieved,
        "raw_artifacts": result.raw_artifacts,
    }
    with index.connect() as connection:
        installed_lane_counts = {
            str(row["lane"]): int(row["n"])
            for row in connection.execute(
                "select lane, count(*) as n from records where source=? group by lane",
                (ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,),
            ).fetchall()
        }
    assembly_receipts = _installed_assembly_receipts(index)
    update_source_metadata_incrementally(
        artifact_dir, source_id=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
        default_lane="genome_features", installed_record_count=int(outcome["record_count"]),
        installed_lane_counts=installed_lane_counts,
        source_payload={
            "source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
            "record_count": int(outcome["record_count"]), "refresh_record_count": int(outcome["refresh_record_count"]),
            "source_gap_count": int(outcome["source_gap_count"]), "assembly_accession": result.assembly_accession,
            "species": result.species, "assembly_ftp": selected["assembly_ftp"], "parsed_lane_counts": result.lane_counts,
            "installed_lane_counts": installed_lane_counts,
            "source_urls": result.source_urls, "raw_artifacts": result.raw_artifacts, "sha256": result.sha256,
            "assembly_count": len(assembly_receipts), "assemblies": assembly_receipts,
            "retrieved_at": retrieved, "refresh_failed": bool(outcome["refresh_failed"]),
            "preserved_existing": bool(outcome["preserved_existing"]),
            "method": "assembly-scoped download and parse of NCBI reference annotations with exact line or record provenance",
        },
    )
    return {
        **outcome,
        "assembly_accession": result.assembly_accession,
        "species": result.species,
        "lane_counts": result.lane_counts,
        "installed_lane_counts": installed_lane_counts,
        "sha256": result.sha256,
        "artifact_dir": artifact_dir.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Anopheles NCBI reference genome features and proteins.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--species", default="Anopheles gambiae")
    parser.add_argument("--assembly-accession")
    parser.add_argument("--assembly-ftp")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args(argv)
    result = ingest_anopheles_ncbi_genome_features(
        artifact_dir=Path(args.artifact_dir), species=args.species,
        assembly_accession=args.assembly_accession, assembly_ftp=args.assembly_ftp,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
