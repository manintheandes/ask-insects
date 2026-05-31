import json
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.sources.uniprot_proteins import UNIPROT_PROTEIN_SOURCE_ID
from scripts.ingest_uniprot_proteins import ingest_uniprot_proteins
from tests.test_uniprot_proteins_source import PROTEOME_PAYLOAD, UNIPROTKB_PAYLOAD


class IngestUniProtProteinsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        def fake_fetch_json(url: str) -> dict:
            if "/uniprotkb/search" in url:
                return UNIPROTKB_PAYLOAD
            if "/proteomes/search" in url:
                return PROTEOME_PAYLOAD
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
                protein_limit=25,
                proteome_limit=5,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], UNIPROT_PROTEIN_SOURCE_ID)
            # 1 protein + 1 proteome record
            self.assertGreaterEqual(result["refresh_record_count"], 2)
            self.assertEqual(result["gap_count"], 0)

            index = SourceIndex(artifact_dir / "source_index.sqlite")
            rows = index.sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertGreaterEqual(counts.get((UNIPROT_PROTEIN_SOURCE_ID, "proteins"), 0), 2)
            # fixture records must be preserved (7 total across lanes)
            fixture_total = sum(v for (src, _), v in counts.items() if src == "mosquito_v1_fixtures")
            self.assertEqual(fixture_total, 7)

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn(UNIPROT_PROTEIN_SOURCE_ID, status["sources"])
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertIn(UNIPROT_PROTEIN_SOURCE_ID, receipt)

    def test_failed_refresh_preserves_existing_rows(self):
        def fake_fetch_json(url: str) -> dict:
            if "/uniprotkb/search" in url:
                return UNIPROTKB_PAYLOAD
            if "/proteomes/search" in url:
                return PROTEOME_PAYLOAD
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            # Populate first
            ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            # Simulate offline failure
            failed = ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T01:00:00Z",
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            # preserved_existing means installed count > 0
            self.assertGreater(failed["record_count"], 0)


if __name__ == "__main__":
    unittest.main()
