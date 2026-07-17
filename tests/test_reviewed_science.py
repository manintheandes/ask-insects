from __future__ import annotations

from dataclasses import replace
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

    def test_substrate_stiffness_paraphrase_selects_texture_topic(self):
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
            catalog_path = self.write_catalog(root)
            questions = (
                (
                    "What sensory evidence links substrate stiffness to egg-laying "
                    "decisions in spotted-wing drosophila?"
                ),
                "What links a stiff oviposition surface to sensory behavior in SWD?",
                "Can SWD sense a stiffer egg-laying surface?",
                "Do SWD females prefer the stiffest substrate when laying eggs?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(
                        index,
                        question,
                        catalog_path=catalog_path,
                    )

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertIn("preferred the harder", answer["answer"])
                    self.assertIn("TRP and DEG/ENaC", answer["answer"])

    def test_recovery_reversibility_paraphrases_select_habituation_topic(self):
        record_id = "swd:openalex_literature:openalex:W3199560580"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator="raw/swd.json#works/W3199560580",
                    )
                ]
            )
            questions = (
                "What would a recovery phase after odor removal tell us about whether an SWD avoidance effect is reversible?",
                "How should I test the reversibility of SWD avoidance once the volatile is gone?",
                "Does SWD avoidance return to baseline after the odor source is removed?",
                "Would SWD avoidance rebound after repellent washout?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertIn("Compare naive and pre-exposed flies", answer["answer"])
                    self.assertIn("does not prove long-term field persistence", answer["answer"])

    def test_aedes_spatial_repellency_is_separated_from_knockdown_and_mortality(self):
        record_id = "openalex:W3048721146"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="aedes_literature_openalex",
                        locator="raw/aedes.json#works/W3048721146",
                    )
                ]
            )
            questions = (
                "If transfluthrin-treated material reduces Aedes aegypti landings, "
                "what measurements would tell me whether I am seeing spatial "
                "repellency, knockdown, or mortality?",
                "How should I separate airborne Aedes avoidance from knockdown and toxicity?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertEqual(answer["evidence"][0]["record_id"], record_id)
                    for fragment in (
                        "paired non-contact",
                        "mesh barrier",
                        "1-minute intervals",
                        "30 minutes",
                        "greater non-contact escape",
                        "reduced escape can indicate knockdown",
                        "contact excitation",
                        "escaped and remaining",
                        "24-hour mortality",
                        "knockdown can suppress escape",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())
                    self.assertNotIn(
                        "less escape as repellency",
                        answer["answer"].casefold(),
                    )

    def test_swd_choice_controls_cover_solvent_airflow_and_locomotor_confounds(self):
        record_ids = (
            "swd:openalex_literature:openalex:W4411730655",
            "swd:openalex_literature:openalex:W4213332511",
            "swd_olfaction_literature:pubmed:26486360",
            "swd:openalex_literature:openalex:W3199560580",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator=(
                            "/Users/josh/.local/share/ask-insects/main/artifacts/"
                            "mosquito-v1/raw/swd.json#works/"
                            f"{record_id.rsplit(':', 1)[-1]}"
                            if position == 0
                            else f"raw/swd.json#works/{record_id.rsplit(':', 1)[-1]}"
                        ),
                    )
                    for position, record_id in enumerate(record_ids)
                ]
            )
            questions = (
                "For an SWD choice assay, what controls separate odor repellency "
                "from solvent, airflow, or impaired locomotion?",
                "In a two-arm SWD odor test, how should I control the carrier and air "
                "stream and verify that lower treated-side occupancy is avoidance "
                "rather than motor suppression?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertIn("carrier", answer["answer"].lower())
                    self.assertIn("airflow", answer["answer"].lower())
                    self.assertIn("locomot", answer["answer"].lower())
                    self.assertEqual(
                        {item["record_id"] for item in answer["evidence"]},
                        set(record_ids),
                    )
                    locators = [
                        item["provenance"]["locator"]
                        for item in answer["evidence"]
                    ]
                    self.assertIn(
                        "artifacts/mosquito-v1/raw/swd.json#works/W4411730655",
                        locators,
                    )
                    self.assertTrue(
                        all(not locator.startswith("/") for locator in locators)
                    )

    def test_aedes_microclimate_chamber_paraphrase_selects_environment_controls(self):
        record_ids = (
            "openalex:W3048721146",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="aedes_literature_openalex",
                        locator=f"raw/aedes.json#records/{position}",
                    )
                    for position, record_id in enumerate(record_ids)
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "When testing an airborne Aedes repellent, how should I standardize "
                "the air plume and microclimate so chamber occupancy is interpretable?",
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer["ok"])
        self.assertIn("airflow direction and speed", answer["answer"])
        self.assertIn("temperature and relative humidity", answer["answer"])
        self.assertIn("R&D design recommendations", answer["answer"])
        self.assertIn("does not provide a universal standard", answer["answer"])
        self.assertIn("complete product-specific", answer["answer"])
        self.assertIn("source gap", answer["answer"])
        self.assertEqual(
            {item["record_id"] for item in answer["evidence"]},
            set(record_ids),
        )

    def test_aedes_human_subject_preparation_routes_to_official_guidance(self):
        record_id = "human_repellent_guidance:epa:810.3700"
        questions = (
            "For an Aedes aegypti arm-in-cage repellent assay, which participant "
            "conditions should be standardized before exposure, and which parts "
            "are official guidance versus my R&D interpretation?",
            "Which volunteer preparation controls does EPA require before a "
            "human-skin mosquito repellent efficacy test?",
            "What should we standardize in subjects before an arm in cage trial, "
            "and which extra covariates would be our study-design choices rather "
            "than EPA rules?",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="human_repellent_testing_guidance",
                        locator=(
                            "https://www.epa.gov/system/files/documents/2023-12/"
                            "1d.-oppts-810.3700-guidelines-july-7-2010.pdf#page=11"
                        ),
                    )
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question in questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {record_id},
                )
                for fragment in (
                    "unscented detergent",
                    "at least twelve hours",
                    "official EPA guidance",
                    "R&D design choices",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_repaired_aedes_topics_label_inference_recommendations_and_source_gaps(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        record_ids = sorted(
            {
                record_id
                for topic in catalog["topics"]
                for record_id in topic["source_record_ids"]
            }
        )
        cases = (
            (
                "What phases of host-seeking suppression are reported after an Aedes blood meal?",
                ("summarizes earlier work", "cannot independently verify", "R&D recommendation"),
            ),
            (
                "Did the nanostructured citronella paper directly measure volatile release rate?",
                ("did not directly measure", "inferred prolonged release", "skin permeation"),
            ),
            (
                "Is humidity directly proven to be redundant with heat and odor during Aedes host seeking?",
                ("source gap", "does not contain a direct primary measurement", "not established"),
            ),
            (
                "How should our volatile Aedes repellent program report source loading and exposure?",
                (
                    "R&D reporting recommendation",
                    "not chemically measured",
                    "did not directly measure",
                    "complete product-specific package",
                    "source gap",
                ),
            ),
            (
                "Does a standard complete-protection-time test establish durability after UV and sweat?",
                (
                    "WHO and EPA",
                    "does not establish",
                    "source gap",
                    "R&D challenge design",
                ),
            ),
            (
                "When can we call reduced Aedes repellent sensitivity inherited resistance?",
                ("operational decision rule", "not a universal definition", "cannot be assumed equivalent"),
            ),
        )

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
            answers = [build_reviewed_science_answer(index, question) for question, _ in cases]

        for (question, expected_fragments), answer in zip(cases, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                for fragment in expected_fragments:
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

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

    def test_catalog_rejects_internal_program_rows_as_scientific_evidence(self):
        payload = catalog_payload()
        payload["topics"][0]["source_record_ids"] = [
            "insect_intelligence_programs:product:swd_crop_repellent:readiness:mode_of_action"
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedScienceError,
                "original scientific or official source",
            ):
                load_reviewed_science_catalog(path)

    def test_reviewed_answer_rejects_record_without_original_public_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            record = evidence_record(
                "study:texture",
                source_id="drosophila_suzukii_core",
                locator="raw/swd.json#works/W3037850025",
            )
            index.upsert_records([replace(record, url=None)])

            answer = build_reviewed_science_answer(
                index,
                "How does SWD fruit texture affect egg laying?",
                catalog_path=self.write_catalog(root),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertFalse(answer["ok"])
        self.assertIn("original public source URL", answer["source_gap"]["reason"])

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

    def test_repaired_science_topics_answer_neighboring_research_questions(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        record_ids = sorted(
            {
                record_id
                for topic in catalog["topics"]
                for record_id in topic["source_record_ids"]
            }
        )
        cases = (
            (
                "How should I interpret a Y-tube or planar olfactometer result "
                "before claiming crop protection from a repellent?",
                "swd:openalex_literature:openalex:W4413971464",
                (
                    "orientation or choice",
                    "does not by itself measure egg laying",
                    "direct crop and damage outcomes",
                ),
            ),
            (
                "Which fermentation chemicals and tested concentration ranges separated SWD from D. melanogaster in Y-tube and EAG assays?",
                "swd:openalex_literature:openalex:W4365509323",
                ("2-phenylethanol", "0.01-0.1%", "1-10%", "0.1-1%"),
            ),
            (
                "Which missing evidence would show SWD resistance is heritable rather than learned after pre-exposure?",
                "swd:openalex_literature:openalex:W3199560580",
                ("cross-resistance", "common-garden", "field phenotype frequencies"),
            ),
            (
                "How should I connect fewer SWD eggs with later larval survival and marketable yield across different fruit ripeness states?",
                "swd_pubmed_literature:pubmed:39769586",
                ("fruit condition", "ripeness"),
            ),
            (
                "How was Aedes aversive odor learning trained and when was memory tested?",
                "openalex:W4315621418",
                ("mechanical shock", "10 pairings", "2-minute", "24 hours"),
            ),
            (
                "What measurements separate sensory detection of a mosquito repellent from the later decision to avoid it in female Aedes aegypti?",
                "openalex:W3179105761",
                ("electroantennogram", "positive control", "non-contact", "1 ppm", "orco", "sodium-channel"),
            ),
            (
                "Which adult, egg, larval, feeding, and crop-damage measurements should a diamondback moth repellent study track?",
                "dbm:openalex:W2114561940",
                ("adult orientation", "egg hatch", "leaf damage"),
            ),
            (
                "If a diamondback moth compound reduces landings for 10 minutes but moth activity returns by 30 minutes, what measurements would distinguish temporary spatial avoidance from toxicity?",
                "dbm:openalex:W4387738540",
                (
                    "fewer landings alone does not prove spatial avoidance",
                    "non-contact and contact arms",
                    "recovery",
                    "delayed mortality",
                    "R&D recommendation",
                ),
            ),
            (
                "How do I tell whether reduced alighting by Plutella xylostella followed by recovery is repellency or reversible knockdown?",
                "dbm:openalex:W1994548084",
                ("clean-air locomotion", "knockdown", "same moths", "10-to-30-minute"),
            ),
            (
                "Does a caprylic-capric acid blend reduce SWD egg laying, and has anyone isolated an airborne effect from substrate contact?",
                "swd:openalex_literature:openalex:W4386466923",
                ("99%", "64%", "caprylic", "capric", "spatial", "contact"),
            ),
            (
                "When commensal growth is present, does SWD oviposition differ on 1% and 3% agar?",
                "swd:openalex_literature:openalex:W3124252639",
                (
                    "1% agar",
                    "3% agar",
                    "Drosophila melanogaster",
                    "Drosophila biarmipes",
                    "laid more eggs",
                    "no significant preference or aversion",
                ),
            ),
            (
                "For a volatile Aedes repellent, which measurements keep applied dose separate from mosquito exposure, and which formulation-delivery evidence is still incomplete?",
                "openalex:W4313493759",
                (
                    "applied mass",
                    "release rate",
                    "airborne concentration",
                    "source-to-mosquito distance",
                    "skin permeation",
                    "did not directly measure",
                    "R&D reporting recommendation",
                ),
            ),
            (
                "What did SWD raspberry trials show about 1-octen-3-ol aerosol puffers versus passive vials and release schedules?",
                "swd:openalex_literature:openalex:W3046652911",
                ("20%", "42-55%", "dawn and dusk", "low fly"),
            ),
            (
                "Which measurements distinguish a directional SWD odor response from general locomotor suppression?",
                "swd:openalex_literature:openalex:W4213332511",
                ("heading", "upwind", "clean air", "speed", "immobility", "mating"),
            ),
            (
                "Our flight mill logged one spotted wing drosophila traveling 283 meters in 24 hours, while most flies never initiated flight. Can we use 283 meters as the minimum width of a crop-repellent buffer, or what does the free-flight comparison actually let us infer?",
                "swd:openalex_literature:openalex:W4290861466",
                (
                    "No.",
                    "401 adults",
                    "15.7%",
                    "18.0%",
                    "13.4%",
                    "283.03 m",
                    "not a design distance",
                ),
            ),
            (
                "Can the longest tethered SWD flight define field treatment spacing, or does the free-flight chamber show that the assay changes the result?",
                "swd:openalex_literature:openalex:W4290861466",
                (
                    "one Drosophila suzukii",
                    "14.0%",
                    "36.7 seconds",
                    "11.7 seconds",
                    "mark-release-recapture",
                ),
            ),
            (
                "Should I interpret SWD adult oviposition choices as protein-to-carbohydrate preference, or as substrate hardness?",
                "swd_traits:pubmed:28592264",
                ("lower protein", "not nutritional composition", "hardness"),
            ),
            (
                "Why did transfluthrin look better in large-cage Aedes trials than in open-field landing collections?",
                "openalex:W4399119561",
                ("negligible", "50-60%", "moderate pyrethroid resistance", "15 g"),
            ),
            (
                "Can we transfer an Anopheles DEET response to Aedes, or are close-range repellent responses species-specific?",
                "openalex:W3013059076",
                ("lemongrass", "PMD", "eugenol", "DEET", "0.5 cm", "30 seconds"),
            ),
            (
                "Do Aedes aegypti populations from different African environments have the same human-odor preference?",
                "openalex:W3044645851",
                ("27", "83%", "dry-season", "human population density"),
            ),
            (
                "Does thermal infrared alone drive Aedes host seeking, and which antennal sensors are involved?",
                "openalex:W4401794442",
                ("34 C", "CO2", "human odor", "TRPA1", "opsins"),
            ),
            (
                "When the same people provide skin-odor samples repeatedly, what do donor consistency, carboxylic acids, and ionotropic-receptor mutants tell us about why female Aedes differ in attraction?",
                "aedes_olfaction_literature:pubmed:36261039",
                (
                    "months to years",
                    "carboxylic acids",
                    "validation cohort",
                    "ionotropic-receptor",
                    "association",
                ),
            ),
            (
                "What evidence shows that human metabolic differences change "
                "Aedes aegypti attraction, and how should we control for donor effects?",
                "aedes_olfaction_literature:pubmed:36261039",
                (
                    "150-person cohort",
                    "associations",
                    "donor identity",
                    "sampling day",
                    "include multiple donors",
                ),
            ),
            (
                "Should a diamondback moth release schedule follow period and timeless expression or measured adult locomotor activity?",
                "dbm:openalex:W4407297126",
                ("period", "timeless", "temperature-driven", "light-suppressed"),
            ),
            (
                "For diamondback moth, how should I separate citronella effects on larval movement, feeding, mortality, adult oviposition, and field abundance?",
                "dbm:openalex:W4387738540",
                ("3 and 4 mL/L", "100%", "48 hours", "Diadegma"),
            ),
            (
                "What controls Aedes host seeking after a blood meal, and is there a proven universal 24-hour phase?",
                "aedes_primary_behavior:pmc:PMC3794971",
                (
                    "summarizes earlier work",
                    "abdominal-distention-associated",
                    "three days",
                    "universal 24-hour phase",
                ),
            ),
            (
                "After an Aedes aegypti female feeds, is abdominal swelling the whole reason she stops seeking hosts for the next 24 hours?",
                "aedes_primary_behavior:pmc:PMC3794971",
                (
                    "summarizes earlier work",
                    "oocyte-development-associated",
                    "three days",
                    "universal 24-hour phase",
                ),
            ),
            (
                "If an Aedes aegypti female's abdomen is experimentally distended without blood, would reduced host seeking prove that blood chemistry caused the suppression?",
                "aedes_primary_behavior:pmc:PMC3794971",
                (
                    "abdominal-distention-associated",
                    "oocyte-development-associated",
                    "cannot independently verify",
                ),
            ),
            (
                "Is NPYLR1 required for post-blood-meal host-seeking suppression in Aedes aegypti?",
                "aedes_primary_behavior:pmc:PMC3794971",
                ("null mutants", "not required"),
            ),
            (
                "How long did the controlled-release citronella formulation protect people in the Aedes study?",
                "aedes_primary_behavior:pmc:PMC9866038:table8",
                (
                    "4.0 +/- 0.0 hours",
                    "0.3 +/- 0.5 hours",
                    "Table 8 labels N=6",
                    "Methods says that four formulations were evaluated on three participants",
                    "sample size is unresolved",
                ),
            ),
            (
                "What direct plant-cue evidence identifies antennally active host volatiles in diamondback moth before repellent screening?",
                "dbm:openalex:W4409241407",
                ("eight", "antennal responses", "field trapping", "does not prove"),
            ),
        )

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
            for question, expected_record_id, expected_fragments in cases:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertIn(
                        expected_record_id,
                        {item["record_id"] for item in answer["evidence"]},
                    )
                    for fragment in expected_fragments:
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

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
            with (
                patch.object(
                    SourceIndex,
                    "summary",
                    side_effect=AssertionError(
                        "normal answers must not scan the full index"
                    ),
                ),
                patch(
                    "askinsects.answer.build_reviewed_science_answer",
                    return_value=reviewed,
                ) as builder,
            ):
                answer = answer_question(
                    "Could an unfamiliar insect respond to this stimulus?",
                    artifact_dir=artifact_dir,
                )

        self.assertEqual(answer, reviewed)
        builder.assert_called_once()


if __name__ == "__main__":
    unittest.main()
