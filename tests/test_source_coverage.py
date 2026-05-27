from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.source_coverage import SOURCE_COVERAGE_SOURCE_ID, build_source_coverage_records
from scripts.ingest_source_coverage import ingest_source_coverage


RETRIEVED_AT = "2026-05-27T00:00:00Z"


def write_coverage_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "scope": {
                    "primary_taxon": "Aedes aegypti",
                    "strategy": "Build the most comprehensive Aedes aegypti intelligence system.",
                },
                "source_contract_gates": ["mapped", "accessible", "atomically_queryable", "receipted", "ask_surface_wired"],
                "domains": [
                    {
                        "id": "behavior",
                        "priority": 3,
                        "status": "partial_source_grade",
                        "target_state": "Host-seeking, feeding, oviposition, mating, flight, larval, and assay behavior rows.",
                        "current_sources": ["aedes_video_atoms", "mendeley_aedes_behavior_media"],
                        "current_gates": {
                            "mapped": "yes",
                            "accessible": "yes",
                            "atomically_queryable": "partial",
                            "receipted": "yes",
                            "ask_surface_wired": "partial",
                        },
                        "current_evidence": ["motion rows are queryable"],
                        "required_next_sources": [
                            "decoded trajectory tables and assay-level rows from Dryad behavior archives",
                            "repellent and attractant assay datasets",
                        ],
                        "completion_evidence": ["behavior questions answer from records or explicit gaps"],
                    },
                    {
                        "id": "images",
                        "priority": 5,
                        "status": "partial_source_grade",
                        "target_state": "Inspectable Aedes still images with labels.",
                        "current_sources": ["aedes_image_atoms"],
                        "current_gates": {
                            "mapped": "yes",
                            "accessible": "yes",
                            "atomically_queryable": "partial",
                            "receipted": "yes",
                            "ask_surface_wired": "yes",
                        },
                        "current_evidence": ["image labels are queryable"],
                        "required_next_sources": ["validated vision or manual labels for sex and anatomy"],
                        "completion_evidence": ["image questions return records or explicit gaps"],
                    },
                    {
                        "id": "video",
                        "priority": 6,
                        "status": "partial_source_grade",
                        "target_state": "Inspectable Aedes videos, motion rows, and explicit video gaps.",
                        "current_sources": ["aedes_video_atoms"],
                        "current_gates": {
                            "mapped": "yes",
                            "accessible": "yes",
                            "atomically_queryable": "partial",
                            "receipted": "yes",
                            "ask_surface_wired": "yes",
                        },
                        "current_evidence": ["keyframes and motion rows are queryable"],
                        "required_next_sources": ["broader repository sweeps and more licensed mirrors"],
                        "completion_evidence": ["video coverage questions answer from records or explicit gaps"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


class SourceCoverageTests(unittest.TestCase):
    def test_builds_overview_domain_and_gap_records_from_coverage_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            coverage_path = Path(tmpdir) / "coverage.json"
            write_coverage_fixture(coverage_path)

            records = build_source_coverage_records(coverage_path, retrieved_at=RETRIEVED_AT)

            self.assertEqual(records[0].record_id, "aedes_source_coverage:overview")
            self.assertEqual(records[0].source, SOURCE_COVERAGE_SOURCE_ID)
            self.assertEqual(records[0].lane, "source_coverage")
            domain_records = [record for record in records if record.payload and record.payload["atom_type"] == "source_coverage_domain"]
            gap_records = [record for record in records if record.payload and record.payload["atom_type"] == "source_coverage_gap"]
            self.assertEqual(len(domain_records), 3)
            self.assertEqual(len(gap_records), 4)
            self.assertTrue(any("decoded trajectory tables" in record.text for record in gap_records))
            behavior = next(record for record in domain_records if record.payload["domain"] == "behavior")
            self.assertIn("atomically_queryable=partial", behavior.text)

    def test_ingest_preserves_other_sources_and_updates_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            coverage_path = Path(tmpdir) / "coverage.json"
            write_coverage_fixture(coverage_path)
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
                        provenance=Provenance(source_id="mosquito_v1_fixtures", locator="fixture#taxonomy", retrieved_at=RETRIEVED_AT),
                    )
                ]
            )

            result = ingest_source_coverage(artifact_dir=artifact_dir, coverage_path=coverage_path, retrieved_at=RETRIEVED_AT)

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], SOURCE_COVERAGE_SOURCE_ID)
            self.assertEqual(result["domain_count"], 3)
            self.assertEqual(result["coverage_gap_count"], 4)
            rows = index.sql("select source, lane, count(*) as n from records group by source, lane", limit=100)
            counts = {(row["source"], row["lane"]): int(row["n"]) for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[(SOURCE_COVERAGE_SOURCE_ID, "source_coverage")], 8)
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn(SOURCE_COVERAGE_SOURCE_ID, status["sources"])
            self.assertEqual(status[SOURCE_COVERAGE_SOURCE_ID]["coverage_gap_count"], 4)

    def test_missing_coverage_question_uses_source_coverage_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            coverage_path = Path(tmpdir) / "coverage.json"
            write_coverage_fixture(coverage_path)
            ingest_source_coverage(artifact_dir=artifact_dir, coverage_path=coverage_path, retrieved_at=RETRIEVED_AT)

            answer = answer_question("what is missing from Aedes coverage?", artifact_dir=artifact_dir, limit=3)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["source"], SOURCE_COVERAGE_SOURCE_ID)
            self.assertIn("Missing Aedes aegypti", answer["evidence"][0]["text"])

    def test_domain_specific_missing_coverage_question_uses_source_coverage_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            coverage_path = Path(tmpdir) / "coverage.json"
            write_coverage_fixture(coverage_path)
            ingest_source_coverage(artifact_dir=artifact_dir, coverage_path=coverage_path, retrieved_at=RETRIEVED_AT)

            answer = answer_question("what is missing from Aedes video coverage?", artifact_dir=artifact_dir, limit=3)

            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "evidence")
            self.assertEqual(answer["evidence"][0]["source"], SOURCE_COVERAGE_SOURCE_ID)
            self.assertEqual(answer["evidence"][0]["record_id"], "aedes_source_coverage:gap:video:1")
            self.assertIn("broader repository sweeps", answer["evidence"][0]["text"])


if __name__ == "__main__":
    unittest.main()
