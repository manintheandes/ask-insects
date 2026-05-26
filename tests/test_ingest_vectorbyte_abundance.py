import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_vectorbyte_abundance import ingest_vectorbyte_abundance, load_dataset_ids_file
from tests.test_vectorbyte_abundance_source import DATASET_220_PAGE_1, DATASET_27006_PAGE_1, SEARCH_PAYLOAD


class IngestVectorByteAbundanceTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "vecdynbyprovider" in url:
                    return SEARCH_PAYLOAD
                if "vecdyncsv" in url and "piids=27006" in url:
                    return DATASET_27006_PAGE_1
                raise AssertionError(url)

            result = ingest_vectorbyte_abundance(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-26T00:00:00Z",
                dataset_limit=1,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "aedes_vectorbyte_abundance")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["refresh_record_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("aedes_vectorbyte_abundance", "ecology")], 1)
            self.assertEqual(counts[("aedes_vectorbyte_abundance", "observations")], 1)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn("aedes_vectorbyte_abundance", receipt)
            self.assertIn("vecdyncsv", receipt)

    def test_failed_refresh_preserves_existing_abundance_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "vecdynbyprovider" in url:
                    return SEARCH_PAYLOAD
                if "vecdyncsv" in url and "piids=27006" in url:
                    return DATASET_27006_PAGE_1
                raise AssertionError(url)

            ingest_vectorbyte_abundance(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-26T00:00:00Z",
                dataset_limit=1,
            )
            failed = ingest_vectorbyte_abundance(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-26T01:00:00Z",
                dataset_limit=1,
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            self.assertEqual(failed["record_count"], 2)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from records where source='aedes_vectorbyte_abundance'",
                limit=1,
            )
            self.assertEqual(rows[0]["n"], 2)

    def test_ingest_accepts_explicit_dataset_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "vecdynbyprovider" in url:
                    raise AssertionError(f"dataset-id mode should not search metadata: {url}")
                if "vecdyncsv" in url and "piids=27006" in url:
                    return DATASET_27006_PAGE_1
                if "vecdyncsv" in url and "piids=220" in url:
                    return DATASET_220_PAGE_1
                raise AssertionError(url)

            result = ingest_vectorbyte_abundance(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-26T00:00:00Z",
                dataset_ids=["27006", "220"],
                dataset_page_limit=1,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 4)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select lane, count(*) as n from records where source='aedes_vectorbyte_abundance' group by lane order by lane",
                limit=10,
            )
            self.assertEqual({row["lane"]: row["n"] for row in rows}, {"ecology": 2, "observations": 2})

    def test_load_dataset_ids_file_accepts_lines_commas_and_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "vecdyn-datasets.txt"
            path.write_text(
                "# installed baseline\n"
                "27006, 220\n"
                "\n"
                "221\n"
                "220\n",
                encoding="utf-8",
            )

            self.assertEqual(load_dataset_ids_file(path), ["27006", "220", "221"])


if __name__ == "__main__":
    unittest.main()
