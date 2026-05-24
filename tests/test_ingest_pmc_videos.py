import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_pmc_videos import ingest_pmc_videos


PMC_HTML = """
<html>
  <head>
    <meta name="citation_title" content="Visual threat avoidance while host seeking by Aedes aegypti mosquitoes">
    <meta name="citation_license" content="CC BY">
  </head>
  <body>
    <a href="/articles/instance/12077400/bin/NIHMS2076695-supplement-2.mp4">Download video file</a>
  </body>
</html>
"""


class IngestPMCVideosTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_pmc_videos(
                artifact_dir=artifact_dir,
                article_urls=["https://pmc.ncbi.nlm.nih.gov/articles/PMC12077400/"],
                fetch_text=lambda url: PMC_HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("pmc_open_access_videos", "media")], 1)

            sources = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("pmc_open_access_videos", sources)


if __name__ == "__main__":
    unittest.main()
