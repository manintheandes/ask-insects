import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii import (
    DROSOPHILA_SUZUKII_SOURCE_ID,
    DrosophilaSuzukiiBuildResult,
)
from scripts.ingest_drosophila_suzukii import ingest_drosophila_suzukii


def fake_fetch_records(**kwargs) -> DrosophilaSuzukiiBuildResult:
    retrieved_at = kwargs.get("retrieved_at") or "2026-05-28T00:00:00Z"
    record = EvidenceRecord(
        record_id="swd:test:taxonomy",
        lane="taxonomy",
        source=DROSOPHILA_SUZUKII_SOURCE_ID,
        title="Drosophila suzukii",
        text="Drosophila suzukii is the spotted wing drosophila.",
        species="Drosophila suzukii",
        url="https://www.gbif.org/species/10568202",
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
            locator="test#taxonomy",
            retrieved_at=str(retrieved_at),
            license="test",
            source_url="https://api.gbif.org/v1/species/match",
        ),
        payload={"atom_type": "taxonomy"},
    )
    return DrosophilaSuzukiiBuildResult(
        source_id=DROSOPHILA_SUZUKII_SOURCE_ID,
        records=[record],
        gaps=[
            {
                "source": DROSOPHILA_SUZUKII_SOURCE_ID,
                "lane": "source_coverage",
                "reason": "test_gap",
            }
        ],
        raw_artifacts=["raw/drosophila_suzukii/test.json"],
        upstream_sources={"gbif": {"record_count": 1}},
    )


class IngestDrosophilaSuzukiiTests(unittest.TestCase):
    def test_ingest_adds_swd_source_without_removing_existing_fixture_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            result = ingest_drosophila_suzukii(
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
            self.assertEqual(sources[DROSOPHILA_SUZUKII_SOURCE_ID], 1)
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn(DROSOPHILA_SUZUKII_SOURCE_ID, status)


if __name__ == "__main__":
    unittest.main()
