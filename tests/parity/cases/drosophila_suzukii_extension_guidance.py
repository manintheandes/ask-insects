from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_extension_guidance import (
    fetch_drosophila_suzukii_extension_guidance_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_extension_guidance"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"

_HTML = """<html>
  <head>
    <title>Spotted wing drosophila management</title>
    <meta name="description" content="Monitor traps, harvest fruit, use sanitation, and manage spotted wing drosophila.">
  </head>
  <body>
    <h1>Spotted wing drosophila management</h1>
    Drosophila suzukii integrated pest management includes monitoring, trapping, sanitation,
    exclusion netting, insecticide rotation, and fruit damage prevention.
  </body>
</html>"""

_SOURCES = [
    {
        "organization": "Test Extension",
        "url": "https://extension.example/swd",
        "topic": "spotted wing drosophila management",
        "region": "test region",
    }
]


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_drosophila_suzukii_extension_guidance_records(
        _SOURCES,
        raw_dir=raw_dir,
        fetch_text=lambda url: _HTML,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_extension_guidance",
    run=_run,
    raw_dir=_RAW_DIR,
)
