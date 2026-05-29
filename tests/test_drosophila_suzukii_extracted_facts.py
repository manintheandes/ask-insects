from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.drosophila_suzukii_extracted_facts import (
    DROSOPHILA_SUZUKII_EXTRACTED_FACTS_PROFILE,
    DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
)
from askinsects.sources.extracted_facts import build_extracted_fact_records


def write_swd_literature_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="swd:openalex:W1",
                lane="literature",
                source="drosophila_suzukii_core",
                title="Drosophila suzukii crop damage and behavior in berry crops",
                text=(
                    "Spotted wing drosophila paper about oviposition behavior, host fruit choice, "
                    "blueberry damage, trap monitoring, biological control, and management."
                ),
                species="Drosophila suzukii",
                url="https://example.org/swd-paper",
                media_url=None,
                provenance=Provenance(
                    source_id="drosophila_suzukii_core",
                    locator="raw/drosophila_suzukii/literature.json#W1",
                    retrieved_at="2026-05-28T00:00:00Z",
                    license="open metadata",
                    source_url="https://example.org/swd-paper",
                ),
                payload={
                    "ids": {"doi": "10.1234/swd.1"},
                    "supplementary_materials": [
                        {
                            "title": "Supplementary table: SWD crop observations",
                            "url": "https://example.org/swd-table.csv",
                            "file_type": "csv",
                            "license": "CC-BY",
                            "source": "publisher",
                        }
                    ],
                },
            ),
            EvidenceRecord(
                record_id="swd:openalex:W2",
                lane="literature",
                source="drosophila_suzukii_core",
                title="Drosophila suzukii insecticide susceptibility",
                text="Spotted wing drosophila resistance paper with spinosad mortality bioassay data.",
                species="Drosophila suzukii",
                url="https://example.org/swd-paper-2",
                media_url=None,
                provenance=Provenance(
                    source_id="drosophila_suzukii_core",
                    locator="raw/drosophila_suzukii/literature.json#W2",
                    retrieved_at="2026-05-28T00:00:00Z",
                    license="open metadata",
                    source_url="https://example.org/swd-paper-2",
                ),
                payload={"ids": {"doi": "10.1234/swd.2"}},
            ),
        ]
    )


class DrosophilaSuzukiiExtractedFactsTests(unittest.TestCase):
    def test_builds_swd_supplement_audit_and_manifest_without_aedes_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_literature_fixture(artifact_dir)

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
                profile=DROSOPHILA_SUZUKII_EXTRACTED_FACTS_PROFILE,
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID)
            self.assertEqual(result.source_record_count, 2)
            self.assertEqual(result.supplement_audit_record_count, 2)
            manifests = [record for record in result.records if record.payload.get("fact_type") == "supplement_manifest"]
            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0].source, DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID)
            self.assertEqual(manifests[0].species, "Drosophila suzukii")
            joined_text = "\n".join(record.text for record in result.records)
            self.assertIn("Drosophila suzukii", joined_text)
            self.assertNotIn("Aedes aegypti", joined_text)

    def test_downloaded_table_rows_are_queryable_with_swd_raw_locator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_literature_fixture(artifact_dir)

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, "https://example.org/swd-table.csv")
                return "fruit,random measurement\nblueberry,12\n".encode("utf-8")

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-28T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=3,
                max_supplement_bytes=100000,
                profile=DROSOPHILA_SUZUKII_EXTRACTED_FACTS_PROFILE,
            )

            self.assertEqual(result.downloaded_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_row_count, 1)
            row_records = [
                record
                for record in result.records
                if record.payload.get("confidence") == "parsed"
            ]
            self.assertGreaterEqual(len(row_records), 1)
            self.assertTrue(
                any(
                    "raw/drosophila_suzukii_extracted_facts/supplements/" in record.provenance.locator
                    for record in row_records
                )
            )
            audit = [
                record
                for record in result.records
                if record.payload.get("fact_type") == "supplement_audit"
                and record.payload.get("source_record_id") == "swd:openalex:W1"
            ][0]
            self.assertIn(
                audit.payload["fields"]["coverage_status"],
                {"supplement_rows_parsed_no_structured_lane_match", "supplement_rows_promoted"},
            )


if __name__ == "__main__":
    unittest.main()
