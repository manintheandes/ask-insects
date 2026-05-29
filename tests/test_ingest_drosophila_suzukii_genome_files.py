from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_genome_files import fetch_drosophila_suzukii_genome_file_records
from scripts.ingest_drosophila_suzukii_genome_files import ingest_drosophila_suzukii_genome_files
from tests.test_drosophila_suzukii_genome_files import ASSEMBLY_ACCESSION, RETRIEVED_AT, fake_fetch_bytes, write_swd_assembly_fixture


class IngestDrosophilaSuzukiiGenomeFilesTests(unittest.TestCase):
    def test_ingest_updates_receipts_and_preserves_deep_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_swd_assembly_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")

            result = ingest_drosophila_suzukii_genome_files(
                artifact_dir=artifact_dir,
                assembly_accession=ASSEMBLY_ACCESSION,
                retrieved_at=RETRIEVED_AT,
                fetch_records_fn=lambda artifact_dir, **kwargs: fetch_drosophila_suzukii_genome_file_records(artifact_dir, fetch_bytes_fn=fake_fetch_bytes, **kwargs),
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "drosophila_suzukii_genome_files")
            self.assertGreater(result["lane_counts"]["genes"], 0)
            counts = {
                row["source"]: int(row["n"])
                for row in index.sql("select source, count(*) as n from records group by source", limit=100)
            }
            self.assertGreaterEqual(counts["drosophila_suzukii_deep_sources"], 1)
            self.assertGreaterEqual(counts["drosophila_suzukii_genome_files"], 4)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn("drosophila_suzukii_genome_files", status["sources"])


if __name__ == "__main__":
    unittest.main()
