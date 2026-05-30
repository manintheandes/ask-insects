from pathlib import Path
from tests.parity.fixtures import ParityCase
from askinsects.sources.pmc_videos import fetch_pmc_video_records

_RAW_DIR = "/tmp/ask-insects-parity/pmc_videos"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"

PMC_HTML = """
<html>
  <head>
    <meta name="citation_title" content="BiteOscope, an open platform to study mosquito biting behavior">
    <meta name="citation_doi" content="10.7554/eLife.56829">
    <meta name="citation_license" content="CC BY 4.0">
  </head>
  <body>
    <p><em>Aedes aegypti</em> biting behavior videos.</p>
    <a href="/articles/instance/7535929/bin/elife-56829-video1.mp4">Download video file</a>
    <p><strong>Video 1.</strong> Aedes aegypti mosquito biting assay.</p>
  </body>
</html>
"""

_ARTICLE_URLS = ["https://pmc.ncbi.nlm.nih.gov/articles/PMC7535929/"]


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_pmc_video_records(
        _ARTICLE_URLS,
        raw_dir=raw_dir,
        fetch_text=lambda url: PMC_HTML,
        retrieved_at=_RETRIEVED_AT,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="pmc_open_access_videos",
    run=_run,
    raw_dir=_RAW_DIR,
)
