#!/usr/bin/env python3
"""Generate tests/parity/golden/<source_id>.json from the CURRENT adapter.
Run BEFORE migrating a lane, on the lane's pre-migration code."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.parity.fixtures import LANE_CASES, _serialize  # noqa: E402

GOLDEN = REPO / "tests" / "parity" / "golden"


def main(argv=None):
    GOLDEN.mkdir(parents=True, exist_ok=True)
    targets = set(argv or [])
    for case in LANE_CASES:
        if targets and case.source_id not in targets:
            continue
        records, gaps = case.run()
        (GOLDEN / f"{case.source_id}.json").write_text(
            json.dumps(_serialize(records, gaps), indent=2, sort_keys=True) + "\n"
        )
        print(f"wrote golden for {case.source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
