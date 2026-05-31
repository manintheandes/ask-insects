from pathlib import Path
from tests.parity.fixtures import ParityCase
from tests.test_osf_flighttrackai_videos_source import OSFFetcher
from askinsects.sources.osf_flighttrackai_videos import fetch_osf_flighttrackai_video_records

_RAW_DIR = "/tmp/ask-insects-parity/osf_flighttrackai_videos"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_osf_flighttrackai_video_records(
        raw_dir=raw_dir,
        fetch_json=OSFFetcher(),
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="osf_flighttrackai_aedes_videos",
    run=_run,
    raw_dir=_RAW_DIR,
)
