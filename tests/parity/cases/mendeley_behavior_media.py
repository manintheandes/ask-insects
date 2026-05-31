from pathlib import Path
from tests.parity.fixtures import ParityCase
from tests.test_mendeley_behavior_media_source import MendeleyFetcher
from askinsects.sources.mendeley_behavior_media import (
    MendeleyDatasetSpec,
    fetch_mendeley_behavior_media_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/mendeley_behavior_media"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"
# Use a single spec (6gvs94p6r2:1) matching what MendeleyFetcher fakes
_SPECS = (
    MendeleyDatasetSpec(
        dataset_id="6gvs94p6r2",
        version=1,
        behavior_labels=("mating", "mate recognition", "wing flash", "wingbeat", "acoustic signal", "high-speed video"),
    ),
)


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_mendeley_behavior_media_records(
        _SPECS,
        raw_dir=raw_dir,
        fetch_json=MendeleyFetcher(),
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="mendeley_aedes_behavior_media",
    run=_run,
    raw_dir=_RAW_DIR,
)
