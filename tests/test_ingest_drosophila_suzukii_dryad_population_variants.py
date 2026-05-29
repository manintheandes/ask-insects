import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_dryad_population_variants import (
    DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
    DrosophilaSuzukiiDryadPopulationVariantsResult,
)
from scripts.ingest_drosophila_suzukii_dryad_population_variants import ingest_drosophila_suzukii_dryad_population_variants


class IngestDrosophilaSuzukiiDryadPopulationVariantsTests(unittest.TestCase):
    def test_ingest_replaces_source_records_and_updates_receipt(self):
        record = EvidenceRecord(
            record_id="swd_dryad_population_variants:file:620083",
            lane="genome_features",
            source=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
            title="Drosophila suzukii Dryad population variant file SNPs-q30-original-SWD.vcf.gz",
            text="Dryad VCF manifest.",
            species="Drosophila suzukii",
            url="https://doi.org/10.25338/B89P86",
            media_url=None,
            provenance=Provenance(
                source_id=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
                locator="raw/drosophila_suzukii_dryad_population_variants/files.json#files/2",
                retrieved_at="2026-05-29T00:00:00Z",
            ),
        )
        fake_result = DrosophilaSuzukiiDryadPopulationVariantsResult(
            source_id=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
            records=[record],
            gaps=[],
            raw_artifacts=["raw/drosophila_suzukii_dryad_population_variants/files.json"],
            requested_urls=["https://example.org/dataset", "https://example.org/files"],
            file_count=2,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            with patch(
                "scripts.ingest_drosophila_suzukii_dryad_population_variants.fetch_drosophila_suzukii_dryad_population_variants_records",
                return_value=fake_result,
            ):
                result = ingest_drosophila_suzukii_dryad_population_variants(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                    max_mirror_bytes=123,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID)
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["source_counts"][DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID], 1)


if __name__ == "__main__":
    unittest.main()
