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
    parser.add_argument(
        "--openalex-literature",
        action="store_true",
        help="Fetch Aedes aegypti literature from OpenAlex, with PubMed and Unpaywall enrichment.",
    )
    parser.add_argument("--species", action="append", default=[], help="Scientific name to fetch from GBIF. Repeatable.")
    parser.add_argument("--occurrence-limit", type=int, default=3, help="GBIF occurrence records to fetch per species.")
    parser.add_argument("--place", help="Place text for iNaturalist observation search, such as Brazil.")
    parser.add_argument("--observation-limit", type=int, default=10, help="iNaturalist observations to fetch per species.")
    parser.add_argument("--page-size", type=int, default=200, help="iNaturalist API page size. Maximum is 200.")
    parser.add_argument("--delay-seconds", type=float, default=0.0, help="Delay between iNaturalist API page requests.")
    parser.add_argument("--literature-species", default="Aedes aegypti")
    parser.add_argument("--literature-from-date", "--from-date", dest="literature_from_date", default="2020-01-01")
    parser.add_argument("--literature-to-date", "--to-date", dest="literature_to_date")
    parser.add_argument("--literature-work-type", "--work-type", dest="literature_work_type", default="article")
    parser.add_argument("--include-topic-discovery", action="store_true")
    parser.add_argument("--literature-page-size", type=int, default=200)
    parser.add_argument("--literature-delay-seconds", type=float)
    parser.add_argument("--literature-max-works", "--max-works", dest="literature_max_works", type=int)
    parser.add_argument("--unpaywall-email")
    parser.add_argument("--skip-fulltext", action="store_true")
    parser.add_argument("--skip-pubmed", action="store_true")
    parser.add_argument("--fixture-path", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if not args.fixtures and not args.gbif and not args.inat and not args.openalex_literature:
        parser.error("select at least one source: --fixtures, --gbif, --inat, --openalex-literature, or a combination")

    result = build_source_index(
        include_fixtures=args.fixtures,
        include_gbif=args.gbif,
        include_inaturalist=args.inat,
        include_literature=args.openalex_literature,
        fixture_path=Path(args.fixture_path),
        artifact_dir=Path(args.artifact_dir),
        gbif_species=args.species or None,
        occurrence_limit=args.occurrence_limit,
        inaturalist_species=args.species or None,
        inaturalist_place=args.place,
        observation_limit=args.observation_limit,
        page_size=args.page_size,
        delay_seconds=args.delay_seconds,
        literature_species=args.literature_species,
        literature_from_date=args.literature_from_date,
        literature_to_date=args.literature_to_date,
        literature_work_type=args.literature_work_type,
        include_topic_discovery=args.include_topic_discovery,
        literature_page_size=args.literature_page_size,
        literature_delay_seconds=args.literature_delay_seconds,
        literature_max_works=args.literature_max_works,
        unpaywall_email=args.unpaywall_email,
        skip_fulltext=args.skip_fulltext,
        skip_pubmed=args.skip_pubmed,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
