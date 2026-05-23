#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, DEFAULT_FIXTURE_PATH, build_source_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Ask Insects local mosquito source index.")
    parser.add_argument("--fixtures", action="store_true", help="Build from deterministic fixture records.")
    parser.add_argument("--gbif", action="store_true", help="Fetch bounded live GBIF taxonomy and occurrence records.")
    parser.add_argument("--species", action="append", default=[], help="Scientific name to fetch from GBIF. Repeatable.")
    parser.add_argument("--occurrence-limit", type=int, default=3, help="GBIF occurrence records to fetch per species.")
    parser.add_argument("--fixture-path", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    args = parser.parse_args()

    if not args.fixtures and not args.gbif:
        parser.error("select at least one source: --fixtures, --gbif, or both")

    result = build_source_index(
        include_fixtures=args.fixtures,
        include_gbif=args.gbif,
        fixture_path=Path(args.fixture_path),
        artifact_dir=Path(args.artifact_dir),
        gbif_species=args.species or None,
        occurrence_limit=args.occurrence_limit,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
