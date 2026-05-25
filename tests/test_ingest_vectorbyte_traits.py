import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_vectorbyte_traits import ingest_vectorbyte_traits
from tests.test_vectorbyte_traits_source import DATASET_126, SEARCH_PAYLOAD


class IngestVectorByteTraitsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "api.vbdhub.org/search" in url:
                    return SEARCH_PAYLOAD
                if "/vectraits-dataset/126/" in url:
                    return DATASET_126
                raise AssertionError(url)

            result = ingest_vectorbyte_traits(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                dataset_limit=1,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "aedes_vectorbyte_traits")
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(result["refresh_record_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("aedes_vectorbyte_traits", "traits")], 1)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn("aedes_vectorbyte_traits", receipt)
            self.assertIn("api.vbdhub.org/search", receipt)

    def test_failed_refresh_preserves_existing_vectorbyte_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "api.vbdhub.org/search" in url:
                    return SEARCH_PAYLOAD
                if "/vectraits-dataset/126/" in url:
                    return DATASET_126
                raise AssertionError(url)

            ingest_vectorbyte_traits(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                dataset_limit=1,
            )
            failed = ingest_vectorbyte_traits(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-25T01:00:00Z",
                dataset_limit=1,
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            self.assertEqual(failed["record_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from records where source='aedes_vectorbyte_traits'",
                limit=1,
            )
            self.assertEqual(rows[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
