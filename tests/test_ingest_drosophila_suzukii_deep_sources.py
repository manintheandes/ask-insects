import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_deep_sources import (
    DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
    DrosophilaSuzukiiDeepResult,
)
from scripts.ingest_drosophila_suzukii_deep_sources import ingest_drosophila_suzukii_deep_sources


def fake_fetch_records(**kwargs) -> DrosophilaSuzukiiDeepResult:
    retrieved_at = kwargs.get("retrieved_at") or "2026-05-28T00:00:00Z"
    record = EvidenceRecord(
        record_id="swd:assembly:GCF_TEST",
        lane="genome_assemblies",
        source=DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
        title="Drosophila suzukii assembly GCF_TEST",
        text="NCBI Assembly record for Drosophila suzukii.",
        species="Drosophila suzukii",
        url="https://www.ncbi.nlm.nih.gov/assembly/GCF_TEST",
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
            locator="test#assembly",
            retrieved_at=str(retrieved_at),
            license="test",
            source_url="https://eutils.ncbi.nlm.nih.gov/",
        ),
        payload={"record_type": "ncbi_assembly"},
    )
    return DrosophilaSuzukiiDeepResult(
        source_id=DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
        records=[record],
        gaps=[],
        raw_artifacts=["raw/drosophila_suzukii_deep_sources/test.json"],
        requested_urls=["https://eutils.ncbi.nlm.nih.gov/"],
        source_counts={"genome_assemblies": 1},
    )


class IngestDrosophilaSuzukiiDeepSourcesTests(unittest.TestCase):
    def test_ingest_deep_sources_preserves_existing_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii_deep_sources(
                artifact_dir=artifact_dir,
                fetch_records_fn=fake_fetch_records,
            )

            self.assertTrue(result["ok"])
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            sources = {
                row["source"]: int(row["n"])
                for row in index.sql("select source, count(*) as n from records group by source", limit=100)
            }
            self.assertIn("mosquito_v1_fixtures", sources)
            self.assertEqual(sources[DROSOPHILA_SUZUKII_DEEP_SOURCE_ID], 1)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn(DROSOPHILA_SUZUKII_DEEP_SOURCE_ID, receipt)


if __name__ == "__main__":
    unittest.main()
