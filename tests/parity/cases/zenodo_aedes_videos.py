from pathlib import Path
from tests.parity.fixtures import ParityCase
from tests.test_zenodo_aedes_videos_source import ZenodoFetcher
from askinsects.sources.zenodo_aedes_videos import fetch_zenodo_aedes_video_records

_RAW_DIR = "/tmp/ask-insects-parity/zenodo_aedes_videos"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_zenodo_aedes_video_records(
        raw_dir=raw_dir,
        fetch_json=ZenodoFetcher(),
        retrieved_at=_RETRIEVED_AT,
        query='"Aedes aegypti" video',
        size=10,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="zenodo_aedes_videos",
    run=_run,
    raw_dir=_RAW_DIR,
)
