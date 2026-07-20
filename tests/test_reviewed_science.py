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
                "Could running SWD cage replicates at different clock times confound the apparent oviposition treatment effect?",
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
                "How would you distinguish a mosquito changing its flight direction from a "
                "mosquito that is simply moving more slowly after repellent exposure?",
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
                "For an Aedes spatial-repellency chamber, what airflow and temperature "
                "details should I record so another lab can reproduce the exposure?",
                "Which daytime window, microclimate measurements, and plume details "
                "should be reported for a reproducible Aedes non-contact chamber assay?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertEqual(answer["evidence"][0]["record_id"], record_id)
                    for fragment in (
                        "at the beginning of each 30-minute trial",
                        "09:00-16:30",
                        "does not publish the numeric assay-room",
                        "25 +/- 2 C",
                        "rearing conditions, not measured assay-room set points",
                        "2.8 mL",
                        "14.7 x 17.5 cm",
                        "solvent-and-carrier vehicle control",
                        "1.91:0.95",
                        "room temperature on aluminium foil",
                        "define and monitor airflow direction and speed",
                        "airborne-exposure measurement gap",
                        "applied loading alone as airborne dose",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

            unrelated = build_reviewed_science_answer(
                index,
                "How does regional humidity affect Aedes aegypti field abundance?",
            )
            if unrelated is not None:
                self.assertNotIn(
                    record_id,
                    {item["record_id"] for item in unrelated["evidence"]},
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
                    provenance_by_record = {
                        item["record_id"]: item["provenance"]
                        for item in answer["evidence"]
                    }
                    locators = [
                        item["locator"] for item in provenance_by_record.values()
                    ]
                    field_source = provenance_by_record[
                        "swd:openalex_literature:openalex:W4411730655"
                    ]
                    self.assertEqual(
                        field_source["source_id"],
                        "doi:10.1093/ee/nvaf057",
                    )
                    self.assertIn(
                        "field raspberry methods/results",
                        field_source["locator"],
                    )
                    self.assertTrue(
                        all(
                            not locator.startswith("/")
                            and "artifacts/" not in locator
                            for locator in locators
                        )
                    )

    def test_swd_pollinator_safety_paraphrases_use_direct_feeding_study(self):
        record_id = "swd:openalex_literature:openalex:W4397009635"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator="raw/swd.json#works/W4397009635",
                    )
                ]
            )
            questions = (
                "SWD was more sensitive than two bee species in an essential-oil feeding study. Is that enough to advance the oil as pollinator-safe in a berry-field repellent program?",
                "Does greater bee tolerance in an SWD feeding assay make the essential oil safe for pollinators in the field?",
                "Can we call an SWD oil bee-safe because honey bees and stingless bees tolerated it better than the flies?",
                "What pollinator risk evidence is still missing before advancing an SWD essential oil for use on berry crops?",
                "Do lower effects in two tested bees establish non-target safety for an SWD crop treatment?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertEqual(
                        [item["record_id"] for item in answer["evidence"]],
                        [record_id],
                    )
                    for fragment in (
                        "No.",
                        "Pectis brevipedunculata",
                        "feeding toxicity and diet-consumption",
                        "still killed more bees than the control",
                        "laboratory hazard, expected field exposure, and field risk",
                        "does not establish pollinator safety",
                        "remain evidence needs",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_swd_pollinator_safety_matcher_rejects_unrelated_questions(self):
        record_id = "swd:openalex_literature:openalex:W4397009635"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator="raw/swd.json#works/W4397009635",
                    )
                ]
            )
            questions = (
                "Is this SWD essential oil an effective oviposition repellent?",
                "Are Aedes aegypti skin repellents safe for people?",
                "Which beneficial insects attack diamondback moth larvae?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    if answer is not None:
                        self.assertNotIn(
                            record_id,
                            {item["record_id"] for item in answer["evidence"]},
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
        self.assertIn("at the beginning of each 30-minute trial", answer["answer"])
        self.assertIn("09:00-16:30", answer["answer"])
        self.assertIn("does not publish the numeric assay-room", answer["answer"])
        self.assertIn("rearing conditions, not measured assay-room set points", answer["answer"])
        self.assertIn("2.8 mL", answer["answer"])
        self.assertIn("14.7 x 17.5 cm", answer["answer"])
        self.assertIn("solvent-and-carrier vehicle control", answer["answer"])
        self.assertIn("1.91:0.95", answer["answer"])
        self.assertIn("room temperature on aluminium foil", answer["answer"])
        self.assertIn("remaining on those papers", answer["answer"])
        self.assertIn("chamber-air concentration", answer["answer"])
        self.assertIn("not the paper's named treated-paper residue limitation", answer["answer"])
        self.assertIn("R&D design recommendations", answer["answer"])
        self.assertIn("applied loading alone as airborne dose", answer["answer"])
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

    def test_aedes_resistance_answer_includes_distinct_thymol_selection_evidence(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "aedes-physiological-repellent-resistance"
        )
        expected_record_ids = {
            "aedes_primary_behavior:plosntds:e0003726",
            "openalex:W4299723530",
            "openalex:W4413344516",
        }
        self.assertEqual(set(topic["source_record_ids"]), expected_record_ids)

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="generic_literature_lane",
                        locator=f"records#{record_id}",
                    )
                    for record_id in expected_record_ids
                ]
            )
            answer = build_reviewed_science_answer(
                index,
                "How should I distinguish inherited Aedes repellent resistance from "
                "ordinary avoidance, and what do the transfluthrin, thymol-selection, "
                "and pyrethroid-clothing studies each establish?",
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer["ok"])
        self.assertIn("thymol", answer["answer"].casefold())
        self.assertIn("life-history", answer["answer"].casefold())
        self.assertIn("does not measure repellent response", answer["answer"].casefold())
        self.assertEqual(
            {item["record_id"] for item in answer["evidence"]},
            expected_record_ids,
        )
        self.assertIn(
            "doi:10.1371/journal.pone.0329776",
            {item["provenance"]["source_id"] for item in answer["evidence"]},
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
                    "affected oviposition more than adult density",
                    "unfamiliar or unnatural substrates",
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
                    "versus clean air",
                    "no preference",
                    "three Brassicaceae",
                    "mixed cropping",
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

    def test_swd_density_topic_handles_count_and_per_fly_wording(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "swd-density-host-quality"
        )
        questions = (
            "If one cage has twice as many SWD females and eggs per fly drops, "
            "is that evidence the treatment deterred egg laying?",
            "We changed the number of female spotted wing drosophila per arena; "
            "how should total eggs, eggs per female, and fruit coverage be interpreted?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        topic["source_record_ids"][0],
                        source_id="public_literature",
                        locator=f'records#{topic["source_record_ids"][0]}',
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
                    set(topic["source_record_ids"]),
                )
                self.assertIn("about 15%", answer["answer"])
                self.assertIn("about 72%", answer["answer"])
                self.assertIn("match female and male density", answer["answer"])
                self.assertIn("does not establish oviposition deterrence", answer["answer"])

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
            "across the eight cited primary studies",
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

    def test_catalog_rejects_malformed_excluded_terms(self):
        payload = catalog_payload()
        payload["topics"][0]["match"]["excluded_any"] = "anopheles"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)

            with self.assertRaisesRegex(ReviewedScienceError, "excluded_any"):
                load_reviewed_science_catalog(path)

    def test_catalog_rejects_malformed_question_intent(self):
        payload = catalog_payload()
        payload["topics"][0]["match"]["question_intent"] = ["sampling_design"]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)

            with self.assertRaisesRegex(ReviewedScienceError, "question_intent"):
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

    def test_catalog_rejects_source_provenance_for_an_unlisted_record(self):
        payload = catalog_payload()
        payload["topics"][0]["source_provenance"] = [
            {
                "record_id": "study:not-listed",
                "title": "Primary study",
                "public_url": "https://doi.org/10.1000/example",
                "source_id": "doi:10.1000/example",
                "locator": "Methods 2",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedScienceError,
                "unknown source records",
            ):
                load_reviewed_science_catalog(path)

    def test_catalog_rejects_non_public_source_provenance_url(self):
        payload = catalog_payload()
        payload["topics"][0]["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Primary study",
                "public_url": "raw/paper.pdf",
                "source_id": "doi:10.1000/example",
                "locator": "Methods 2",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedScienceError,
                "public HTTP",
            ):
                load_reviewed_science_catalog(path)

    def test_catalog_source_provenance_overrides_generic_index_metadata(self):
        payload = catalog_payload()
        payload["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Exact primary study",
                "public_url": "https://doi.org/10.1000/example",
                "source_id": "doi:10.1000/example",
                "locator": "Results: harder oviposition substrate comparison",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        "study:texture",
                        source_id="generic_literature_lane",
                        locator="artifacts/generic.json#records/0",
                    )
                ]
            )

            answer = build_reviewed_science_answer(
                index,
                "How does SWD fruit texture affect egg laying?",
                catalog_path=self.write_catalog(root, payload),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        evidence = answer["evidence"][0]
        self.assertEqual(evidence["title"], "Exact primary study")
        self.assertEqual(evidence["url"], "https://doi.org/10.1000/example")
        self.assertEqual(evidence["provenance"]["source_id"], "doi:10.1000/example")
        self.assertEqual(
            evidence["provenance"]["locator"],
            "Results: harder oviposition substrate comparison",
        )

    def test_catalog_rejects_missing_exact_source_provenance_when_required(self):
        payload = catalog_payload()
        payload["require_exact_source_provenance"] = True
        payload["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Exact primary study",
                "public_url": "https://doi.org/10.1000/example",
                "source_id": "doi:10.1000/example",
                "locator": "Results: harder oviposition substrate comparison",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedScienceError,
                "missing exact source provenance.*study:new-insect",
            ):
                load_reviewed_science_catalog(path)

    def test_catalog_rejects_generic_source_id_when_exact_provenance_is_required(self):
        payload = catalog_payload()
        payload["topics"] = [payload["topics"][0]]
        payload["require_exact_source_provenance"] = True
        payload["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Primary study",
                "public_url": "https://doi.org/10.1000/example",
                "source_id": "generic_literature_lane",
                "locator": "Results: harder oviposition substrate comparison",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedScienceError,
                "exact public source_id",
            ):
                load_reviewed_science_catalog(path)

    def test_catalog_rejects_index_locator_when_exact_provenance_is_required(self):
        payload = catalog_payload()
        payload["topics"] = [payload["topics"][0]]
        payload["require_exact_source_provenance"] = True
        payload["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Primary study",
                "public_url": "https://doi.org/10.1000/example",
                "source_id": "doi:10.1000/example",
                "locator": "artifacts/literature.json#works/W123",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedScienceError,
                "claim-level locator",
            ):
                load_reviewed_science_catalog(path)

    def test_topic_source_provenance_overrides_catalog_entry(self):
        payload = catalog_payload()
        payload["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Catalog primary study",
                "public_url": "https://doi.org/10.1000/catalog",
                "source_id": "doi:10.1000/catalog",
                "locator": "Abstract",
            }
        ]
        payload["topics"][0]["source_provenance"] = [
            {
                "record_id": "study:texture",
                "title": "Topic-specific primary study",
                "public_url": "https://doi.org/10.1000/topic",
                "source_id": "doi:10.1000/topic",
                "locator": "Results: exact claim",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            index = SourceIndex(root / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        "study:texture",
                        source_id="generic_literature_lane",
                        locator="artifacts/generic.json#records/0",
                    )
                ]
            )

            answer = build_reviewed_science_answer(
                index,
                "How does SWD fruit texture affect egg laying?",
                catalog_path=self.write_catalog(root, payload),
            )

        self.assertIsNotNone(answer)
        assert answer is not None
        evidence = answer["evidence"][0]
        self.assertEqual(evidence["title"], "Topic-specific primary study")
        self.assertEqual(evidence["provenance"]["source_id"], "doi:10.1000/topic")
        self.assertEqual(evidence["provenance"]["locator"], "Results: exact claim")

    def test_repository_catalog_requires_complete_exact_source_provenance(self):
        payload = load_reviewed_science_catalog(default_reviewed_science_catalog())

        self.assertIs(payload["require_exact_source_provenance"], True)

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
                "Three commercial transfluthrin repellents were stronger than a high-purity preparation but lost part of that effect in Orco-null Aedes. Does that show transfluthrin itself has two receptor mechanisms, or what can we conclude about the products' unidentified additional compounds?",
                "openalex:W3179105761",
                (
                    "does not show that transfluthrin itself has two receptor mechanisms",
                    "unidentified additional compounds",
                    "Orco-dependent component",
                    "cannot be assigned",
                ),
            ),
            (
                "Commercial transfluthrin formulations show an Orco-linked component that the pure active does not. Can the extra compounds be assigned that mechanism?",
                "openalex:W3179105761",
                (
                    "Aedes aegypti",
                    "does not show that transfluthrin itself has two receptor mechanisms",
                    "unidentified additional compounds",
                    "cannot be assigned",
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
                "Is the caprylic-plus-capric mixture ready to advance as a simpler CFFA formulation for SWD, or do we need a broader component comparison?",
                "swd:openalex_literature:openalex:W4386466923",
                (
                    "bounded formulation hypothesis",
                    "1.38 mg caprylic acid plus 1.46 mg capric acid",
                    "not significantly different",
                    "not field tests of the two-component blend",
                    "component and blend dose-response",
                ),
            ),
            (
                "In the CFFA work, some trials counted eggs and others recovered larvae and pupae. Which result measures oviposition directly, and why can the offspring counts not identify airborne avoidance?",
                "swd:openalex_literature:openalex:W4386466923",
                (
                    "later no-choice comparison counted eggs directly",
                    "20 females",
                    "larvae and pupae",
                    "cannot",
                    "airborne spatial avoidance",
                ),
            ),
            (
                "For CFFA, why should recovered offspring and direct egg counts be treated as different endpoints when deciding whether the effect is spatial?",
                "swd:openalex_literature:openalex:W4386466923",
                (
                    "counted eggs directly",
                    "recovered larvae and pupae",
                    "no-contact",
                    "surface-contact",
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
                (
                    "20%",
                    "42-55%",
                    "dawn and dusk",
                    "low fly",
                    "does not isolate total emitted dose",
                ),
            ),
            (
                "In raspberry plots, did the advantage of timed octenol puffers over passive vials prove that a larger total dose caused the result?",
                "swd:openalex_literature:openalex:W3046652911",
                (
                    "20%",
                    "42-55%",
                    "tested delivery methods differed in outcome",
                    "does not isolate total emitted dose",
                    "airborne concentration at the flies",
                    "low fly abundance",
                ),
            ),
            (
                "Timed 1-octen-3-ol aerosol puffers outperformed passive vials in raspberry plots. Does that isolate total dose as the driver, or only show a delivery-method difference under those field conditions?",
                "swd:openalex_literature:openalex:W3046652911",
                (
                    "20%",
                    "42-55%",
                    "dawn and dusk",
                    "low fly abundance",
                    "tested delivery methods differed in outcome",
                    "does not isolate total emitted dose",
                ),
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
                (
                    "lower protein",
                    "1:8 protein-to-carbohydrate diet",
                    "did not differ significantly in their nutritional preference",
                    "D. biarmipes preferred the softest tested substrate",
                    "D. suzukii showed no significant hardness preference",
                ),
            ),
            (
                "Why did transfluthrin look better in large-cage Aedes trials than in open-field landing collections?",
                "openalex:W4399119561",
                ("negligible", "50-60%", "moderate pyrethroid resistance", "15 g"),
            ),
            (
                "Should the large-cage hessian emanator result or the disappointing open-field result control our outdoor product decision, and how should we diagnose the gap?",
                "openalex:W4399119561",
                (
                    "Use the open-field result",
                    "context-dependent biological effect",
                    "not be averaged",
                    "human landing and biting separately",
                    "airborne transfluthrin concentration",
                ),
            ),
            (
                "Can we transfer an Anopheles DEET response to Aedes, or are close-range repellent responses species-specific?",
                "openalex:W3013059076",
                (
                    "significant repellency to lemongrass oil, PMD, eugenol, and DEET",
                    "DEET was not significantly repellent",
                    "weak response",
                    "P=0.08",
                    "not the same as zero movement",
                    "0.5 cm",
                    "30-second",
                ),
            ),
            (
                "Did every Anopheles coluzzii female remain still near DEET in the 30-second odor assay, or was the result only statistically non-significant?",
                "openalex:W3013059076",
                (
                    "DEET was not significantly repellent",
                    "not the same as zero movement",
                    "one resting female",
                    "30-second",
                ),
            ),
            (
                "Was the Anopheles DEET result in the close-proximity assay zero response, or a non-significant repellency comparison?",
                "openalex:W3013059076",
                (
                    "DEET was not significantly repellent",
                    "not the same as zero movement",
                    "0.5 cm",
                ),
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

    def test_decision_route_matchers_reject_neighboring_questions(self):
        record_ids = (
            "swd:openalex_literature:openalex:W4386466923",
            "openalex:W4399119561",
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
            questions = (
                "Should we advance caprylic acid as a mosquito skin formulation?",
                "Why did a large-cage moth trial disagree with a field trial?",
                "How should an Aedes emanator be tested in a laboratory cage?",
                "Why did a hessian emanator work in a large-cage Anopheles gambiae test but disappoint in an open-field trial?",
                "Should a semi-field Culex hessian emanator result control an outdoor field decision?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNone(answer)

    def test_swd_field_delivery_matcher_rejects_other_species_and_generic_delivery(self):
        record_id = "swd:openalex_literature:openalex:W3046652911"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator="raw/swd.json#works/W3046652911",
                    )
                ]
            )
            questions = (
                "Did Aedes aegypti aerosol puffers outperform passive vials in a field trial?",
                "Does an automated greenhouse dispenser release more total dose than a passive vial?",
                "Do octenol mosquito-trap puffers change dengue vector competence?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    if answer is not None:
                        self.assertNotIn(
                            record_id,
                            {item["record_id"] for item in answer["evidence"]},
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

    def test_swd_exclusion_net_questions_use_the_reviewed_operating_envelope(self):
        record_id = "swd:openalex_literature:openalex:W4408117270"
        record = EvidenceRecord(
            record_id=record_id,
            lane="literature",
            source="drosophila_suzukii_core",
            title=(
                "The Efficacy of Protective Nets Against Drosophila suzukii: "
                "The Effect of Temperature, Airflow, and Pest Morphology"
            ),
            text="Primary study metadata and abstract.",
            species="Drosophila suzukii",
            url="10.3390/insects16030253",
            media_url=None,
            provenance=Provenance(
                source_id="drosophila_suzukii_core",
                locator=(
                    "raw/drosophila_suzukii/literature/page_002.json"
                    "#works/W4408117270"
                ),
                retrieved_at=RETRIEVED_AT,
                license="OpenAlex metadata",
            ),
        )
        questions = (
            "Can an SWD exclusion net qualified in still air be used in a fan-ventilated berry tunnel?",
            "What hot-weather and airflow envelope should we challenge before deploying mesh against spotted wing drosophila?",
            "Our Drosophila suzukii screen worked with cool-reared flies; what must change before a windy field test?",
            "Which airflow and heat conditions should I vary before treating an SWD exclusion screen as reliable outside a laboratory passage assay?",
            "Can one lower-canopy sample across the cherry season prove that exclusion mesh works under low airflow for SWD?",
            "We sampled cherries below the screen, but is the SWD barrier reliable under hotter and windier field conditions?",
            "Before field deployment, should D. suzukii exclusion mesh be challenged under fan ventilation and heat?",
            "Is SWD exclusion fabric proven for a heated polytunnel with strong ventilation, or must we qualify that operating range?",
            "Our SWD mesh passed a bench assay. What environmental qualification and crop-performance matrix is needed before recommending it to berry growers?",
            "Our berry farm has a mesh that passed a bench assay. Which environmental qualification matrix should precede a grower recommendation?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([record])
            answers = [
                build_reviewed_science_answer(index, question)
                for question in questions
            ]

        for answer in answers:
            self.assertIsNotNone(answer)
            assert answer is not None
            self.assertTrue(answer["ok"])
            self.assertEqual(answer["answer_shape"], "reviewed_science")
            self.assertIn("Do not qualify", answer["answer"])
            self.assertIn("not experimentally controlled", answer["answer"])
            self.assertIn("were associated with lower efficacy", answer["answer"])
            self.assertIn("did not establish a controlled temperature effect", answer["answer"])
            self.assertIn(
                "a monotonic difference between 1.5 and 3.0 m/s",
                answer["answer"],
            )
            self.assertEqual(
                [item["record_id"] for item in answer["evidence"]],
                [record_id],
            )
            evidence = answer["evidence"][0]
            self.assertEqual(
                evidence["url"],
                "https://doi.org/10.3390/insects16030253",
            )
            self.assertEqual(
                evidence["provenance"]["source_id"],
                "doi:10.3390/insects16030253",
            )
            self.assertEqual(
                evidence["provenance"]["locator"],
                "Methods 2.1-2.2; Results 3.1 and 3.3; "
                "Tables 1-3 and 6-8; Conclusion 5",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([record])
            unrelated = build_reviewed_science_answer(
                index,
                "Should I use an exclusion net to keep birds out of blueberries?",
            )
            nearby = build_reviewed_science_answer(
                index,
                "Which mesh color is easiest to see when counting SWD in a laboratory cage?",
            )
            implicit_species_neighbor = build_reviewed_science_answer(
                index,
                "Our greenhouse mesh passed a bench assay. Which environmental qualification matrix should precede deployment?",
            )

        self.assertIsNone(unrelated)
        self.assertIsNone(nearby)
        self.assertIsNone(implicit_species_neighbor)

    def test_swd_seasonal_canopy_questions_use_the_reviewed_sampling_design(self):
        record_id = "swd:openalex_literature:openalex:W3036207020"
        record = EvidenceRecord(
            record_id=record_id,
            lane="literature",
            source="drosophila_suzukii_core",
            title=(
                "Spatial distribution of spotted-wing drosophila (Diptera: "
                "Drosophilidae) and other insects in fruit of a sweet cherry "
                "(Rosaceae) orchard"
            ),
            text="Primary study title and abstract.",
            species="Drosophila suzukii",
            url="10.4039/tce.2020.41",
            media_url=None,
            provenance=Provenance(
                source_id="drosophila_suzukii_core",
                locator="raw/drosophila_suzukii/literature/page_005.json#works/W3036207020",
                retrieved_at=RETRIEVED_AT,
                license="OpenAlex metadata",
            ),
        )
        questions = (
            "Can one SWD canopy position represent infestation through the whole cherry season?",
            "How should we stratify SWD fruit samples by orchard row, height, and aspect as cultivars ripen?",
            "Can one fixed lower-south canopy sample be our season-long SWD infestation readout in sweet cherry, or did the orchard study show that the spatial pattern changes with population density and ripening stage?",
            "How should we stratify SWD fruit samples by canopy height and aspect through the cherry season during a repellent trial?",
            "Where should we sample SWD-infested fruit across orchard rows as cultivars ripen during a spray trial?",
            "Can a lower-canopy sweet-cherry fruit sample represent seasonal SWD infestation when adult trap counts are recorded separately?",
            "How should we measure SWD fruit infestation by canopy position through the season inside a netted orchard?",
            "How should we collect SWD-infested cherries from upper and lower canopy positions as cultivars ripen?",
            "Where should we collect SWD-infested cherries across north and south canopy positions through the season?",
            "Design a representative season-long SWD fruit-collection plan across orchard rows, canopy heights, and cultivars.",
            "How should we sample SWD fruit by canopy position through the season in a hot, fan-ventilated tunnel with an exclusion net?",
            "Can cherries picked only from the lower south canopy represent SWD infestation as successive cultivars ripen?",
            "Is an SWD estimate from upper-canopy cherries alone defensible across early and late ripening cultivars?",
            "We pick fruit from one southern branch each week; does that represent whole-orchard SWD infestation over time?",
            "Should SWD fruit collection rotate among border and interior rows as different cherry cultivars ripen?",
            "Could a pooled sample from the bottom canopy hide seasonal changes in SWD aggregation?",
            "To estimate season-long SWD infestation, must fruit collection cover both canopy heights and both aspects?",
            "At each ripening stage, where would we collect cherries to estimate SWD infestation across the orchard?",
            "Can a fixed upper-north fruit collection estimate SWD infestation before and after population growth?",
            "Does a south-row sample represent seasonal SWD infestation separately from adult trap counts in a treatment arm?",
            "Where should fruit be sampled across orchard rows during an SWD pesticide assay as cultivars ripen?",
            "We are testing an odor treatment; can upper-canopy fruit alone estimate SWD infestation over the cherry season?",
            "For treatment and control blocks, is one lower-north sample representative of SWD infestation as cherries ripen?",
            "During a spray experiment, would one bottom-row sample give a representative SWD readout across successive cultivars?",
            "We've only been taking cherries from one low southern limb; can that stand in for the orchard's SWD burden from first to last cultivar?",
            "Would fruit gathered at the north edge give a fair seasonwide estimate of spotted wing drosophila as varieties mature?",
            "Build us a fruit-sampling scheme that follows SWD across border and center rows from early through late cherry cultivars.",
            "Are cherries from a single upper branch enough to describe SWD infestation while the orchard moves through ripening?",
            "The crew pools fruit from every southern bottom branch; could that hide shifts in SWD as cultivars mature?",
            "How many orchard locations should each weekly fruit pull cover to track SWD through ripening?",
            "Could a north-edge picking routine misrepresent SWD across the rest of the canopy later in the season?",
            "Do repeated collections from one bottom branch capture the change from sparse to aggregated SWD over time?",
            "In treated and untreated cherry blocks, how should fruit samples span rows and canopy heights as SWD density changes?",
            "During a repellent efficacy study, can one upper-row cherry sample represent SWD infestation through all ripening dates?",
            "While testing a repellent, how should fruit collection cover upper and lower canopy zones as SWD abundance rises?",
            "The assay compares spray and untreated plots; must SWD cherries be sampled across north and south aspects over time?",
            "Within mesh enclosures, should cherry collection rotate among rows as seasonal SWD density changes?",
            "Under exclusion fabric, can one north-canopy fruit sample represent SWD infestation across cultivars?",
            "The orchard is netted, but our question is whether bottom-row cherries represent SWD infestation over time; should we stratify?",
            "Could pooling cherries from the lowest south-facing branches conceal a shift from sparse to clustered SWD later in the season?",
            "How broadly should each weekly cherry collection cover the orchard to estimate SWD through successive ripening stages?",
            "Would a north-border picking routine understate SWD in central lower canopy once populations build?",
            "Can fruit repeatedly gathered from one bottom limb capture the seasonal transition to aggregated D. suzukii?",
            "In an insecticide experiment, is one upper-canopy fruit pull a defensible SWD infestation endpoint across all harvest dates?",
            "During an odor-treatment assay, how should fruit collection be stratified through ripening to measure SWD infestation without confusing placement with efficacy?",
            "In pesticide assay blocks, what seasonal sampling scheme should estimate SWD from early through late cherry cultivars?",
            "Can SWD infestation estimated from the top of a single center-row tree stand for all canopy aspects as population density increases?",
            "What stratified cherry-sampling scheme would best estimate D. suzukii infestation across rows, heights, aspects, and maturity stages?",
            "How should cherry fruit collection be spread spatially and temporally to track spotted wing drosophila through harvest?",
            "Must an SWD monitoring plan collect infested fruit from multiple aspects rather than the same branch all summer?",
            "What orchard sampling layout would let us compare SWD fruit infestation reliably between early and late ripening stages?",
            "Across the first and final cherry harvests, can one low east-facing branch represent SWD infestation throughout the orchard?",
            "Would repeatedly gathering cherries only from border trees give a representative D. suzukii estimate as the season advances?",
            "Is a fixed high-canopy picking point a fair estimator of SWD infestation from early through late cherry maturity?",
            "Should a seasonal D. suzukii readout rotate among border rows, center rows, top branches, and bottom branches?",
            "Can one northern orchard location stand for SWD fruit infestation before and after abundance increases?",
            "Could compositing cherries from orchard margins obscure a later shift in Drosophila suzukii toward central low branches?",
            "How should the team spread cherry collections across space and harvest time to measure changes in spotted wing drosophila clustering?",
            "Would sampling only fruit nearest the ground bias an SWD estimate when late cultivars and higher fly densities arrive?",
            "How many canopy strata and orchard zones should a cherry sample include to follow D. suzukii from sparse to aggregated populations?",
            "Should fruit-level SWD measurements be rotated across compass aspects, heights, rows, and maturity dates?",
            "Design a repeated cherry collection that can compare SWD infestation across orchard position and phenology without treating one branch as universal.",
            "When SWD numbers rise, can cherries gathered from one upper edge still stand for fruit infestation in lower central trees?",
            "Would pooling all D. suzukii fruit observations from one canopy quarter conceal density-dependent spatial aggregation across ripening stages?",
            "Does repeatedly measuring spotted-wing drosophila in cherry fruit from the orchard centre at mid-canopy give a defensible trajectory as fruit matures, or do we need wider spatial replication?",
            "If we assay 30 cherries per tree for spotted wing drosophila each week, can all fruit come from the north-facing lower crown, especially once abundance climbs in late cultivars?",
            "When measuring spotted wing drosophila incidence in individual cherries, should we balance fruit among compass aspects and orchard row positions at every cultivar's harvest date?",
            "How should cherries per tree be allocated across canopy layers and row neighborhoods when D. suzukii abundance is low in early picks but surges before the final cultivar?",
            "For D. suzukii, how should cherry fruit inspection be divided between north-facing interior branches and south-facing margin branches during weekly preharvest rounds?",
            "What spatial and temporal replication should a sweet-cherry fruit collection use to compare SWD infestation among early, midseason, and late cultivars without pseudoreplicating one canopy sector?",
            "For D. suzukii, should cherry subsamples come from upper crown and trunk-adjacent lower crown positions at both the first and final harvests?",
            "Write the sampling logic for fruit-level spotted-wing drosophila measurement over cherry phenological stages and orchard strata, including how often each canopy aspect is revisited.",
            "In a commercial sweet-cherry orchard, how should we quantify SWD fruit infestation among perimeter trees, row interiors, and central crowns from first color through final harvest?",
            "What allocation of inspected sweet cherries among boundary and interior trees would track Drosophila suzukii infestation over the seven-week ripening sequence?",
            "Should our SWD fruit census in sweet cherry split each cultivar's harvest among treetop, mid-crown, and near-ground positions across orchard rows?",
            "How many Drosophila suzukii-infested cherries should be drawn from north-facing versus south-facing branches in every cultivar and harvest week?",
            "How should fruit-level spotted wing drosophila observations be partitioned among orchard margins, center rows, canopy tiers, and ripeness classes?",
            "For SWD in a sweet-cherry block, how should individual-fruit inspections cover edge, middle, and interior rows as population pressure builds toward late harvest?",
            "At successive sweet-cherry picks, where should we inspect fruit for spotted wing drosophila so row position and vertical canopy strata are represented?",
            "What representative fruit collection would compare SWD infestation at the orchard boundary and core when abundance shifts between early and late sweet-cherry varieties?",
            "Can one stratum of the sweet-cherry canopy be used to estimate spotted wing drosophila infestation across the full picking calendar, or must rows and aspects be rotated?",
            "During sweet-cherry ripening, how should D. suzukii fruit examinations be distributed across row ends, mid-row trees, lower shade, and upper sun?",
            "Are fortnightly spotted wing drosophila infestation checks on cherries from one southern low branch adequate for a sweet-cherry orchard as fruit moves from blush to ripe?",
            "Could repeatedly inspecting D. suzukii infestation in fruit from the same east-side sweet-cherry trees distort the trend from low-density onset to peak abundance?",
            "At each sweet-cherry harvest, should spotted-wing drosophila cherries be selected randomly within every row-by-height-by-aspect cell or composited by orchard zone?",
            "Can SWD infestation measured from the lower half of center-row sweet-cherry trees generalize to border treetops after late cultivars come into bearing?",
            "To estimate D. suzukii infestation in a sweet-cherry planting, what sampling frame should cross canopy thirds and compass quadrants as early and late cultivars mature?",
            "We score sweet-cherry fruit for D. suzukii infestation after incubation; which canopy neighborhoods should enter the survey at first blush, full color, and harvest?",
            "At changing SWD densities, what sweet-cherry inspection layout prevents one row orientation or canopy tier from determining the entire infestation estimate?",
            "What orchard-by-canopy allocation of sweet-cherry samples would let us track Drosophila suzukii from initial detection to maximum fruit infestation?",
            "How can a sweet-cherry monitoring routine cover D. suzukii variation among rows and branch exposures while fruit maturity advances?",
            "To avoid pseudoreplication, where should we draw sweet-cherry fruit for Drosophila suzukii assays across orchard blocks and phenological stages?",
            "When SWD density climbs across the sweet-cherry season, should fruit infestation tallies be replicated along orchard transects and vertical crown thirds?",
            "SWD, sweet cherry: inspect fruit by canopy depth and row terminus at every cultivar pick, or composite the whole season?",
            "For Drosophila suzukii, can sweet-cherry subsampling stay confined to proximal branches while infestation pressure shifts between preharvest rounds?",
            "How should Drosophila suzukii-positive sweet cherries be enumerated across orchard transects, canopy depths, and serial harvests?",
            "For weekly SWD incidence estimates in sweet cherry, apportion inspected fruit among row termini, mid-row trees, and crown interiors as density changes?",
            "What multistage allocation should be used for SWD-infested sweet cherries across orchard quadrants and fruit-development stages?",
            "For Drosophila suzukii in sweet cherry, devise a repeated-measures fruit inspection across paired row orientations and canopy shells over the cultivar succession.",
            "Drosophila suzukii in sweet cherry: map fruit-infestation observations by row azimuth and canopy depth through the harvest progression.",
            "Sweet-cherry Drosophila suzukii surveillance: allocate individual-fruit examinations among canopy faces and orchard zones whenever harvest density shifts.",
            "Drosophila suzukii sweet-cherry sampling protocol: divide cherries among outer, mid-canopy, and trunk-side positions whenever maturity stages change.",
            "Does collecting sweet-cherry fruit for SWD from only inner lower branches misrepresent infestation after population pressure builds later in the season?",
            "How should individual sweet-cherry fruit be assayed for SWD across lower shade, upper sun, perimeter trees, and the final cultivar's ripening period?",
            "For D. suzukii, should cherries be subsampled from orchard corners and middle-row crowns on every cultivar harvest?",
            "SWD sweet-cherry infestation: stratify fruit picks by orchard quadrant and inner-versus-outer canopy at each cultivar's preharvest and harvest survey.",
            "Drosophila suzukii, sweet-cherry fruit infestation: replicate picks across row termini, central trees, canopy thirds, and successive ripening cohorts.",
            "When sweet-cherry fruit colour advances, should Drosophila suzukii samples be drawn from each canopy aspect and from both peripheral and interior rows?",
            "Specify a sweet-cherry fruit-infestation survey for Drosophila suzukii that revisits upper, middle, and lower canopy shells in border and central rows before each harvest.",
            "To estimate seasonal Drosophila suzukii fruit infestation in sweet cherry, collect replicate cherries along edge-to-core transects and from sunlit and shaded crown tiers.",
            "Drosophila suzukii sweet-cherry protocol: survey fruit infestation in alternating row azimuths and canopy depths on successive harvest rounds.",
            "Please balance sweet-cherry fruit collected for SWD infestation among windward borders, leeward interiors, crown levels, and the first, middle, and final commercial picks.",
            "Build a seasonwide sweet-cherry fruit pull for Drosophila suzukii infestation that crosses compass sides, canopy heights, and orchard blocks.",
            "Before and after SWD abundance peaks, select sweet-cherry fruit for infestation assays from row borders, row interiors, and multiple canopy faces.",
            "Would fortnightly Drosophila suzukii fruit-infestation surveys from fixed southeast lower branches capture the seasonal shift across sweet-cherry varieties?",
            "Draft a sweet-cherry SWD fruit-infestation protocol that repeatedly collects from windward and leeward rows, inner and outer crowns, and successive harvest stages.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([record])
            answers = [
                build_reviewed_science_answer(index, question)
                for question in questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                self.assertIn("Do not use one fixed lower-south", answer["answer"])
                self.assertIn("five successively ripening cultivars over seven weeks", answer["answer"])
                self.assertIn("keep fruit-emergence infestation separate", answer["answer"])
                self.assertIn("R&D inference", answer["answer"])
                self.assertIn("not a design validated by the paper", answer["answer"])
                evidence = answer["evidence"][0]
                self.assertEqual(evidence["record_id"], record_id)
                self.assertEqual(evidence["url"], "https://doi.org/10.4039/tce.2020.41")
                self.assertEqual(
                    evidence["provenance"]["source_id"],
                    "doi:10.4039/tce.2020.41",
                )
                self.assertIn(
                    "low-, later-, and high-density distribution",
                    evidence["provenance"]["locator"],
                )

        unrelated_questions = (
            "Should SWD netting cover the lower canopy throughout the cherry season?",
            "Where should we spray for SWD in the orchard canopy as cherries ripen?",
            "Should an SWD repellent be placed in the lower-south canopy for the entire season?",
            "Is the lower canopy the best place for an SWD trap throughout the cherry season?",
            "Does SWD spatial distribution prove where to spray in a ripening cherry orchard?",
            "Does seasonal SWD spatial distribution tell us whether we should spray the lower canopy?",
            "Should the SWD repellent go in the lower canopy as cherries ripen?",
            "Can orchard monitoring decide trap locations for SWD through the cherry season?",
            "Does SWD distribution show where netting goes as each cultivar ripens?",
            "Does one lower-canopy SWD fruit sample show where insecticide should be applied through the cherry season?",
            "Can seasonal SWD fruit sampling tell us where pesticide belongs in the upper orchard canopy?",
            "Does a lower-south sample decide chemical treatment placement as cherry cultivars ripen?",
            "Can one canopy sample show where an odor dispenser should go for SWD through the season?",
            "Does orchard sampling determine the best canopy position for a volatile emitter during cherry ripening?",
            "Can SWD fruit samples tell us where to install exclusion screening through the cherry season?",
            "Does seasonal canopy sampling establish where barrier fabric belongs in a cherry orchard?",
            "Should sticky cards go in the lower canopy based on SWD fruit samples through the season?",
            "Can orchard samples decide where a lure station goes in the lower canopy as cherries ripen?",
            "Can one lower-canopy sample tell us where to install a bait station for seasonal SWD monitoring?",
            "Does a lower-canopy fruit sample establish treatment placement through the cherry season?",
            "Does sampling by canopy position show where a push-pull emitter should go as cultivars ripen?",
            "Does seasonal lower-canopy SWD sampling show where we should be spraying?",
            "Should SWD repellents go in the lower canopy based on fruit samples across the season?",
            "Can one season-long SWD fruit sample tell us which canopy rows should be netted?",
            "Should we be trapping in the lower canopy based on SWD fruit samples through the cherry season?",
            "Can one lower-canopy SWD fruit sample represent the cherry season well enough to choose insecticide placement?",
            "Could seasonal SWD sampling represent enough of the upper versus lower cherry canopy to decide where an odor dispenser goes?",
            "Does a stratified SWD sample represent each cherry row over the season well enough to select a sticky-card location?",
            "Is a lower-canopy SWD sample representative across ripening cultivars for choosing where exclusion screening belongs?",
            "Will an upper-canopy SWD sample represent orchard infestation over the season well enough to pick a bait-station site?",
            "Can a lower-canopy SWD fruit sample be representative enough to justify targeting the south cherry row with insecticide throughout the season?",
            "Could an upper-canopy SWD sample represent the ripening season well enough to tell us to put an odor dispenser in the north row?",
            "Does a stratified SWD sample represent each cherry row over the season well enough to tell us which canopy should hang sticky cards?",
            "Is a lower-canopy SWD sample representative across cultivars for focusing pesticide applications on the south orchard row?",
            "Will an upper-canopy SWD sample represent seasonal infestation well enough to position a lure station in the lower row?",
            "Can one north-row SWD sample be representative over ripening cultivars before we put barrier fabric on the lower canopy?",
            "Where should we collect seasonal SWD fruit samples across north and south rows to decide which canopy receives insecticide?",
            "How should we sample upper and lower cherry positions through ripening before choosing a repellent dispenser location for SWD?",
            "Please design a representative SWD sampling map across canopy heights and cultivars so we can position bait stations?",
            "How should orchard crews measure SWD in north and south canopy positions before selecting spray zones for the season?",
            "Design a seasonal fruit-collection plan across upper and lower canopy areas to choose where sticky cards should hang for SWD.",
            "Where should we sample SWD-infested cherries across rows to locate repellent emitters during cultivar ripening?",
            "How should we monitor seasonal SWD aggregation by canopy aspect to place lure stations?",
            "In a hot, fan-ventilated tunnel, how should we sample upper and lower canopy positions over the season to determine whether an SWD net remains effective?",
            "How should we collect SWD from north and south canopy zones over time if the actual question is whether hot, fan-assisted netting works?",
            "How should we monitor parasitoid emergence across north and south cherry rows as SWD populations change over the season?",
            "How should we measure parasitoid diversity in top and bottom canopy fruit while SWD densities rise over time?",
            "Where should we monitor pollinator activity across upper and lower cherry canopy positions as SWD abundance changes over the season?",
            "How should we collect yeast communities from north and south cherry rows across ripening while studying SWD ecology?",
            "Can orchard sampling across heights over the season determine which branch gets treated for SWD?",
            "Could representative SWD fruit samples by row guide our placement plan for odor hardware during ripening?",
            "Can SWD samples from north and south rows select the canopy for a push-pull release as cultivars mature?",
            "Would sampling SWD cherries over time identify the row that needs a physical barrier?",
            "Can a representative lower-canopy SWD sample choose the row for chemical protection across the cherry season?",
            "Should soil samples span north and south orchard rows through ripening while we track SWD pressure?",
            "How should leaves be collected from upper and lower cherry branches over the season during an SWD ecology study?",
            "At low and high population density, should our cherries come from both canopy heights and both compass sides?",
            "Is the representativeness of one southern-row fruit pull stable from early to late cultivars?",
            "Inside each netted treatment block, how should we collect cherries across canopy aspects over the season?",
            "Canopy samples are an endpoint in a barrier-mesh experiment; are both row edges and the center needed across cultivars?",
            "Does one southern-row cherry collection remain representative from early-ripening to late-ripening varieties?",
            "Inside netted experimental plots, should seasonal cherry samples rotate among edges, center, canopy heights, and aspects?",
            "Can a seasonwide cherry sampling map identify the row that should be sprayed for spotted wing drosophila?",
            "Would a high-density SWD fruit sample justify focusing control hardware on the lower south side?",
            "What row-by-row sampling plan should we use for predatory mites in cherries while tracking seasonal D. suzukii pressure?",
            "Can our seasonal cherry samples tell the spray crew which SWD row should receive the first insecticide pass?",
            "How should SWD raspberry fruit samples be distributed between border and interior canopy zones from early to late harvest?",
            "Can a lower-canopy blueberry collection represent Drosophila suzukii infestation as berry cultivars ripen?",
            "How should peach fruit inspections for Drosophila suzukii span upper and lower tree crowns as seasonal density increases?",
            "How should SWD-infested apricots be sampled between windward and leeward orchard rows as early and late cultivars ripen?",
            "For Drosophila suzukii in pears, what fruit-inspection allocation across upper and lower crowns would represent infestation from first pick to final harvest?",
            "Would seasonal SWD fruit sampling in inner and outer sweet-cherry crowns prove that a volatile repellent works?",
            "How should adult SWD trap counts be allocated among border and interior sweet-cherry rows over successive harvest weeks?",
            "At sunrise versus dusk during sweet-cherry ripening, should SWD fruit collections alternate between east- and west-facing canopy sectors?",
            "How should spider abundance be sampled across outer and inner sweet-cherry rows from bloom through late harvest while SWD pressure increases?",
            "Should sweet-cherry sugar and firmness measurements be balanced between top and bottom canopy fruit as Drosophila suzukii density rises toward harvest?",
            "For Drosophila suzukii adults, should trapping stations be inspected in upper and lower sweet-cherry crowns at each cultivar harvest?",
            "Where should an SWD repellent dispenser be installed within the sweet-cherry canopy as cultivars move from blush to harvest?",
            "Would repeated SWD-infested sweet-cherry samples across orchard rows and canopy tiers over the season demonstrate that a volatile repellent works?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([record])
            unrelated = [
                build_reviewed_science_answer(index, question)
                for question in unrelated_questions
            ]

        for question, answer in zip(unrelated_questions, unrelated, strict=True):
            with self.subTest(unrelated_question=question):
                if answer is not None:
                    self.assertNotIn("Do not use one fixed lower-south", answer["answer"])
                    self.assertTrue(
                        all(
                            item["record_id"] != record_id
                            for item in answer["evidence"]
                        )
                    )

    def test_dbm_chemosensory_and_resistance_evidence_route_handles_unseen_paraphrases(self):
        record_ids = (
            "dbm:openalex:W2119258755",
            "dbm:openalex:W2289612981",
            "dbm:openalex:W2754278786",
            "dbm:openalex:W3022069165",
            "dbm:openalex:W4285394072",
            "dbm:openalex:W4392755518",
        )
        questions = (
            "What direct evidence does Ask Insects have for odorant receptors, "
            "chemoreception genes, and resistance-related behavior in diamondback "
            "moth, and what important uncertainties remain?",
            "For Plutella xylostella, which chemosensory genes and odorant receptors "
            "have direct functional evidence, and how does that differ from the "
            "behavioral evidence in insecticide-resistant strains?",
            "Summarize DBM molecular odor detection and what resistant-strain "
            "movement and egg-laying results do and do not establish.",
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
                    for record_id in record_ids
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
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                for fragment in (
                    "54 odorant receptors",
                    "PxylOR11",
                    "PxylOR16",
                    "CRISPR",
                    "gamma-cyhalothrin",
                    "spinetoram",
                    "does not establish",
                    "field crop protection",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    set(record_ids),
                )
                or11 = next(
                    item
                    for item in answer["evidence"]
                    if item["record_id"] == "dbm:openalex:W4285394072"
                )
                self.assertEqual(
                    or11["title"],
                    "Odorant Receptor PxylOR11 Mediates Repellency of Plutella "
                    "xylostella to Aromatic Volatiles",
                )
                self.assertEqual(
                    or11["url"],
                    "https://doi.org/10.3389/fphys.2022.938555",
                )
                self.assertEqual(
                    or11["provenance"]["source_id"],
                    "doi:10.3389/fphys.2022.938555",
                )
                self.assertIn(
                    "dual-choice bioassays",
                    or11["provenance"]["locator"].casefold(),
                )

    def test_dbm_receptor_and_resistance_routes_answer_narrow_scientist_questions(self):
        record_ids = (
            "dbm:openalex:W2289612981",
            "dbm:openalex:W2754278786",
            "dbm:openalex:W4285394072",
            "dbm:openalex:W4392755518",
        )
        cases = (
            (
                "Which diamondback moth odorant receptors have direct functional "
                "evidence, which ligands were tested, and what does each experiment "
                "not prove?",
                {
                    "dbm:openalex:W2754278786",
                    "dbm:openalex:W4285394072",
                    "dbm:openalex:W4392755518",
                },
                ("PxylOR11", "PxylOR16", "heptanal", "field crop protection"),
            ),
            (
                "How does physiological insecticide resistance relate to oviposition "
                "and larval movement avoidance in DBM, and does the study show the "
                "same mechanism?",
                {"dbm:openalex:W2289612981"},
                (
                    "gamma-cyhalothrin",
                    "spinetoram",
                    "life-stage",
                    "does not identify",
                ),
            ),
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
                    for record_id in record_ids
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question, _, _ in cases
            ]

        for (question, expected_record_ids, fragments), answer in zip(
            cases, answers, strict=True
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    expected_record_ids,
                )
                for fragment in fragments:
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_named_dbm_receptors_route_to_their_exact_primary_papers(self):
        records = {
            "dbm:openalex:W4285394072": (
                "doi:10.3389/fphys.2022.938555",
                "https://doi.org/10.3389/fphys.2022.938555",
                "dual-choice bioassays",
            ),
            "dbm:openalex:W4392755518": (
                "doi:10.1186/s12915-024-01862-9",
                "https://doi.org/10.1186/s12915-024-01862-9",
                "CRISPR/Cas9 knockout",
            ),
        }
        cases = (
            (
                "Which aromatic volatiles activated PxylOR11 in diamondback moth, "
                "and what direct evidence linked that receptor to female repellency?",
                "dbm:openalex:W4285394072",
                ("benzyl alcohol", "salicylaldehyde", "phenylacetaldehyde", "Xenopus"),
            ),
            (
                "For PxylOR11, how do the oocyte recordings, antennal response, and "
                "female dual-choice result fit together, and is there knockout evidence?",
                "dbm:openalex:W4285394072",
                ("Xenopus", "antennal", "dual-choice", "did not use a receptor knockout"),
            ),
            (
                "What direct evidence shows that PxylOR16 mediates diamondback moth "
                "avoidance of heptanal, and what does the study not prove about crop protection?",
                "dbm:openalex:W4392755518",
                ("heptanal", "larvae", "adults", "CRISPR", "field crop protection"),
            ),
            (
                "What did deleting PxylOR16 show about heptanal avoidance in Plutella "
                "xylostella, and where did the odor originate?",
                "dbm:openalex:W4392755518",
                ("knockout", "heptanal", "parasitoid", "Cotesia vestalis"),
            ),
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
                    for record_id in records
                ]
            )
            answers = [
                answer_question(question, artifact_dir=Path(tmpdir))
                for question, _, _ in cases
            ]

        for (question, expected_record_id, fragments), answer in zip(
            cases, answers, strict=True
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {expected_record_id},
                )
                for fragment in fragments:
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                source_id, public_url, locator_fragment = records[expected_record_id]
                evidence = answer["evidence"][0]
                self.assertEqual(evidence["provenance"]["source_id"], source_id)
                self.assertEqual(evidence["url"], public_url)
                self.assertIn(
                    locator_fragment.casefold(),
                    evidence["provenance"]["locator"].casefold(),
                )

    def test_normal_answer_path_returns_exact_dbm_mechanism_sources(self):
        from askinsects.cli import compact_agent_answer

        record_ids = (
            "dbm:openalex:W2119258755",
            "dbm:openalex:W2289612981",
            "dbm:openalex:W2754278786",
            "dbm:openalex:W3022069165",
            "dbm:openalex:W4285394072",
            "dbm:openalex:W4392755518",
        )
        question = (
            "What links diamondback moth chemosensory receptors to odor avoidance, "
            "and how is that evidence different from resistance-linked behavior?"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="plutella_xylostella_literature",
                        locator=f"records#{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            answer = answer_question(question, artifact_dir=artifact_dir)

        self.assertTrue(answer["ok"])
        self.assertEqual(answer["answer_shape"], "reviewed_science")
        self.assertEqual(
            {item["record_id"] for item in answer["evidence"]},
            set(record_ids),
        )
        final_answer = compact_agent_answer(answer)["final_answer"]
        self.assertIn(
            "[Odorant Receptor PxylOR11 Mediates Repellency of Plutella "
            "xylostella to Aromatic Volatiles]"
            "(https://doi.org/10.3389/fphys.2022.938555)",
            final_answer,
        )
        self.assertIn("Source ID: `doi:10.3389/fphys.2022.938555`", final_answer)
        self.assertIn("Locator: `Abstract: antennal tissue expression", final_answer)

    def test_fresh_swd_and_aedes_topics_use_exact_primary_source_provenance(self):
        records = {
            "swd:openalex_literature:openalex:W4413971464": (
                "doi:10.1017/s0007485325100369",
                "https://doi.org/10.1017/S0007485325100369",
                "two-choice planar olfactometer",
            ),
            "swd:openalex_literature:openalex:W3199560580": (
                "doi:10.1093/ee/nvab099",
                "https://doi.org/10.1093/ee/nvab099",
                "24, 48, or 72",
            ),
            "swd:openalex_literature:openalex:W4411730655": (
                "doi:10.1093/ee/nvaf057",
                "https://doi.org/10.1093/ee/nvaf057",
                "field raspberry",
            ),
            "swd:openalex_literature:openalex:W3161910963": (
                "doi:10.3389/fmicb.2021.656406",
                "https://doi.org/10.3389/fmicb.2021.656406",
                "axenic and conventional",
            ),
            "aedes_primary_behavior:pmc:PMC3794971": (
                "doi:10.1371/journal.pntd.0002486",
                "https://doi.org/10.1371/journal.pntd.0002486",
                "null-mutant host-seeking",
            ),
            "openalex:W4225097850": (
                "doi:10.1038/s41598-022-10825-5",
                "https://doi.org/10.1038/s41598-022-10825-5",
                "AeCyc knockout",
            ),
            "openalex:W3187681115": (
                "doi:10.1016/j.cub.2021.07.003",
                "https://doi.org/10.1016/j.cub.2021.07.003",
                "Figure 2 and Supplementary Figure S2",
            ),
        }
        cases = (
            (
                "Can a low dose of methyl jasmonate attract SWD even when a higher "
                "dose repels it, and which dose units were actually tested?",
                {"swd:openalex_literature:openalex:W4413971464"},
                ("3.86 to 15.45", "309.0", "filter paper"),
            ),
            (
                "Did 24, 48, or 72 hours of pre-exposure make female SWD habituate "
                "to octenol or 2-pentylfuran, and what did the assay not establish?",
                {"swd:openalex_literature:openalex:W3199560580"},
                ("no loss of deterrence", "geosmin", "field persistence"),
            ),
            (
                "How should we connect fewer pupae from treated raspberries in the "
                "SWD push-pull study to a defensible crop-protection claim?",
                {"swd:openalex_literature:openalex:W4411730655"},
                ("fewer pupae", "marketable yield", "commercial crop-protection"),
            ),
            (
                "How could microbiome status, mating state, and starvation confound "
                "the behavioral baseline in an SWD repellent assay?",
                {"swd:openalex_literature:openalex:W3161910963"},
                ("microbiome", "virgin", "starvation"),
            ),
            (
                "Is NPYLR1 required for post-blood-meal host-seeking suppression in "
                "Aedes aegypti, or did the null-mutant experiment rule that out?",
                {"aedes_primary_behavior:pmc:PMC3794971"},
                ("not required", "null mutants", "unknown receptor"),
            ),
            (
                "Why should time after lights-on be controlled in an Aedes aegypti "
                "repellent assay, and what did the cycle knockout actually change?",
                {"openalex:W4225097850"},
                ("locomotor", "host-odor", "blood-feeding"),
            ),
            (
                "An AeCyc knockout changes host-odor response and blood feeding but "
                "also egg hatch, development, survival, and mating. Can we use it to "
                "infer a time-of-day repellent effect without separating general "
                "fitness costs?",
                {"openalex:W4225097850"},
                (
                    "egg hatching",
                    "development",
                    "survival",
                    "mating",
                    "cannot be assigned solely",
                    "intact mosquitoes",
                ),
            ),
            (
                "If Aedes aegypti op1 or op2 is knocked out alone versus both "
                "together, what does that show about visual target attraction and "
                "sensory redundancy?",
                {"openalex:W3187681115"},
                ("op1", "op2", "double mutants", "odor tracking"),
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="generic_public_literature_lane",
                        locator=f"records#{record_id}",
                    )
                    for record_id in records
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question, _, _ in cases
            ]

        for (question, expected_record_ids, fragments), answer in zip(
            cases, answers, strict=True
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    expected_record_ids,
                )
                for fragment in fragments:
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                for item in answer["evidence"]:
                    source_id, public_url, locator_fragment = records[item["record_id"]]
                    self.assertEqual(item["provenance"]["source_id"], source_id)
                    self.assertEqual(item["url"], public_url)
                    self.assertIn(
                        locator_fragment.casefold(),
                        item["provenance"]["locator"].casefold(),
                    )

    def test_unnamed_swd_dose_reversal_routes_to_exact_meja_evidence(self):
        from askinsects.cli import compact_agent_answer

        record_id = "swd:openalex_literature:openalex:W4413971464"
        questions = (
            "Our unnamed SWD volatile is attractive at a low loading and repellent "
            "at a higher loading. What laboratory series should "
            "we run before translating it to a field rate?",
            "For spotted wing drosophila, how should we bracket a source-mass "
            "series after seeing attraction at lower source masses and repellency "
            "at higher source masses, and which exposure units must we measure?",
            "Our SWD assay shows that an unnamed odor draws flies at lower source "
            "loads but pushes them away at higher source loads. What dose series "
            "and exposure measurements should we run next?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator=f"records#{record_id}",
                    )
                ]
            )
            answers = [
                answer_question(question, artifact_dir=artifact_dir)
                for question in questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {record_id},
                )
                self.assertIn("bracket", answer["answer"].casefold())
                self.assertIn("separate carrier-controlled", answer["answer"].casefold())
                self.assertIn("release rate", answer["answer"].casefold())
                self.assertIn("air concentration", answer["answer"].casefold())
                final_answer = compact_agent_answer(answer)["final_answer"]
                self.assertIn(
                    "[Dose-dependent effect of methyl jasmonate on Drosophila "
                    "suzukii (Matsumura) (Diptera: Drosophilidae)]"
                    "(https://doi.org/10.1017/S0007485325100369)",
                    final_answer,
                )
                self.assertIn(
                    "Source ID: `doi:10.1017/s0007485325100369`",
                    final_answer,
                )
                self.assertIn(
                    "Locator: `Abstract: two-choice cage and two-choice planar "
                    "olfactometer",
                    final_answer,
                )

        negative_questions = (
            "For SWD, a volatile source below the canopy pulled flies toward it, "
            "while one above the crop pushed them away. How should we measure the "
            "spatial response?",
            "For SWD, attraction occurred below the canopy and repellency above "
            "the crop during field exposure.",
            "How should source-to-fly distance and field exposure be reported for "
            "an SWD repellent tested at one high loading?",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator=f"records#{record_id}",
                    )
                ]
            )
            negative_answers = [
                build_reviewed_science_answer(index, question)
                for question in negative_questions
            ]

        for question, answer in zip(
            negative_questions, negative_answers, strict=True
        ):
            with self.subTest(question=question):
                if answer is not None:
                    self.assertNotIn(
                        record_id,
                        {item["record_id"] for item in answer["evidence"]},
                    )

        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="drosophila_suzukii_core",
                        locator=f"records#{record_id}",
                    )
                ]
            )
            named_answer = build_reviewed_science_answer(
                index,
                "Why is methyl jasmonate attractive at a low dose but repellent "
                "at a higher dose in SWD?",
            )

        self.assertIsNotNone(named_answer)
        assert named_answer is not None
        self.assertTrue(
            named_answer["answer"].startswith(
                "Methyl jasmonate was not uniformly repellent."
            )
        )

    def test_hop_greenhouse_result_routes_to_exact_field_translation_evidence(self):
        from askinsects.cli import compact_agent_answer
        from askinsects.sources.swd_primary_field_evidence import (
            build_swd_primary_field_evidence_records,
        )

        questions = (
            "A hop-pellet treatment cut SWD larval infestation in our greenhouse "
            "cages. Should I advance the same soil-applied pellets into a commercial "
            "raspberry push program, and what result would stop me?",
            "Humulus lupulus reduced spotted wing drosophila infestation in a short "
            "cage assay. What field evidence and stopping rule should govern a "
            "raspberry or blackberry trial?",
            "Can a confined-cage SWD result with hop pellets qualify the unchanged "
            "formulation for commercial field use?",
        )
        negative_questions = (
            "Which hop cultivar has the highest alpha-acid percentage for brewing?",
            "How should I measure generic greenhouse humidity in an SWD colony?",
            "Does a raspberry aroma attract SWD in an olfactometer?",
            "Did hop pellets reduce SWD infestation in the greenhouse cage?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                build_swd_primary_field_evidence_records(
                    retrieved_at="2026-07-19T00:00:00Z"
                )
            )
            answers = [
                answer_question(question, artifact_dir=artifact_dir)
                for question in questions
            ]
            negatives = [
                build_reviewed_science_answer(index, question)
                for question in negative_questions
            ]

        expected_record_id = (
            "swd_primary_field:doi:10.1016/j.cropro.2019.05.033"
        )
        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {expected_record_id},
                )
                for fragment in (
                    "do not advance",
                    "24-hour",
                    "commercial raspberry and blackberry",
                    "larvae in fruit",
                    "stop",
                ):
                    self.assertIn(fragment, answer["answer"].casefold())
                final_answer = compact_agent_answer(answer)["final_answer"]
                self.assertIn(
                    "[Evaluation of hop (Humulus lupulus) as a repellent for the "
                    "management of Drosophila suzukii]"
                    "(https://doi.org/10.1016/j.cropro.2019.05.033)",
                    final_answer,
                )
                self.assertIn(
                    "Source ID: `doi:10.1016/j.cropro.2019.05.033`",
                    final_answer,
                )
                self.assertIn(
                    "Locator: `Abstract; Results sections 3.1-3.3; Discussion and "
                    "conclusion, pp. 4-5; Figures 1-2`",
                    final_answer,
                )

        for question, answer in zip(negative_questions, negatives, strict=True):
            with self.subTest(question=question):
                if answer is not None:
                    self.assertNotIn(
                        expected_record_id,
                        {item["record_id"] for item in answer["evidence"]},
                    )

    def test_catalog_preserves_exact_title_and_complete_figure_locator(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        provenance = {
            item["record_id"]: item for item in catalog["source_provenance"]
        }
        push_pull = provenance[
            "swd:openalex_literature:openalex:W4411730655"
        ]
        self.assertEqual(
            push_pull["title"],
            "Oviposition deterrent as a component of a push–pull management "
            "approach for Drosophila suzukii",
        )

        seasonal_morph = provenance[
            "swd_olfaction_literature:pubmed:29668908"
        ]
        self.assertEqual(
            seasonal_morph["title"],
            "Comparative Antennal and Behavioral Responses of Summer and Winter "
            "Morph Drosophila suzukii (Diptera: Drosophilidae) to Ecologically "
            "Relevant Volatiles",
        )
        self.assertEqual(
            seasonal_morph["locator"],
            "Abstract: female summer- and winter-morph electroantennogram responses "
            "to six volatiles; no-choice behavior for geosmin and bornyl acetate; "
            "geosmin T-maze aversion",
        )

        cffa_blend = provenance[
            "swd:openalex_literature:openalex:W4386466923"
        ]
        self.assertEqual(
            cffa_blend["title"],
            "A 2-component blend of coconut oil-derived fatty acids as an "
            "oviposition deterrent against Drosophila suzukii (Drosophilidae: "
            "Diptera)",
        )
        self.assertEqual(
            cffa_blend["locator"],
            "Methods: Laboratory Choice Test 1, Laboratory No-Choice Test, and "
            "Table 1; Results: Field Test 1, Laboratory Choice Tests 1-2, "
            "Laboratory No-Choice Test, and Figure 4; Discussion: unresolved "
            "spatial- versus contact-mediated mode",
        )

        density = provenance["swd:openalex_literature:openalex:W3171171860"]
        self.assertEqual(
            density["title"],
            "Plasticity in Oviposition Site Selection Behavior in Drosophila "
            "suzukii (Diptera: Drosophilidae) in Relation to Adult Density and "
            "Host Distribution and Quality",
        )

        yeast = provenance["swd:openalex_literature:openalex:W4213332511"]
        self.assertEqual(
            yeast["title"],
            "Hanseniaspora uvarum Attracts Drosophila suzukii (Diptera: "
            "Drosophilidae) With High Specificity",
        )
        self.assertEqual(
            yeast["locator"],
            "Methods: virgin 3-6-day-old females starved for 24 hours; Results: "
            "wind-tunnel takeoff-plus-upwind-flight response and source contact",
        )

        fruit_injury = provenance[
            "swd:openalex_literature:openalex:W3163892682"
        ]
        self.assertEqual(
            fruit_injury["title"],
            "Mind the Wound!-Fruit Injury Ranks Higher than, and Interacts with, "
            "Heterospecific Cues for Drosophila suzukii Oviposition",
        )

        exact_titles = {
            "aedes_primary_behavior:pubmed:469272": (
                "Humoral inhibition of host-seeking in Aedes aegypti during "
                "oöcyte maturation"
            ),
            "openalex:W3048721146": (
                "Behavioral responses to transfluthrin by Aedes aegypti, "
                "Anopheles minimus, Anopheles harrisoni, and Anopheles dirus "
                "(Diptera: Culicidae)"
            ),
            "swd:openalex_literature:openalex:W3132534524": (
                "Olfactory Cues From Host- and Non-host Plant Odor Influence the "
                "Behavioral Responses of Adult Drosophila suzukii (Diptera: "
                "Drosophilidae) to Visual Cues"
            ),
            "swd:openalex_literature:openalex:W4397009635": (
                "Contributions of γ-Aminobutyric Acid (GABA) Receptors for the "
                "Activities of Pectis brevipedunculata Essential Oil against "
                "Drosophila suzukii and Pollinator Bees"
            ),
            "human_repellent_guidance:epa:810.3700": (
                "Product Performance Test Guidelines OPPTS 810.3700: Insect "
                "Repellents to be Applied to Human Skin"
            ),
            "human_repellent_guidance:who:2009.4": (
                "Guidelines for efficacy testing of mosquito repellents for "
                "human skin"
            ),
            "dbm:openalex:W2114561940": (
                "Host Selection Behavior and the Fecundity of Plutella "
                "xylostella (Lepidoptera: Plutellidae) on Multiple Host Plants"
            ),
            "dbm:openalex:W2164349268": (
                "Oviposition by Plutella xylostella (Lepidoptera: Plutellidae) "
                "and Effects of Phylloplane Waxiness"
            ),
            "dbm:openalex:W4413460540": (
                "A semiochemical attract-and-kill formulation to manage "
                "diamondback moth (Lepidoptera: Plutellidae)"
            ),
            "dbm:openalex:W4393189143": (
                "Inhibition Effect of Non-Host Plant Volatile Extracts on "
                "Reproductive Behaviors in the Diamondback Moth Plutella "
                "xylostella (Linnaeus)"
            ),
        }
        for record_id, title in exact_titles.items():
            with self.subTest(record_id=record_id):
                self.assertEqual(provenance[record_id]["title"], title)

        self.assertEqual(
            provenance["aedes_primary_behavior:pmc:PMC3577799"]["locator"],
            "Abstract and Results: behavioral insensitivity and reduced "
            "electroantennogram response three hours after DEET pre-exposure; "
            "odor and host-stimulus control experiments",
        )
        self.assertEqual(
            provenance["dbm:openalex:W2141627881"]["locator"],
            "Abstract and Results: airflow repellency and oviposition-deterrence "
            "endpoints for Mikania micrantha essential oil and five volatile "
            "compounds",
        )
        self.assertEqual(
            provenance["dbm:openalex:W4393189143"]["locator"],
            "Methods 2.4-2.7 and Results 3.2-3.3: male orientation to sex "
            "pheromone plus essential oil, field trap catch, and female "
            "oviposition responses",
        )

        durability = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "aedes-skin-repellent-durability"
        )
        self.assertEqual(
            durability["source_record_ids"],
            [
                "human_repellent_guidance:who:2009.4",
                "human_repellent_guidance:epa:810.3700",
            ],
        )
        self.assertNotIn("wash-in", durability["answer"].casefold())

        vision = provenance["openalex:W3187681115"]
        self.assertIn("Figure 2", vision["locator"])
        self.assertIn("Supplementary Figure S2", vision["locator"])
        self.assertIn("Figure 3", vision["locator"])
        self.assertIn("Supplementary Figure S3", vision["locator"])
        self.assertIn("Figure 4", vision["locator"])
        self.assertIn("Supplementary Figure S4", vision["locator"])

        topics = {topic["id"]: topic for topic in catalog["topics"]}
        self.assertEqual(
            topics["swd-eggs-to-crop-protection"]["source_provenance"][0][
                "title"
            ],
            push_pull["title"],
        )
        self.assertEqual(
            topics["aedes-visual-rhodopsin-redundancy"]["source_provenance"][0][
                "locator"
            ],
            vision["locator"],
        )

    def test_reality_eval_repairs_generalize_to_neighboring_paraphrases(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topics = {topic["id"]: topic for topic in catalog["topics"]}
        cases = (
            (
                "Nearly all SWD eggs moved to untreated fruit while total fecundity fell. Which no-choice, survival, movement, and mating controls distinguish avoidance from impairment?",
                "swd-choice-endpoint-confounds",
                ("cannot by itself", "total eggs", "female survival"),
            ),
            (
                "Treated SWD berries were firmer and drier while control berries were wounded. How should those fruit conditions be crossed before assigning the effect to repellency?",
                "swd-fruit-condition-controls",
                ("factorial design", "fruit injury directly changed oviposition", "did not measure a specific moisture effect"),
            ),
            (
                "Our SWD treatment arm used firm intact berries while the comparison arm used soft wounded fruit. Can the egg difference isolate the compound?",
                "swd-fruit-condition-controls",
                ("factorial design", "fruit injury directly changed oviposition", "record those variables"),
            ),
            (
                "The SWD intervention and comparator groups differed in berry firmness and wounding. What prevents attributing their egg-count contrast to the compound?",
                "swd-fruit-condition-controls",
                ("factorial design", "fruit injury directly changed oviposition", "record those variables"),
            ),
            (
                "Three hours after DEET pre-exposure, Aedes aegypti respond less strongly. How do we separate sensory adaptation from associative learning?",
                "aedes-olfactory-learning",
                ("reduced electroantennogram response", "dopamine signaling", "sensory adaptation"),
            ),
            (
                "Which human-seeking cues remain after a mosquito repellent exposure, and what exactly did the visual-rhodopsin experiment show?",
                "aedes-host-cues-after-exposure",
                (
                    "nearly eliminated at 1000 and 100 lux",
                    "abolished at 25 and 5 lux",
                    "compound-specific exposure must be tested",
                ),
            ),
            (
                "Our SWD odor candidate received more eggs on a firmer fruit analog than its vehicle. What does mechanosensation evidence say, and which control separates odor from firmness?",
                "swd-fruit-texture-mechanosensation",
                (
                    "cannot isolate odor",
                    "cross candidate versus vehicle",
                    "factorial design",
                ),
            ),
            (
                "How should we cross inoculation and substrate hardness in an SWD egg-laying assay, and which egg endpoints should we keep separate?",
                "swd-microbial-oviposition",
                (
                    "cross inoculated versus uninoculated",
                    "egg allocation",
                    "total egg output",
                ),
            ),
            (
                "Did adult SWD ignore nutritional composition when choosing where to lay eggs, or did both species prefer one protein-to-carbohydrate ratio?",
                "swd-nutrition-versus-oviposition-texture",
                (
                    "both species preferentially laid eggs on the 1:8 protein-to-carbohydrate diet",
                    "fewer eggs on the 1:1 diet",
                    "did not differ significantly in their nutritional preference",
                    "D. suzukii showed no significant hardness preference",
                ),
            ),
            (
                "Can an SWD assay with fed virgins be compared directly with one using starved mated gravid females?",
                "swd-physiological-state-confounds",
                (
                    "Do not compare",
                    "conventional mated gravid females at 7 hours",
                    "not significant at 12 or 24 hours",
                ),
            ),
            (
                "What did the SWD foraging study show about fed conventional gravid females versus starved axenic virgins, and why can those batches not be compared?",
                "swd-physiological-state-confounds",
                (
                    "Do not compare",
                    "feeding, mating, and gravidity changed together",
                    "sex and microbiome status",
                ),
            ),
            (
                "Can I compare SWD egg counts from a treatment run at noon with a control run at night, or must I block clock time?",
                "swd-diurnal-oviposition-confound",
                ("No.", "concurrently", "daily egg-laying rhythm"),
            ),
            (
                "Which product-specific airflow, carrier, release, and delivery information is missing from an Aedes spatial-repellency chamber result?",
                "aedes-spatial-environment-controls",
                (
                    "cannot by itself define a complete product-specific exposure package",
                    "release rate",
                    "delivery hardware",
                ),
            ),
            (
                "Before broad diamondback moth repellent screening, which experiment closes the candidate-specific evidence gap?",
                "dbm-first-baseline-experiment",
                ("source release rate", "choice and no-choice oviposition", "same measured candidate headspace"),
            ),
            (
                "How should we cross reduced leaf wax with larva-induced headspace to test the sequence from diamondback moth orientation through egg laying?",
                "dbm-host-cue-sequence-experiment",
                (
                    "crossed 2 x 2 experiment",
                    "Generate the headspace separately",
                    "initial orientation",
                    "total eggs",
                ),
            ),
            (
                "After fewer diamondback moth adults land, which larval, damage, beneficial-insect, and yield gates still matter?",
                "dbm-product-endpoint-ladder",
                ("beneficial-insect safety", "separate safety gate", "adult avoidance alone"),
            ),
            (
                "If Aedes aegypti combines carbon dioxide, human odor, and body infrared, could blocking thermal infrared alone protect a person?",
                "aedes-thermal-infrared-integration",
                ("roughly 34 C", "TRPA1", "not a validated stand-alone repellent target"),
            ),
            (
                "Should a volatile selected with summer-morph SWD be rescreened in winter morphs before a year-round oviposition program?",
                "swd-seasonal-morph-olfaction",
                ("matched delivered doses", "oviposition", "field efficacy"),
            ),
            (
                "Aerosol puffers beat passive octenol vials in raspberries. What exposure and crop measurements should the next field trial collect?",
                "swd-field-plume-delivery",
                ("emitted mass", "time-resolved canopy concentration", "marketable yield"),
            ),
            (
                "The DBM citronella paper inferred less larval feeding from lower adult egg output. What else could explain it and what should the repeat measure?",
                "dbm-citronella-endpoint-separation",
                ("development time", "survivor selection", "total eggs", "egg allocation"),
            ),
        )
        record_ids = sorted(
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
                    for record_id in record_ids
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question, _, _ in cases
            ]

        for (question, topic_id, fragments), answer in zip(cases, answers, strict=True):
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
                if topic_id == "aedes-spatial-environment-controls":
                    self.assertNotIn(
                        "current public source plane", answer["answer"].casefold()
                    )

    def test_expanded_locators_cover_reviewed_protocol_claims(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        provenance = {
            item["record_id"]: item for item in catalog["source_provenance"]
        }
        citronella_locator = provenance[
            "aedes_primary_behavior:pmc:PMC9866038:table8"
        ]["locator"]
        self.assertIn("Methods", citronella_locator)
        self.assertIn("skin-permeation", citronella_locator)
        self.assertIn("Table 8", citronella_locator)

        state_topic = next(
            topic
            for topic in catalog["topics"]
            if topic["id"] == "swd-physiological-state-confounds"
        )
        state_locator = state_topic["source_provenance"][0]["locator"]
        self.assertIn("5- to 10-day-old adults", state_locator)
        self.assertIn("15-hour food deprivation", state_locator)
        self.assertIn("7, 12, and 24 hours", state_locator)

        epa_locator = provenance["human_repellent_guidance:epa:810.3700"][
            "locator"
        ]
        self.assertIn("section (b)(7) Complete Protection Time", epa_locator)
        self.assertIn("section (c)(1)(iii)(B)", epa_locator)
        self.assertIn("section (c)(1)(ix)", epa_locator)
        self.assertNotIn("Paragraphs (v)", epa_locator)

        transfluthrin_locator = provenance["openalex:W3048721146"]["locator"]
        self.assertIn("Figure 4 and Table 6", transfluthrin_locator)
        self.assertIn("Discussion paragraphs", transfluthrin_locator)

        learning_locator = provenance["openalex:W4315621418"]["locator"]
        self.assertIn("Materials and methods 4(b)(ii)", learning_locator)
        self.assertIn("60-second odor presentation", learning_locator)
        self.assertIn("2-minute inter-trial interval", learning_locator)

    def test_visual_rhodopsin_route_rejects_broader_multimodal_neighbors(self):
        broad_record_ids = {
            "openalex:W4401794442",
            "openalex:W3187681115",
            "openalex:W4297252092",
        }
        questions = (
            "How do carbon dioxide, human odor, vision, and heat combine during "
            "Aedes aegypti host seeking, and are these cues redundant?",
            "If one visual receptor is knocked out in Aedes aegypti, can other "
            "host-seeking cues compensate, or is the whole system redundant?",
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
                    for record_id in broad_record_ids
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question) for question in questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    broad_record_ids,
                )


if __name__ == "__main__":
    unittest.main()
