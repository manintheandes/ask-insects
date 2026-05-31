from pathlib import Path

from tests.parity.fixtures import ParityCase
from tests.test_drosophila_suzukii_osu_trap_reports_source import (
    RETRIEVED_AT,
    CSV_FIXTURE,
    osu_fetcher,
)
from askinsects.sources.drosophila_suzukii_osu_trap_reports import (
    FetchBody,
    ReportSpec,
    fetch_drosophila_suzukii_osu_trap_report_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_osu_trap_reports"

# Use only CSV specs to keep the golden byte-stable (openpyxl xlsx bytes are
# non-deterministic across Python/openpyxl versions).
_SPECS = [
    ReportSpec(
        year=2021,
        url="https://docs.google.com/spreadsheets/d/1KLU8rEoaz1Cnt9ILbUf77tSxOIriwZR0Xtj-wwNZgDA/gviz/tq?tqx=out:csv&sheet=Spotted-wing%20drosophila",
        filename="osu_swd_trap_report_2021_spotted_wing_drosophila.csv",
        file_kind="csv",
        sheet_name="Spotted-wing drosophila",
    ),
    ReportSpec(
        year=2016,
        url="https://docs.google.com/spreadsheets/d/1qNQEBjIwxSTA3JYi00CuhzkkLAJtnkdczdfqeQD2IbQ/pub?output=csv",
        filename="osu_swd_trap_report_2016.csv",
        file_kind="csv",
    ),
    ReportSpec(
        year=2015,
        url="https://docs.google.com/spreadsheets/d/1g2sFMxG-EKJdBXdXyF1fFLUfCGp6piwwWvjv-IQEoWw/pub?output=csv",
        filename="osu_swd_trap_report_2015.csv",
        file_kind="csv",
        expected_unavailable=True,
    ),
]


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_drosophila_suzukii_osu_trap_report_records(
        raw_dir=raw_dir,
        fetch_body=osu_fetcher,
        retrieved_at=RETRIEVED_AT,
        report_specs=_SPECS,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_osu_trap_reports",
    run=_run,
    raw_dir=_RAW_DIR,
)
