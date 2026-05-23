#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from askinsects.builder import DEFAULT_ARTIFACT_DIR, DEFAULT_FIXTURE_PATH, build_fixture_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Ask Insects local mosquito source index.")
    parser.add_argument("--fixtures", action="store_true", help="Build from deterministic fixture records.")
    parser.add_argument("--fixture-path", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    args = parser.parse_args()

    if not args.fixtures:
        parser.error("V1 supports --fixtures. Live source fetchers will be added after the local plane is proven.")

    result = build_fixture_index(Path(args.fixture_path), Path(args.artifact_dir))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
