import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_drosophila_suzukii_olfaction_literature import ingest_drosophila_suzukii_olfaction_literature
from tests.test_drosophila_suzukii_pubmed_literature_source import ESEARCH, ESUMMARY


def _fake_fetch(url):
    if "esearch.fcgi" in url:
        return ESEARCH
    if "esummary.fcgi" in url:
        return ESUMMARY
    raise AssertionError(url)


class IngestOlfactionLiteratureTests(unittest.TestCase):
    def test_ingest_installs_olfaction_literature(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mosquito-v1"
            result = ingest_drosophila_suzukii_olfaction_literature(
                artifact_dir=artifact_dir, fetch_json=_fake_fetch,
                retrieved_at="2026-06-05T00:00:00Z", max_results=20, page_size=10, delay_seconds=0,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_olfaction_literature")
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from records where source='drosophila_suzukii_olfaction_literature'",
                limit=5,
            )
            self.assertGreaterEqual(rows[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
