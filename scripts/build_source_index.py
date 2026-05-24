#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, DEFAULT_FIXTURE_PATH, build_source_index


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Ask Insects local mosquito source index.")
    parser.add_argument("--fixtures", action="store_true", help="Build from deterministic fixture records.")
    parser.add_argument("--gbif", action="store_true", help="Fetch bounded live GBIF taxonomy and occurrence records.")
    parser.add_argument("--inat", action="store_true", help="Fetch bounded live iNaturalist observations with photos.")
    parser.add_argument("--ncbi-genome", action="store_true", help="Parse an NCBI Datasets genome package.")
    parser.add_argument("--species", action="append", default=[], help="Scientific name to fetch from GBIF. Repeatable.")
    parser.add_argument("--occurrence-limit", type=int, default=3, help="GBIF occurrence records to fetch per species.")
    parser.add_argument("--occurrence-page-size", type=int, default=300, help="GBIF API page size for occurrence search.")
    parser.add_argument("--occurrence-workers", type=int, default=1, help="GBIF occurrence page workers. Use carefully with public APIs.")
    parser.add_argument("--gbif-delay-seconds", type=float, default=0.0, help="Delay between GBIF occurrence API page requests.")
    parser.add_argument("--place", help="Place text for iNaturalist observation search, such as Brazil.")
    parser.add_argument("--observation-limit", type=int, default=10, help="iNaturalist observations to fetch per species.")
    parser.add_argument("--page-size", type=int, default=200, help="iNaturalist API page size. Maximum is 200.")
    parser.add_argument("--delay-seconds", type=float, default=0.0, help="Delay between iNaturalist API page requests.")
    parser.add_argument("--genome-package-dir", help="Path to an unpacked NCBI Datasets genome package.")
    parser.add_argument("--genome-assembly-accession", default="GCF_002204515.2", help="NCBI genome assembly accession.")
    parser.add_argument("--fixture-path", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if not args.fixtures and not args.gbif and not args.inat and not args.ncbi_genome:
        parser.error("select at least one source: --fixtures, --gbif, --inat, --ncbi-genome, or a combination")

    result = build_source_index(
        include_fixtures=args.fixtures,
        include_gbif=args.gbif,
        include_inaturalist=args.inat,
        include_ncbi_genome=args.ncbi_genome,
        fixture_path=Path(args.fixture_path),
        artifact_dir=Path(args.artifact_dir),
        gbif_species=args.species or None,
        occurrence_limit=args.occurrence_limit,
        occurrence_page_size=args.occurrence_page_size,
        occurrence_workers=args.occurrence_workers,
        gbif_delay_seconds=args.gbif_delay_seconds,
        inaturalist_species=args.species or None,
        inaturalist_place=args.place,
        observation_limit=args.observation_limit,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
        genome_package_dir=Path(args.genome_package_dir) if args.genome_package_dir else None,
        genome_assembly_accession=args.genome_assembly_accession,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
