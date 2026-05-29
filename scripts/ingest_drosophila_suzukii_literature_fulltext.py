#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.builder import DEFAULT_ARTIFACT_DIR
from askinsects.sources.drosophila_suzukii import DROSOPHILA_SUZUKII_SOURCE_ID, DROSOPHILA_SUZUKII_SPECIES
from scripts.enrich_literature_index import EnrichmentConfig, run_enrichment


def ingest_drosophila_suzukii_literature_fulltext(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    email: str | None = None,
    limit: int | None = 25,
    delay_seconds: float = 0.0,
    max_fulltext_bytes: int = 60_000_000,
    include_unpaywall: bool | None = None,
    resume: bool = True,
) -> dict[str, object]:
    query_unpaywall = bool(email) if include_unpaywall is None else bool(include_unpaywall)
    config = EnrichmentConfig(
        artifact_dir=artifact_dir,
        source_id="drosophila_suzukii_literature_fulltext",
        input_source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
        source_label=f"{DROSOPHILA_SUZUKII_SPECIES} literature",
        email=email,
        pubmed=False,
        unpaywall=query_unpaywall,
        fulltext=True,
        limit=limit,
        delay_seconds=delay_seconds,
        max_fulltext_bytes=max_fulltext_bytes,
        resume=resume,
    )
    summary = run_enrichment(config)
    summary["source"] = "drosophila_suzukii_literature_fulltext"
    summary["input_source"] = DROSOPHILA_SUZUKII_SOURCE_ID
    summary["species"] = DROSOPHILA_SUZUKII_SPECIES
    summary["legal_fulltext_only"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enrich indexed Drosophila suzukii literature with legal direct full text."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--email")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--max-fulltext-bytes", type=int, default=60_000_000)
    parser.add_argument("--unpaywall", action="store_true")
    parser.add_argument("--no-resume", dest="resume", action="store_false", default=True)
    args = parser.parse_args(argv)
    result = ingest_drosophila_suzukii_literature_fulltext(
        artifact_dir=Path(args.artifact_dir),
        email=args.email,
        limit=args.limit,
        delay_seconds=args.delay_seconds,
        max_fulltext_bytes=args.max_fulltext_bytes,
        include_unpaywall=args.unpaywall or bool(args.email),
        resume=args.resume,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
