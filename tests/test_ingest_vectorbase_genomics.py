import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_vectorbase_genomics import ingest_vectorbase_genomics
from tests.test_vectorbase_genomics_source import write_fake_vectorbase_files


class IngestVectorBaseGenomicsTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:taxonomy:aedes",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti",
                        text="Aedes aegypti taxonomy fixture.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#taxonomy",
                            retrieved_at="2026-05-23T00:00:00Z",
                        ),
                    )
                ]
            )
            file_urls = write_fake_vectorbase_files(root / "downloads")

            result = ingest_vectorbase_genomics(
                artifact_dir=artifact_dir,
                file_urls=file_urls,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane"
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[("vectorbase_aedes_genomics", "genes")], 1)
            self.assertEqual(counts[("vectorbase_aedes_genomics", "transcripts")], 2)
            self.assertEqual(counts[("vectorbase_aedes_genomics", "proteins")], 1)
            self.assertEqual(counts[("vectorbase_aedes_genomics", "genome_features")], 5)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from record_payloads where source='vectorbase_aedes_genomics'"
            )
            self.assertEqual(payload_rows[0]["n"], 9)


if __name__ == "__main__":
    unittest.main()
