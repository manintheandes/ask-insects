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

    def test_swd_seasonal_morph_olfaction_paraphrases_use_direct_source(self):
        record_id = "swd_olfaction_literature:pubmed:29668908"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_olfaction_literature",
                        locator="raw/swd-olfaction.json#result/29668908",
                    )
                ]
            )
            questions = (
                "Summer-morph SWD avoid geosmin, but winter-morph females have weaker antennal responses and no significant geosmin aversion. How should we screen a year-round volatile without mistaking seasonal sensory plasticity for loss of detection?",
                "Could seasonal sensory plasticity make a volatile look inactive in winter-morph SWD?",
                "How should summer- and winter-morph SWD be compared in an antennal odor screen?",
                "Does a weaker winter-morph EAG mean female SWD cannot detect geosmin?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertEqual(answer["evidence"][0]["record_id"], record_id)
                    for fragment in (
                        "isoamyl acetate, acetic acid, and geosmin",
                        "winter-morph responses were reduced overall",
                        "summer morphs showed significant aversion",
                        "not proof that winter morphs cannot detect",
                        "matched delivered doses",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_swd_diurnal_oviposition_paraphrases_use_direct_source(self):
        record_id = "swd_olfaction_literature:pubmed:30379809"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_olfaction_literature",
                        locator="raw/swd-olfaction.json#result/30379809",
                    )
                ]
            )
            questions = (
                "Our SWD treatment and control cages were scored at different times of day. Could the apparent oviposition deterrence be a daily rhythm artifact, and how should the repeat be blocked?",
                "Could time of day make an SWD cage treatment look like it reduced egg laying?",
                "How should I block a daily SWD oviposition assay across treatment and control cages?",
                "Could a light-dark egg-laying rhythm confound an SWD repellent repeat?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertEqual(answer["evidence"][0]["record_id"], record_id)
                    for fragment in (
                        "2.4-fold",
                        "15.4-fold",
                        "9.1-fold and 25-fold",
                        "exceeded 30 degrees C",
                        "randomize both within replicated time blocks",
                    ):
                        self.assertIn(fragment, answer["answer"])

    def test_swd_delayed_oviposition_is_separated_from_spatial_avoidance(self):
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
                        locator=f"raw/swd.json#records/{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "In an SWD crop-repellent screen, what evidence would distinguish delayed egg-laying from true spatial avoidance?",
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["answer_shape"], "reviewed_science")
        self.assertEqual(
            {item["record_id"] for item in answer["evidence"]},
            set(record_ids),
        )
        self.assertIn("separate endpoints on separate timelines", answer["answer"])
        self.assertIn("normal locomotion", answer["answer"])
        self.assertIn("post-exposure catch-up", answer["answer"])
        self.assertIn("does not by itself prove field crop protection", answer["answer"])

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
                "In a non-contact transfluthrin escape chamber, does less Aedes escape "
                "mean stronger repellency, or could it mean knockdown?",
                "Could a lower Aedes aegypti exit rate under noncontact airborne exposure "
                "reflect locomotor impairment instead of weak avoidance?",
                "If more treated Aedes remain in a non-contact chamber, should I call that "
                "repellency or possible knockdown?",
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

    def test_topical_contact_does_not_route_to_a_spatial_source_gap(self):
        record_ids = (
            "openalex:W4403603462",
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
                        locator=f"raw/aedes.json#works/{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            questions = (
                "If mosquitoes touch a topical treatment and then do not bite, "
                "does that prove Aedes repellency at a distance?",
                "Can fewer Aedes bites after brief skin contact establish "
                "spatial repellency before contact?",
                "Does a topical Aedes repellent that works after touching skin "
                "prove a non-contact effect?",
                "An Aedes mosquito lands on treated skin and leaves before "
                "probing. What does that show about contact deterrence versus "
                "repellency before landing?",
                "Aedes approaches and lands normally, then disengages after its "
                "tarsi touch treated skin. Which evidence is pre-contact and "
                "which is post-contact?",
                "If an Aedes aegypti skin treatment leaves approaches unchanged but lowers "
                "probing after contact, can we call it distance repellency?",
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
                    [item["record_id"] for item in answer["evidence"]],
                    list(record_ids),
                )
                for fragment in (
                    "does not prove repellency at a distance",
                    "physical contact already occurred",
                    "multiple brief skin contacts",
                    "paired excito-repellency design",
                    "prevent contact with a barrier",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_dbm_antennal_field_blend_paraphrases_preserve_endpoint_boundary(self):
        record_ids = (
            "dbm:openalex:W4409241407",
            "dbm:openalex:W2114561940",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="plutella_xylostella_literature",
                        locator=f"raw/dbm.json#works/{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            questions = (
                "DBM antennae respond to a Brassica volatile blend and field "
                "traps catch adults. Does that prove reduced oviposition or crop injury?",
                "Can an antennally active broccoli odor blend with higher trap "
                "catch predict egg laying and leaf damage in Plutella xylostella?",
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
                    [item["record_id"] for item in answer["evidence"]],
                    list(record_ids),
                )
                for fragment in (
                    "antennal detection",
                    "adult field attraction",
                    "three-component blend",
                    "cannot substitute",
                    "eggs, larvae, leaf damage",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_aedes_environment_control_paraphrases_use_reviewed_source_gap(self):
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
                "What environmental controls belong in an Aedes vapor assay, and which "
                "carrier and delivery details are still unsupported by the cited evidence?",
                "Which Aedes vapor-assay environment variables and carrier-delivery "
                "details need to be standardized?",
                "In an Aedes airborne chamber test, what should we control about the "
                "environment and what formulation exposure details remain unknown?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertEqual(answer["evidence"][0]["record_id"], record_id)
                    for fragment in (
                        "recording temperature and relative humidity",
                        "define and monitor airflow direction and speed",
                        "carrier, release-rate, application-method, and delivery package",
                        "source gap",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

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
        self.assertIn("remaining on those papers", answer["answer"])
        self.assertIn("chamber-air concentration", answer["answer"])
        self.assertIn("not the paper's named treated-paper residue limitation", answer["answer"])
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
                (
                    "two 1979 primary studies",
                    "saline enemas",
                    "blood enemas",
                    "haemolymph transfer",
                    "R&D recommendation",
                ),
            ),
            (
                "Did the nanostructured citronella paper directly measure volatile release rate?",
                ("did not directly measure", "inferred prolonged release", "skin permeation"),
            ),
            (
                "Is humidity directly proven to be redundant with heat and odor during Aedes host seeking?",
                (
                    "close-range moisture",
                    "do not directly manipulate humidity or moisture",
                    "source gap",
                    "not established",
                ),
            ),
            (
                "How should our volatile Aedes repellent program report source loading and exposure?",
                (
                    "R&D reporting recommendation",
                    "not chemically determined",
                    "remaining on those papers",
                    "chamber-air concentration",
                    "retained source mass",
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

    def test_blood_meal_state_answer_cites_both_primary_1979_studies(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "aedes-blood-meal-internal-state"
        )
        expected_record_ids = {
            "aedes_primary_behavior:pubmed:544697",
            "aedes_primary_behavior:pubmed:469272",
            "aedes_primary_behavior:pmc:PMC3794971",
        }
        self.assertEqual(set(topic["source_record_ids"]), expected_record_ids)

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="aedes_primary_behavior_evidence",
                        locator=f"records#{record_id}",
                    )
                    for record_id in expected_record_ids
                ]
            )
            questions = (
                "What controls Aedes aegypti host seeking after a blood meal?",
                "What did the original experiments using saline and blood enemas "
                "show about the two stages of Aedes aegypti host-seeking "
                "suppression after a meal?",
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question in questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    expected_record_ids,
                )

    def test_blood_meal_state_answers_do_not_overclaim_mechanism(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topics = {topic["id"]: topic for topic in catalog["topics"]}
        blood_meal_answer = topics["aedes-blood-meal-internal-state"]["answer"]
        npylr1_answer = topics["aedes-npylr1-necessity"]["answer"]

        self.assertNotIn(
            "anterior distention was more effective",
            blood_meal_answer.casefold(),
        )
        self.assertIn("does not distinguish", npylr1_answer.casefold())
        self.assertIn("redundant signaling", npylr1_answer.casefold())
        self.assertIn("different unknown receptor", npylr1_answer.casefold())
        self.assertNotIn(
            "supports redundant signaling rather than",
            npylr1_answer.casefold(),
        )

    def test_failed_public_science_cases_are_complete_and_cite_direct_evidence(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topics = {topic["id"]: topic for topic in catalog["topics"]}
        cases = (
            (
                "How do adult density and host quality change spotted wing drosophila egg-laying behavior?",
                "swd-density-host-quality",
                (
                    "whole raspberries",
                    "declined as female density increased",
                    "intermediate densities",
                    "male density did not significantly change",
                    "nonlinear",
                ),
            ),
            (
                "How could age, mating status, hunger, or prior egg laying change an SWD repellent result?",
                "swd-physiological-state-confounds",
                (
                    "15 hours",
                    "starvation-induced locomotion",
                    "virgin",
                    "gravid",
                    "reproductive maturity",
                    "remaining egg load",
                ),
            ),
            (
                "Can prior odor or host experience change how Aedes aegypti responds to a repellent?",
                "aedes-olfactory-learning",
                (
                    "previous DEET exposure",
                    "three hours",
                    "electroantennogram",
                    "associative learning",
                    "does not establish long-term",
                ),
            ),
            (
                "How much can mosquito population, genotype, age, or insecticide-resistance background change a repellent result?",
                "aedes-population-and-state-variation",
                (
                    "5.0%",
                    "54.9%",
                    "0.00852%",
                    "does not quantify",
                    "do not assume",
                ),
            ),
            (
                "What can an arm-in-cage landing assay establish, and what can it not establish about actual bite prevention?",
                "aedes-arm-in-cage-meaning",
                (
                    "landing-only",
                    "does not establish fewer probes or blood meals",
                    "separately measured",
                    "contact",
                ),
            ),
            (
                "How do we distinguish physiological resistance to a mosquito repellent from ordinary behavioral avoidance or reduced sensitivity?",
                "aedes-physiological-repellent-resistance",
                (
                    "heritable behavioral insensitivity",
                    "does not by itself prove",
                    "altered physiological mechanism",
                    "nine generations",
                    "experimental cross",
                ),
            ),
            (
                "Which plant cues guide diamondback moth host finding and egg laying, and which evidence is direct for Plutella xylostella?",
                "dbm-direct-host-cue-gap",
                (
                    "iberin",
                    "sulforaphane",
                    "non-volatile",
                    "epicuticular wax",
                    "more eggs",
                    "larva-induced",
                    "Y-tube olfactory assay",
                    "did not measure landing or egg deposition",
                ),
            ),
        )
        required_record_ids = sorted(
            {
                record_id
                for _, topic_id, _ in cases
                for record_id in topics[topic_id]["source_record_ids"]
            }
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
                    for record_id in required_record_ids
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question, _, _ in cases
            ]

        for (question, topic_id, fragments), answer in zip(
            cases, answers, strict=True
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    set(topics[topic_id]["source_record_ids"]),
                )
                for fragment in fragments:
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_dbm_cross_species_answer_cites_direct_oviposition_evidence(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "dbm-cross-species-transfer-boundary"
        )
        oviposition_record_id = "dbm:openalex:W2114561940"
        self.assertIn(oviposition_record_id, topic["source_record_ids"])

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="plutella_xylostella_literature",
                        locator=f"raw/plutella/{record_id.rsplit(':', 1)[-1]}.json#jsonpath=$.work",
                    )
                    for record_id in topic["source_record_ids"]
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "What can SWD or mosquito spatial-repellency evidence legitimately "
                "suggest for diamondback moth, and what must be tested directly?",
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer["ok"])
        self.assertIn("oviposition", answer["answer"])
        self.assertIn(
            oviposition_record_id,
            {item["record_id"] for item in answer["evidence"]},
        )

    def test_dbm_host_cue_topic_matches_chemistry_and_surface_wording(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "dbm-direct-host-cue-gap"
        )
        questions = (
            "What evidence separates volatile isothiocyanate effects from "
            "leaf-surface wax effects on diamondback moth egg laying?",
            "How do phylloplane wax and isothiocyanates affect Plutella "
            "xylostella oviposition?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="plutella_xylostella_literature",
                        locator=f"records#{record_id}",
                    )
                    for record_id in topic["source_record_ids"]
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
                self.assertIn("iberin", answer["answer"].casefold())
                self.assertIn("epicuticular wax", answer["answer"].casefold())
                self.assertIn("y-tube olfactory assay", answer["answer"].casefold())
                self.assertIn(
                    "did not measure landing or egg deposition",
                    answer["answer"].casefold(),
                )
                self.assertNotIn(
                    "attracted adult females for oviposition",
                    answer["answer"].casefold(),
                )
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    set(topic["source_record_ids"]),
                )

    def test_dbm_gap_answer_acknowledges_direct_repellent_work_and_quantifies_exposure(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "dbm-first-baseline-experiment"
        )
        direct_repellent_records = {
            "dbm:openalex:W2141627881",
            "dbm:openalex:W4383535925",
            "dbm:openalex:W4393189143",
            "dbm:openalex:W4387738540",
        }
        self.assertTrue(direct_repellent_records.issubset(topic["source_record_ids"]))

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="plutella_xylostella_literature",
                        locator=f"records#{record_id}",
                    )
                    for record_id in topic["source_record_ids"]
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "Before screening diamondback moth repellents, what is the most "
                "important public-evidence gap to close and what experiment would close it?",
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer["ok"])
        for fragment in (
            "direct studies already report",
            "airborne concentration at the moth",
            "known DBM-active positive control",
            "do not label a volatile-treated surface contact-only",
            "marketable yield or quality",
            "release rate alone is not airborne concentration",
        ):
            self.assertIn(fragment.casefold(), answer["answer"].casefold())
        self.assertEqual(
            {item["record_id"] for item in answer["evidence"]},
            set(topic["source_record_ids"]),
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
                "A red-colored emitter and a transparent sham produced different SWD side choices. What repeat would isolate odor repellency from the hardware's visual cue?",
                "swd:openalex_literature:openalex:W3132534524",
                (
                    "color preferences",
                    "changed with the accompanying odor",
                    "visually match treatment and control",
                    "randomizing positions",
                    "not oviposition",
                ),
            ),
            (
                "Our coloured volatile cartridge is visible to spotted wing drosophila but the control is clear. How should we rerun the assay before calling it an olfactory effect?",
                "swd:openalex_literature:openalex:W3132534524",
                (
                    "color preferences",
                    "hide the source",
                    "randomizing positions",
                    "interacting modalities",
                ),
            ),
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
                (
                    "did not test genetic association",
                    "rear unexposed offspring",
                    "select lines across generations",
                    "cross-resistance",
                    "field phenotype frequencies",
                    "common-garden",
                ),
            ),
            (
                "How should I connect fewer SWD eggs with later larval survival and marketable yield across different fruit ripeness states?",
                "swd_pubmed_literature:pubmed:39769586",
                (
                    "overripe fruit",
                    "cultivar differences in pupation",
                    "Table 1 shows pupation rates of 0.80-0.87",
                    "abstract instead reports pupation up to 0.89",
                    "0.51-0.62",
                    "did not compare developmental outcomes across ripeness states",
                    "marketable yield",
                    "economic loss",
                    "operational fit",
                ),
            ),
            (
                "Which endpoints connect fewer SWD eggs on fruit to fewer surviving larvae and less marketable crop loss?",
                "swd_pubmed_literature:pubmed:39769586",
                (
                    "Table 1 shows pupation rates of 0.80-0.87",
                    "abstract instead reports pupation up to 0.89",
                    "0.51-0.62",
                    "fewer pupae",
                    "marketable yield",
                ),
            ),
            (
                "How redundant are carbon dioxide, human odor, heat, humidity, and visual cues during Aedes aegypti host seeking?",
                "openalex:W4401794442",
                (
                    "close-range moisture",
                    "convective body heat",
                    "less than 10 cm",
                    "thermal infrared",
                    "mid-range directional cue",
                    "source gap",
                ),
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
                "Why can transfluthrin reduce Aedes aegypti landings when a whole-antenna EAG shows no signal, and what evidence points to sodium channels?",
                "openalex:W3179105761",
                (
                    "20 ng/cm2",
                    "DEET, 1-octen-3-ol, and lactic acid",
                    "No locomotor abnormality",
                    "orco-null",
                    "S989P and V1016G",
                    "1S-cis",
                    "laboratory landing",
                    "did not measure airborne concentration",
                ),
            ),
            (
                "Does an absent antennal response to pure transfluthrin mean Aedes failed to sense it, or do Orco, kdr, and stereoisomer experiments support the observed repellency through another pathway?",
                "openalex:W3179105761",
                (
                    "does not exclude a response in individual antennal neurons",
                    "KDR:ROCK",
                    "sodium-channel-dependent principal mechanism",
                    "Three tested commercial transfluthrin products behaved differently",
                    "unknown background differences",
                ),
            ),
            (
                "Why does Aedes aegypti show transfluthrin-mediated landing suppression despite a null antennal field potential, and how do Orco deletion and kdr substitutions constrain the mechanism?",
                "openalex:W3179105761",
                (
                    "99.2-99.9% purity",
                    "another sensory organ",
                    "applied to the lower net",
                    "without requiring intact Orco-mediated odorant-receptor signaling",
                ),
            ),
            (
                "Aedes females still shun transfluthrin near a hand although their antennal field potential is silent. Which channel perturbations identify the responsible route?",
                "openalex:W3179105761",
                (
                    "mutant mosquito sodium channel was less sensitive",
                    "1S-cis isomer",
                    "complete detection-to-avoidance pathway",
                ),
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
                    "measure feeding or consumption directly",
                    "did not directly measure consumption",
                    "recovery",
                    "delayed mortality",
                    "R&D recommendation",
                ),
            ),
            (
                "A diamondback moth candidate reduces landings, but normal activity returns within 30 minutes. What study would separate temporary spatial avoidance, reversible knockdown, and delayed toxicity?",
                "dbm:openalex:W4387738540",
                (
                    "measure feeding or consumption directly",
                    "did not directly measure consumption",
                    "same moths",
                    "delayed mortality",
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
                (
                    "99%",
                    "64%",
                    "larvae and pupae",
                    "not from direct egg counts",
                    "component choice assays likewise counted recovered larvae and pupae",
                    "caprylic",
                    "capric",
                    "spatial",
                    "contact",
                ),
            ),
            (
                "We're deciding whether coconut free fatty acid should be developed as an airborne SWD repellent or as an oviposition deterrent on fruit. What do the existing egg-count results establish, and which experiment would resolve the mode of action?",
                "swd:openalex_literature:openalex:W4386466923",
                (
                    "reported CFFA as an oviposition deterrent",
                    "larvae and pupae",
                    "not from direct egg counts",
                    "later no-choice comparison counted eggs directly",
                    "no-contact",
                    "total egg output",
                ),
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
                "In an SWD wind-tunnel screen, how can we tell whether a volatile redirects flight rather than broadly suppressing movement, and which matched controls should the protocol include?",
                "swd:openalex_literature:openalex:W4213332511",
                (
                    "heading",
                    "upwind",
                    "clean air",
                    "match airflow, solvent, and release rate",
                    "blind tracking",
                    "do not establish that any candidate volatile is a repellent",
                ),
            ),
            (
                "How would you distinguish plume-guided SWD flight redirection from a volatile that suppresses movement throughout the tunnel?",
                "swd:openalex_literature:openalex:W4213332511",
                ("plume occupancy", "clean air", "locomotion", "randomize", "circadian"),
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
                (
                    "larval positions",
                    "later egg output",
                    "did not directly measure food consumption",
                    "mortality",
                    "Diadegma",
                ),
            ),
            (
                "What controls Aedes host seeking after a blood meal, and is there a proven universal 24-hour phase?",
                "aedes_primary_behavior:pubmed:544697",
                (
                    "two 1979 primary studies",
                    "saline enemas",
                    "blood enemas",
                    "three days",
                    "universal 24-hour phase",
                ),
            ),
            (
                "After an Aedes aegypti female feeds, is abdominal swelling the whole reason she stops seeking hosts for the next 24 hours?",
                "aedes_primary_behavior:pubmed:469272",
                (
                    "oocyte maturation",
                    "haemolymph transfer",
                    "three days",
                    "universal 24-hour phase",
                ),
            ),
            (
                "If an Aedes aegypti female's abdomen is experimentally distended without blood, would reduced host seeking prove that blood chemistry caused the suppression?",
                "aedes_primary_behavior:pubmed:544697",
                (
                    "saline enemas",
                    "blood enemas",
                    "does not establish one receptor",
                ),
            ),
            (
                "Is NPYLR1 required for post-blood-meal host-seeking suppression in Aedes aegypti?",
                "aedes_primary_behavior:pmc:PMC3794971",
                (
                    "null mutants",
                    "not required",
                    "does not distinguish",
                    "redundant signaling",
                    "different unknown receptor",
                ),
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

    def test_transfluthrin_mechanism_matcher_rejects_unrelated_aedes_sensory_questions(self):
        record_id = "openalex:W3179105761"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="aedes_literature_openalex",
                        locator="raw/aedes.json#works/W3179105761",
                    )
                ]
            )
            questions = (
                "Can Aedes aegypti smell human odor but avoid DEET?",
                "Does Aedes aegypti detect heat but avoid a visual target?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNone(answer)

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
