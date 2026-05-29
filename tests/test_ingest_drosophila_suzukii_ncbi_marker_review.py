import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_ncbi_marker_review import (
    DrosophilaSuzukiiNcbiMarkerReviewResult,
)
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_ncbi_marker_review import (
    ingest_drosophila_suzukii_ncbi_marker_review,
)


class IngestDrosophilaSuzukiiNcbiMarkerReviewTests(unittest.TestCase):
    def test_ingest_replaces_marker_review_source_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_records(**kwargs):
                return DrosophilaSuzukiiNcbiMarkerReviewResult(
                    source_id="drosophila_suzukii_ncbi_marker_review",
                    records=[
                        EvidenceRecord(
                            record_id="swd_ncbi_marker_review:nuccore:PV000001.1",
                            lane="dna_barcodes",
                            source="drosophila_suzukii_ncbi_marker_review",
                            title="Drosophila suzukii ITS2",
                            text="Drosophila suzukii marker-review record marker_group=nuclear_ribosomal_or_its",
                            species="Drosophila suzukii",
                            url="https://www.ncbi.nlm.nih.gov/nuccore/PV000001.1",
                            media_url=None,
                            provenance=Provenance(
                                source_id="drosophila_suzukii_ncbi_marker_review",
                                locator="raw/marker_review.json#result/1",
                                retrieved_at="2026-05-29T00:00:00Z",
                            ),
                            payload={"atom_type": "ncbi_marker_review", "marker_group": "nuclear_ribosomal_or_its"},
                        )
                    ],
                    gaps=[],
                    raw_artifacts=["raw/marker_review.json"],
                    requested_urls=["https://eutils.example"],
                    query="Drosophila suzukii[Organism]",
                    reported_total_count=1,
                    fetched_count=1,
                    page_count=1,
                    marker_group_counts={"nuclear_ribosomal_or_its": 1},
                )

            with mock.patch(
                "scripts.ingest_drosophila_suzukii_ncbi_marker_review.fetch_drosophila_suzukii_ncbi_marker_review_records",
                fake_fetch_records,
            ):
                result = ingest_drosophila_suzukii_ncbi_marker_review(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("drosophila_suzukii_ncbi_marker_review", "dna_barcodes")], 1)


if __name__ == "__main__":
    unittest.main()
