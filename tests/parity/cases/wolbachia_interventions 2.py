from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_wolbachia_interventions_source import HTML
from askinsects.sources.wolbachia_interventions import fetch_wolbachia_intervention_records

_RAW_DIR = "/tmp/ask-insects-parity/wolbachia_interventions"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"

_SOURCES = [
    {
        "organization": "World Mosquito Program",
        "url": "https://www.worldmosquitoprogram.org/example-yogyakarta",
        "topic": "Yogyakarta Wolbachia randomized controlled trial",
        "intervention_type": "wMel Wolbachia replacement",
    }
]


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)

    r = fetch_wolbachia_intervention_records(
        _SOURCES,
        raw_dir=raw_dir,
        fetch_text=lambda url: HTML,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="aedes_wolbachia_interventions",
    run=_run,
    raw_dir=_RAW_DIR,
)
