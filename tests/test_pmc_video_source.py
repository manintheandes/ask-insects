import tempfile
import unittest
from pathlib import Path

from askinsects.sources.pmc_videos import PMC_VIDEO_SOURCE_ID, fetch_pmc_video_records


PMC_HTML = """
<html>
  <head>
    <meta name="citation_title" content="BiteOscope, an open platform to study mosquito biting behavior">
    <meta name="citation_doi" content="10.7554/eLife.56829">
    <meta name="citation_license" content="CC BY 4.0">
  </head>
  <body>
    <p><em>Aedes aegypti</em> biting behavior videos.</p>
    <p>This article is distributed under the terms of the <a href="http://creativecommons.org/licenses/by/4.0/">Creative Commons Attribution License</a>.</p>
    <a href="/articles/instance/7535929/bin/elife-56829-video1.mp4">Download video file</a>
    <p><strong>Video 1.</strong> Aedes aegypti mosquito biting assay.</p>
    <a href="/articles/instance/7535929/bin/elife-56829-video1.mp4">Duplicate video link</a>
    <a href="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/7535929/elife-56829-video2-pmcvs_normal.mp4">Stream</a>
  </body>
</html>
"""


class PMCVideosSourceTests(unittest.TestCase):
    def test_fetch_pmc_video_records_normalizes_downloadable_videos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_pmc_video_records(
                ["https://pmc.ncbi.nlm.nih.gov/articles/PMC7535929/"],
                raw_dir=Path(tmpdir),
                fetch_text=lambda url: PMC_HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(result.source_id, PMC_VIDEO_SOURCE_ID)
        self.assertEqual(result.article_count, 1)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].lane, "media")
        self.assertEqual(result.records[0].source, PMC_VIDEO_SOURCE_ID)
        self.assertEqual(result.records[0].species, "Aedes aegypti")
        self.assertIn("video", result.records[0].title.lower())
        self.assertNotIn("still image", result.records[0].title.lower())
        self.assertEqual(
            result.records[0].media_url,
            "https://pmc.ncbi.nlm.nih.gov/articles/instance/7535929/bin/elife-56829-video1.mp4",
        )
        self.assertEqual(result.records[0].provenance.license, "CC BY 4.0")
        self.assertIn("raw_html", result.records[0].payload)
        self.assertTrue(result.raw_artifacts)

    def test_fetch_pmc_video_records_records_gap_when_article_has_no_videos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_pmc_video_records(
                ["https://pmc.ncbi.nlm.nih.gov/articles/PMC1/"],
                raw_dir=Path(tmpdir),
                fetch_text=lambda url: "<html><head><meta name='citation_title' content='Aedes aegypti'></head></html>",
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(result.records, [])
        self.assertEqual(result.gaps[0]["source"], PMC_VIDEO_SOURCE_ID)
        self.assertEqual(result.gaps[0]["reason"], "pmc_video_links_missing")

    def test_fetch_pmc_video_records_parses_creative_commons_license_text(self):
        html = """
        <html><head><meta name="citation_title" content="Aedes aegypti video"></head>
        <body>
          <p>Distributed under the terms of the Creative Commons Attribution License.</p>
          <a href="/articles/instance/1/bin/video1.mp4">Download video file</a>
        </body></html>
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_pmc_video_records(
                ["https://pmc.ncbi.nlm.nih.gov/articles/PMC1/"],
                raw_dir=Path(tmpdir),
                fetch_text=lambda url: html,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertEqual(result.records[0].provenance.license, "Creative Commons Attribution License")


if __name__ == "__main__":
    unittest.main()
