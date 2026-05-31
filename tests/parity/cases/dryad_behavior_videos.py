from pathlib import Path
from tests.parity.fixtures import ParityCase
from tests.test_dryad_behavior_videos_source import DryadFetcher
from askinsects.sources.dryad_behavior_videos import (
    DryadDatasetSpec,
    fetch_dryad_behavior_video_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/dryad_behavior_videos"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"
# Single dataset spec matching the DryadFetcher fake payload
_SPECS = (
    DryadDatasetSpec(
        doi="10.5061/dryad.example",
        behavior_labels=("host seeking", "thermal infrared", "human odor", "CO2", "navigation"),
    ),
)


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_dryad_behavior_video_records(
        _SPECS,
        raw_dir=raw_dir,
        fetch_json=DryadFetcher(),
        # No fetch_text: landing pages won't be fetched (no live call)
        # No fetch_bytes: table downloads won't be attempted (no table ext files present)
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="dryad_aedes_behavior_videos",
    run=_run,
    raw_dir=_RAW_DIR,
)
