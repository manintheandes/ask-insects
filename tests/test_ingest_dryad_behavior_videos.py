import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from scripts.ingest_dryad_behavior_videos import ingest_dryad_behavior_videos
from tests.test_dryad_behavior_videos_source import DryadFetcher


class IngestDryadBehaviorVideosTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            from askinsects.records import EvidenceRecord, Provenance

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

            result = ingest_dryad_behavior_videos(
                artifact_dir=artifact_dir,
                dois=["10.5061/dryad.example"],
                fetch_json=DryadFetcher(),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane"
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[("dryad_aedes_behavior_videos", "behavior")], 2)
            self.assertEqual(counts[("dryad_aedes_behavior_videos", "media")], 1)
            payload_rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select count(*) as n from record_payloads where source='dryad_aedes_behavior_videos'"
            )
            self.assertEqual(payload_rows[0]["n"], 3)


if __name__ == "__main__":
    unittest.main()
