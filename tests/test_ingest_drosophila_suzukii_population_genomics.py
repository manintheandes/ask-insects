import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_population_genomics import (
    DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
    DrosophilaSuzukiiPopulationGenomicsResult,
)
from scripts.ingest_drosophila_suzukii_population_genomics import ingest_drosophila_suzukii_population_genomics


class IngestDrosophilaSuzukiiPopulationGenomicsTests(unittest.TestCase):
    def test_ingest_replaces_source_records_and_updates_receipt(self):
        record = EvidenceRecord(
            record_id="swd_population_genomics:bioproject:PRJNA1289399",
            lane="genome_features",
            source=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
            title="Drosophila suzukii population genomics BioProject PRJNA1289399",
            text="Pool-seq data from 3 Drosophila suzukii populations.",
            species="Drosophila suzukii",
            url="https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1289399",
            media_url=None,
            provenance=Provenance(
                source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
                locator="raw/drosophila_suzukii_population_genomics/summary.json#result/1289399",
                retrieved_at="2026-05-29T00:00:00Z",
            ),
        )
        fake_result = DrosophilaSuzukiiPopulationGenomicsResult(
            source_id=DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID,
            records=[record],
            gaps=[],
            raw_artifacts=["raw/drosophila_suzukii_population_genomics/summary.json"],
            requested_urls=["https://example.org/esearch", "https://example.org/esummary"],
            reported_count=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            with patch(
                "scripts.ingest_drosophila_suzukii_population_genomics.fetch_drosophila_suzukii_population_genomics_records",
                return_value=fake_result,
            ):
                result = ingest_drosophila_suzukii_population_genomics(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID)
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["reported_count"], 1)
        self.assertEqual(result["source_counts"][DROSOPHILA_SUZUKII_POPULATION_GENOMICS_SOURCE_ID], 1)


if __name__ == "__main__":
    unittest.main()
