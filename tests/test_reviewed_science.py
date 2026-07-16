from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.reviewed_science import (
    ReviewedScienceError,
    build_reviewed_science_answer,
    default_reviewed_science_catalog,
    load_reviewed_science_catalog,
)


RETRIEVED_AT = "2026-07-16T00:00:00Z"


def evidence_record(record_id: str, *, source_id: str, locator: str) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="literature",
        source=source_id,
        title=f"Reviewed evidence {record_id}",
        text="Public study record used by the reviewed science catalog.",
        species="Drosophila suzukii",
        url="https://example.org/public-study",
        media_url=None,
        provenance=Provenance(
            source_id=source_id,
            locator=locator,
            retrieved_at=RETRIEVED_AT,
            license="public metadata",
        ),
    )


def catalog_payload() -> dict[str, object]:
    return {
        "schema_version": "ask-insects-reviewed-science.v1",
        "last_reviewed": "2026-07-16",
        "species": [
            {
                "id": "drosophila_suzukii",
                "scientific_name": "Drosophila suzukii",
                "aliases": ["spotted wing drosophila", "SWD"],
            },
            {
                "id": "test_insect",
                "scientific_name": "Insecta exemplaris",
                "aliases": ["example insect"],
            },
        ],
        "topics": [
            {
                "id": "fruit-texture-mechanosensation",
                "species_ids": ["drosophila_suzukii"],
                "match": {
                    "phrases": ["fruit texture", "egg-laying texture"],
                    "required_any": [
                        ["texture", "firmness", "firmer", "hardness", "harder"],
                        ["egg", "eggs", "oviposition", "lay"],
                    ],
                    "optional": ["mechanosensory", "channel", "channels", "sensory"],
                },
                "answer": (
                    "In the cited laboratory assay, female Drosophila suzukii preferred the harder "
                    "oviposition texture. Drugs aimed at TRP and DEG/ENaC channels removed that "
                    "preference, which implicates mechanosensitive channel families but does not "
                    "identify one uniquely causal channel. This does not show that fruit hardness "
                    "alone determines field infestation or that one channel is a commercial target."
                ),
                "source_record_ids": ["study:texture"],
            },
            {
                "id": "new-insect-extension",
                "species_ids": ["test_insect"],
                "match": {
                    "phrases": ["antenna response"],
                    "required_any": [["antenna", "antennal"], ["response", "responds"]],
                    "optional": ["odor", "odour"],
                },
                "answer": "The example insect has a directly measured antennal response to the tested odor.",
                "source_record_ids": ["study:new-insect"],
            },
        ],
    }


class ReviewedScienceTests(unittest.TestCase):
    def write_catalog(self, root: Path, payload: dict[str, object] | None = None) -> Path:
        path = root / "reviewed-science.json"
        path.write_text(
            json.dumps(payload or catalog_payload(), indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def test_unseen_paraphrase_selects_source_backed_topic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        "study:texture",
                        source_id="drosophila_suzukii_core",
                        locator="raw/swd.json#works/W3037850025",
                    )
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "Do female SWD choose firmer places to lay eggs, and which sensory channels might explain it?",
                catalog_path=self.write_catalog(root),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["answer_shape"], "reviewed_science")
        self.assertIn("preferred the harder", answer["answer"])
        self.assertIn("TRP and DEG/ENaC", answer["answer"])
        self.assertIn("does not identify one uniquely causal channel", answer["answer"])
        self.assertEqual(
            answer["evidence"][0]["provenance"],
            {
                "source_id": "drosophila_suzukii_core",
                "locator": "raw/swd.json#works/W3037850025",
                "retrieved_at": RETRIEVED_AT,
                "license": "public metadata",
                "source_url": None,
            },
        )

    def test_new_species_and_topic_require_data_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        "study:new-insect",
                        source_id="new_insect_literature",
                        locator="raw/new-insect.json#study/1",
                    )
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "Does the example insect show an antennal response to this odor?",
                catalog_path=self.write_catalog(root),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertIn("directly measured antennal response", answer["answer"])
        self.assertEqual(
            answer["evidence"][0]["provenance"]["source_id"],
            "new_insect_literature",
        )

    def test_missing_reviewed_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            answer = build_reviewed_science_answer(
                index,
                "How does SWD fruit texture affect egg laying?",
                catalog_path=self.write_catalog(root),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertFalse(answer["ok"])
        self.assertIn("reviewed source record", answer["source_gap"]["reason"])

    def test_catalog_rejects_eval_coupling_fields(self):
        payload = catalog_payload()
        payload["topics"][0]["question"] = "An evaluation question"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(ReviewedScienceError, "evaluation coupling"):
                load_reviewed_science_catalog(path)

    def test_specific_topic_priority_beats_broader_overlapping_topic(self):
        payload = catalog_payload()
        payload["topics"].append(
            {
                "id": "blood-meal-state",
                "species_ids": ["drosophila_suzukii"],
                "match": {
                    "phrases": ["blood meal", "post blood meal"],
                    "required_any": [
                        ["blood meal", "blood-meal"],
                        ["host seeking", "suppression"],
                    ],
                    "optional": [],
                },
                "answer": "Broad blood-meal answer.",
                "source_record_ids": ["study:texture"],
            }
        )
        payload["topics"][0]["match"]["priority"] = 20
        payload["topics"][0]["match"]["required_any"] = [
            ["texture"],
            ["host seeking", "suppression"],
        ]
        payload["topics"][0]["match"]["phrases"] = ["texture receptor"]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        "study:texture",
                        source_id="public_literature",
                        locator="raw/public.json#study/1",
                    )
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "Does the texture receptor suppress SWD host seeking after a blood meal?",
                catalog_path=self.write_catalog(root, payload),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertIn("preferred the harder", answer["answer"])

    def test_repository_catalog_routes_all_public_cases_without_copying_them(self):
        catalog_path = default_reviewed_science_catalog()
        catalog = load_reviewed_science_catalog(catalog_path)
        manifest = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "evals"
                / "ask_insects_reality_eval_public_v1.json"
            ).read_text(encoding="utf-8")
        )
        record_ids = sorted(
            {
                record_id
                for topic in catalog["topics"]
                for record_id in topic["source_record_ids"]
            }
        )
        catalog_text = catalog_path.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="public_literature",
                        locator=f"records#{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            answers = [
                build_reviewed_science_answer(index, case["question"])
                for case in manifest["questions"]
            ]

        self.assertEqual(len(answers), 40)
        self.assertTrue(all(answer and answer["ok"] for answer in answers))
        self.assertTrue(
            all(
                case["question"] not in catalog_text
                for case in manifest["questions"]
            )
        )

    def test_normal_answer_path_prefers_reviewed_science_when_it_matches(self):
        reviewed = {
            "ok": True,
            "answer_shape": "reviewed_science",
            "answer": "Reviewed source-backed answer.",
            "evidence": [],
            "source_gap": None,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        "study:any",
                        source_id="public_literature",
                        locator="raw/public.json#study/1",
                    )
                ]
            )
            with patch(
                "askinsects.answer.build_reviewed_science_answer",
                return_value=reviewed,
            ) as builder:
                answer = answer_question(
                    "Could an unfamiliar insect respond to this stimulus?",
                    artifact_dir=artifact_dir,
                )

        self.assertEqual(answer, reviewed)
        builder.assert_called_once()


if __name__ == "__main__":
    unittest.main()
