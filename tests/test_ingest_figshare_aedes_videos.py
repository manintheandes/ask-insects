import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_figshare_aedes_videos import ingest_figshare_aedes_videos
from tests.test_figshare_aedes_videos_source import FigshareFetcher


class IngestFigshareAedesVideosTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
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

            result = ingest_figshare_aedes_videos(
                artifact_dir=artifact_dir,
                fetch_json=FigshareFetcher(),
                retrieved_at="2026-05-25T00:00:00Z",
                query="Aedes aegypti video",
                page_size=10,
            )

            self.assertTrue(result["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane"
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[("figshare_aedes_videos", "media")], 2)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from record_payloads where source='figshare_aedes_videos'"
            )
            self.assertEqual(payload_rows[0]["n"], 2)
            gap_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from record_payloads where source='figshare_aedes_videos' and payload_json like '%\"atom_type\": \"video_gap\"%'"
            )
            self.assertEqual(gap_rows[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
