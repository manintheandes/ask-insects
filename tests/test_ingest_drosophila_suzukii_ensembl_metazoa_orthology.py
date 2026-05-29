from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_ensembl_metazoa_orthology import (
    DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
    DrosophilaSuzukiiEnsemblMetazoaOrthologyResult,
)
from scripts.ingest_drosophila_suzukii_ensembl_metazoa_orthology import ingest_drosophila_suzukii_ensembl_metazoa_orthology


class IngestDrosophilaSuzukiiEnsemblMetazoaOrthologyTests(unittest.TestCase):
    def test_ingest_replaces_source_records_and_preserves_nonfatal_empty_history_gaps(self):
        record = EvidenceRecord(
            record_id="swd_ensembl_current_gene:2",
            lane="genome_features",
            source=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            title="Drosophila suzukii Ensembl Metazoa current gene: Dpit47",
            text="Ensembl Metazoa current gene row for Dpit47.",
            species="Drosophila suzukii",
            url=None,
            media_url=None,
            provenance=Provenance(
                source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
                locator="raw/ensembl/gene.txt.gz#line/1",
                retrieved_at="2026-05-29T00:00:00Z",
                license="test",
            ),
            payload={"atom_type": "ensembl_metazoa_current_gene"},
        )
        result = DrosophilaSuzukiiEnsemblMetazoaOrthologyResult(
            source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            records=[record],
            gaps=[
                {
                    "source": DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
                    "reason": "swd_ensembl_metazoa_stable_id_event_empty",
                }
            ],
            raw_artifacts=["raw/ensembl/gene.txt.gz"],
            requested_urls=["https://example.test/gene.txt.gz"],
            current_gene_count=1,
            dmel_homolog_count=0,
            geneid_xref_count=0,
            stable_id_event_count=0,
            gene_archive_count=0,
            homolog_relationship_counts={},
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "scripts.ingest_drosophila_suzukii_ensembl_metazoa_orthology.fetch_drosophila_suzukii_ensembl_metazoa_orthology_records",
            return_value=result,
        ):
            payload = ingest_drosophila_suzukii_ensembl_metazoa_orthology(
                artifact_dir=Path(tmp),
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["record_count"], 1)
        self.assertEqual(payload["gap_count"], 1)
        self.assertFalse(payload["preserved_existing"])


if __name__ == "__main__":
    unittest.main()
