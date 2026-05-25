import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_mosquito_repellent_external_discovery import ingest_mosquito_repellent_external_discovery
from tests.test_mosquito_repellent_external_discovery_source import (
    AGRICOLA,
    CROSSREF_PREPRINT,
    DATACITE,
    EUROPEPMC,
    FIGSHARE,
    OPENALEX,
    SEMANTIC_SCHOLAR,
    ZENODO,
)


def fake_external_fetch(url, body_json=None):
    if "api.openalex.org" in url:
        return OPENALEX
    if "SRC%3AAGR" in url or "SRC:AGR" in url:
        return AGRICOLA
    if "europepmc" in url:
        return EUROPEPMC
    if "semanticscholar" in url:
        return SEMANTIC_SCHOLAR
    if "api.crossref.org" in url:
        return CROSSREF_PREPRINT
    if "api.datacite.org" in url:
        return DATACITE
    if "zenodo.org" in url:
        return ZENODO
    if "api.figshare.com" in url:
        return FIGSHARE
    raise AssertionError(url)


class IngestMosquitoRepellentExternalDiscoveryTests(unittest.TestCase):
    def test_ingest_updates_external_records_and_receipts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            result = ingest_mosquito_repellent_external_discovery(
                artifact_dir=artifact_dir,
                fetch_json=fake_external_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results_per_source=5,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "mosquito_repellent_external_discovery")
            self.assertIn("openalex", result["source_counts"])
            self.assertIn("datasets", result["lane_counts"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select lane, count(*) as n from records where source='mosquito_repellent_external_discovery' group by lane",
                limit=20,
            )
            lanes = {row["lane"]: row["n"] for row in rows}
            self.assertIn("literature", lanes)
            self.assertIn("datasets", lanes)
            self.assertIn("patents", lanes)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn("mosquito_repellent_external_discovery", receipt)
            self.assertIn("patentsview_migrated_or_unavailable_json_api", receipt)

    def test_failed_refresh_preserves_existing_external_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            ingest_mosquito_repellent_external_discovery(
                artifact_dir=artifact_dir,
                fetch_json=fake_external_fetch,
                retrieved_at="2026-05-25T00:00:00Z",
            )
            failed = ingest_mosquito_repellent_external_discovery(
                artifact_dir=artifact_dir,
                fetch_json=lambda url, body_json=None: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-25T01:00:00Z",
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            self.assertGreater(failed["record_count"], 0)


if __name__ == "__main__":
    unittest.main()
