import tempfile
import unittest
from pathlib import Path
from unittest import mock

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_drosophila_suzukii_ncbi_nucleotide import ingest_drosophila_suzukii_ncbi_nucleotide
from tests.test_drosophila_suzukii_ncbi_nucleotide_source import ESEARCH, ESUMMARY


class IngestDrosophilaSuzukiiNcbiNucleotideTests(unittest.TestCase):
    def test_ingest_updates_nucleotide_lane_without_removing_core_barcodes(self):
        def fake_fetch(url):
            if "esearch.fcgi" in url:
                return ESEARCH
            if "esummary.fcgi" in url:
                return ESUMMARY
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd:bold:barcode:SWD1",
                        lane="dna_barcodes",
                        source="drosophila_suzukii_core",
                        title="BOLD DNA barcode SWD1",
                        text="BOLD barcode with GenBank accession PV080836.",
                        species="Drosophila suzukii",
                        url="https://example.org/bold/SWD1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_core",
                            locator="raw/bold.tsv#row/1",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                        payload={"genbank_accession": "PV080836"},
                    )
                ]
            )

            result = ingest_drosophila_suzukii_ncbi_nucleotide(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                max_results=10,
                page_size=10,
                delay_seconds=0,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["bold_accession_matched_count"], 1)
            counts = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, count(*) as n from records group by source order by source",
                limit=10,
            )
            by_source = {row["source"]: int(row["n"]) for row in counts}
            self.assertEqual(by_source["drosophila_suzukii_core"], 1)
            self.assertEqual(by_source["drosophila_suzukii_ncbi_nucleotide"], 2)

    def test_failed_refresh_preserves_existing_nucleotide_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="swd_ncbi_nucleotide:nuccore:old",
                        lane="dna_barcodes",
                        source="drosophila_suzukii_ncbi_nucleotide",
                        title="Existing GenBank row",
                        text="Existing GenBank row should be preserved.",
                        species="Drosophila suzukii",
                        url="https://www.ncbi.nlm.nih.gov/nuccore/old",
                        media_url=None,
                        provenance=Provenance(
                            source_id="drosophila_suzukii_ncbi_nucleotide",
                            locator="raw/old.json#result/old",
                            retrieved_at="2026-05-29T00:00:00Z",
                        ),
                    )
                ]
            )

            with mock.patch(
                "askinsects.sources.drosophila_suzukii_ncbi_nucleotide.fetch_json_url",
                side_effect=RuntimeError("offline"),
            ):
                result = ingest_drosophila_suzukii_ncbi_nucleotide(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-05-29T00:00:00Z",
                )

            self.assertFalse(result["ok"])
            self.assertTrue(result["preserved_existing"])
            # preserved_existing is True is the real guard against record loss here;
            # the loosened count only tolerates added source_gap EvidenceRecords.
            self.assertGreaterEqual(result["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
