import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_figshare_mk_selection import (
    DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
    DrosophilaSuzukiiFigshareMkSelectionResult,
)
from scripts.ingest_drosophila_suzukii_figshare_mk_selection import ingest_drosophila_suzukii_figshare_mk_selection


class IngestDrosophilaSuzukiiFigshareMkSelectionTests(unittest.TestCase):
    def test_ingest_preserves_sources_and_updates_metadata(self):
        record = EvidenceRecord(
            record_id="swd_figshare_mk_selection:DS20_00004020:r1",
            lane="genome_features",
            source=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
            title="Drosophila suzukii Figshare MK selection row: DS20_00004020",
            text="Figshare McDonald-Kreitman selection row for Drosophila suzukii gene DS20_00004020.",
            species="Drosophila suzukii",
            url="https://figshare.com/articles/dataset/Suzukii_Subpulchrella_Sig_MK_two_methods_csv/13366079/3",
            media_url=None,
            provenance=Provenance(
                source_id=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                locator="raw/figshare.csv#row/1",
                retrieved_at="2026-05-29T00:00:00Z",
            ),
            payload={"atom_type": "figshare_mk_selection_row", "d_suzukii_gene": "DS20_00004020"},
        )

        def fake_fetch_records(**kwargs):
            return DrosophilaSuzukiiFigshareMkSelectionResult(
                source_id=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                records=[record],
                gaps=[],
                raw_artifacts=["raw/figshare.csv"],
                requested_urls=["https://ndownloader.figshare.com/files/26251579"],
                parsed_row_count=1,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            with patch(
                "scripts.ingest_drosophila_suzukii_figshare_mk_selection.fetch_drosophila_suzukii_figshare_mk_selection_records",
                fake_fetch_records,
            ):
                result = ingest_drosophila_suzukii_figshare_mk_selection(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 1)
            self.assertEqual(result["parsed_row_count"], 1)
            self.assertEqual(result["source_counts"][DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID], 1)
            status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn(DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID, status)


if __name__ == "__main__":
    unittest.main()
