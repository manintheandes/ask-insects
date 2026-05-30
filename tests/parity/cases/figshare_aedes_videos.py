from pathlib import Path
from tests.parity.fixtures import ParityCase
from tests.test_figshare_aedes_videos_source import FigshareFetcher
from askinsects.sources.figshare_aedes_videos import fetch_figshare_aedes_video_records

_RAW_DIR = "/tmp/ask-insects-parity/figshare_aedes_videos"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_figshare_aedes_video_records(
        raw_dir=raw_dir,
        fetch_json=FigshareFetcher(),
        retrieved_at=_RETRIEVED_AT,
        query="Aedes aegypti video",
        page_size=10,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="figshare_aedes_videos",
    run=_run,
    raw_dir=_RAW_DIR,
)
