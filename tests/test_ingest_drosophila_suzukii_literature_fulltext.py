import tempfile
import unittest
from pathlib import Path
from unittest import mock


class IngestDrosophilaSuzukiiLiteratureFulltextTests(unittest.TestCase):
    def test_wrapper_uses_swd_source_id_and_legal_fulltext(self) -> None:
        from scripts.ingest_drosophila_suzukii_literature_fulltext import (
            ingest_drosophila_suzukii_literature_fulltext,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            with mock.patch("scripts.ingest_drosophila_suzukii_literature_fulltext.run_enrichment") as run:
                run.return_value = {"ok": True, "fulltext": {"records": 1, "units": 2}}
                result = ingest_drosophila_suzukii_literature_fulltext(
                    artifact_dir=artifact_dir,
                    email="sources@openinsects.org",
                    limit=10,
                    delay_seconds=0,
                    max_fulltext_bytes=12345,
                    include_unpaywall=True,
                    resume=False,
                )

        config = run.call_args.args[0]
        self.assertEqual(config.artifact_dir, artifact_dir)
        self.assertEqual(config.source_id, "drosophila_suzukii_literature_fulltext")
        self.assertEqual(config.input_source_id, "drosophila_suzukii_core")
        self.assertEqual(config.source_label, "Drosophila suzukii literature")
        self.assertFalse(config.pubmed)
        self.assertTrue(config.unpaywall)
        self.assertTrue(config.fulltext)
        self.assertEqual(config.limit, 10)
        self.assertFalse(config.resume)
        self.assertEqual(config.max_fulltext_bytes, 12345)
        self.assertTrue(result["legal_fulltext_only"])
        self.assertEqual(result["input_source"], "drosophila_suzukii_core")


if __name__ == "__main__":
    unittest.main()
