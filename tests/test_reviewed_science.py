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

    def test_normalized_match_patterns_are_case_insensitive_and_validated(self):
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

            payload = catalog_payload()
            payload["topics"][0]["match"]["required_normalized_pattern_groups"] = [
                [r"\bCHOOSE\b"]
            ]
            answer = build_reviewed_science_answer(
                index,
                "Do female SWD choose firmer places to lay eggs?",
                catalog_path=self.write_catalog(root, payload),
            )
            self.assertIsNotNone(answer)

            payload["topics"][0]["match"]["required_normalized_pattern_groups"] = [
                ["[invalid"]
            ]
            with self.assertRaisesRegex(ReviewedScienceError, "invalid regex"):
                load_reviewed_science_catalog(self.write_catalog(root, payload))

            payload = catalog_payload()
            payload["topics"][0]["match"]["excluded_normalized_patterns"] = [
                "[invalid"
            ]
            with self.assertRaisesRegex(ReviewedScienceError, "invalid regex"):
                load_reviewed_science_catalog(self.write_catalog(root, payload))

            payload = catalog_payload()
            payload["topics"][0]["match"][
                "implicit_species_excluded_normalized_patterns"
            ] = ["[invalid"]
            with self.assertRaisesRegex(ReviewedScienceError, "invalid regex"):
                load_reviewed_science_catalog(self.write_catalog(root, payload))

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
                "After taking away an SWD volatile, which measurements distinguish persistent avoidance, habituation, and a response that vanishes quickly?",
                "Design a washout time course that separates residual odor, learned habituation, and toxic motor impairment in SWD.",
                "How can I tell whether an SWD repellent response persists after odor removal or fades back to baseline?",
                "When the odor source is taken away, what observations separate a lasting SWD behavior change from leftover vapor or temporary paralysis?",
                "What post-exposure schedule would distinguish SWD habituation from residual chemical in the chamber?",
                "How should recovery be tracked after removing an airborne SWD deterrent?",
                "Once an SWD odor treatment ends, how often should behavior be checked to separate recovery from lasting avoidance?",
                "Following exposure, how should I measure whether SWD avoidance survives source removal?",
                "What should we measure after odor withdrawal to distinguish recovery from habituation in SWD?",
                "If SWD still avoids one side for an hour after I remove an odor source, how do I determine whether that is lingering airborne chemical rather than a lasting behavioral change?",
                "After we remove the odor source, how can we separate lingering chemical from a lasting behaviour change in SWD?",
                "If the odor source is removed, what distinguishes residual airborne repellent from learned SWD avoidance?",
                "For an SWD oviposition repellent lead, how should I think about adult or larval pre-exposure before assuming the deterrent will keep working after repeated crop exposure?",
                "Before I trust an SWD oviposition deterrent across repeated crop exposure, how should adult and larval pre-exposure be tested?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertIn("15 minutes, 1 hour, 6 hours, 24 hours, and 48 hours", answer["answer"])
                    self.assertIn("measured airborne concentration or surface residue", answer["answer"])
                    self.assertIn("chemical persistence, not a learned post-exposure effect", answer["answer"])
                    self.assertIn("after verified clearance", answer["answer"])
                    self.assertIn("supports habituation", answer["answer"])
                    self.assertIn("shows retained sensitivity, not persistent avoidance in odor-free air", answer["answer"])
                    self.assertIn("shows rapid loss of the active repellent effect", answer["answer"])
                    self.assertIn("not post-removal recovery measurements", answer["answer"])
                    self.assertIn("does not prove long-term field persistence", answer["answer"])

    def test_recovery_answer_does_not_define_avoidance_without_an_odor_target(self):
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

            answer = build_reviewed_science_answer(
                index,
                "After a volatile is removed, what recovery measurements would show whether SWD avoidance persists, habituates, or rapidly disappears?",
            )

            self.assertIsNotNone(answer)
            assert answer is not None
            self.assertNotIn(
                "still avoid in clean air after the volatile has cleared",
                answer["answer"],
            )
            self.assertIn(
                "An unchanged same-dose rechallenge response shows retained sensitivity",
                answer["answer"],
            )

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
                "Can I score SWD treatment jars in the morning and controls at dusk if the exposure duration is identical?",
                "Can I read SWD treatment cages at dawn and control cages at dusk if both ran for the same exposure time?",
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
                "How can we tell whether apparent vapor repellency in Aedes aegypti is actually knockdown or toxicity?",
                "What dose-matched endpoints distinguish voluntary Aedes vapor avoidance from knockdown and delayed death?",
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
                        "nominal active-ingredient loading or applied dose",
                        "exposure duration constant",
                        "equal paper loading does not guarantee equal delivered vapor exposure",
                        "1-minute intervals",
                        "30 minutes",
                        "same nominal loading and 30-minute exposure",
                        "greater non-contact escape",
                        "reduced escape can indicate knockdown",
                        "contact excitation",
                        "escaped and remaining",
                        "24-hour mortality",
                        "knockdown can suppress escape",
                        "report the dose or loading and observation time for each",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())
                    self.assertNotIn(
                        "less escape as repellency",
                        answer["answer"].casefold(),
                    )

    def test_anopheles_assay_separates_spatial_contact_and_toxic_effects(self):
        record_ids = (
            "reviewed_repellent_evidence:transfluthrin_who_spatial_repellency_assay_guidance_2013",
            "reviewed_repellent_evidence:deet_anopheles_contact_spatial_toxicity_separation_2019",
            "openalex:W3048721146",
        )
        questions = (
            "Our volatile candidate drives Anopheles gambiae out of a chamber but also knocks some mosquitoes down. What assay layout and endpoints would let me call spatial repellency, contact irritancy, toxicity, or none of them without mixing the mechanisms?",
            "How should I design an Anopheles assay to distinguish airborne repellency, an effect that appears only after contact, and toxic knockdown?",
            "Which matched controls and endpoints separate spatial escape, contact irritancy, recovery, and 24-hour mortality in malaria mosquitoes?",
            "An Anopheles candidate causes chamber exits and some delayed deaths. What no-contact and contact-permitted arms keep those claims separate?",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="reviewed_science_test",
                        locator=f"test#{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)
                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertEqual(
                        [item["record_id"] for item in answer["evidence"]],
                        list(record_ids),
                    )
                    for fragment in (
                        "mesh barrier physically prevented contact",
                        "matched contact control",
                        "contact residence",
                        "immediate knockdown",
                        "recovery",
                        "delayed mortality",
                        "24 hours",
                        "Toxic incapacitation can suppress escape",
                        "supports none of those claims",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_aedes_contact_spatial_answer_requires_delivered_vapor_comparability(self):
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
                        locator=f"raw/aedes.json#works/{record_id.split(':')[-1]}",
                    )
                    for record_id in record_ids
                ]
            )

            answer = build_reviewed_science_answer(
                index,
                "Equal transfluthrin on two papers does not necessarily mean equal vapor exposure. How should I verify delivered dose while separating Aedes spatial escape, contact excitation, reversible knockdown, and 24-hour death?",
            )

            self.assertIsNotNone(answer)
            assert answer is not None
            self.assertIn(
                "equal paper loading does not establish equal delivered vapor exposure",
                answer["answer"],
            )
            self.assertIn(
                "same nominal loading and exposed cohorts",
                answer["answer"],
            )
            self.assertIn(
                "report the dose or loading and observation time for every endpoint",
                answer["answer"],
            )

    def test_aedes_post_exposure_recovery_defines_denominators(self):
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
                "What should be measured after Aedes repellent exposure to separate "
                "temporary knockdown, recovery, and mortality?",
                "After an Aedes transfluthrin exposure, how should I compare recovered, "
                "knocked-down, and dead mosquitoes across treatments?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertEqual(answer["evidence"][0]["record_id"], record_id)
                    for fragment in (
                        "immediate knockdown",
                        "repeated recovery",
                        "delayed mortality",
                        "same exposed cohort",
                        "denominators before comparing treatments",
                        "same starting cohort denominator",
                        "not necessarily dead",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

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
                "An Aedes mosquito reaches treated skin and only departs after "
                "tarsal contact. Does that establish distance repellency, and "
                "which paired contact/non-contact assay would separate the effects?",
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
                    "screen mesh barrier",
                    "recorded every minute for 30 minutes",
                    "24-hour mortality",
                    "simultaneous paired non-contact escape response",
                    "R&D interpretation:",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                for unsupported in (
                    "reduced entry",
                    "measure entry",
                    "orientation",
                    "landing, or escape",
                ):
                    self.assertNotIn(unsupported, answer["answer"].casefold())

    def test_er_contact_only_result_pattern_is_interpreted_directly(self):
        record_id = "openalex:W3048721146"
        questions = (
            "If Aedes escapes after touching treated paper while mesh-separated "
            "non-contact escape matches control, what can and cannot be claimed "
            "about spatial repellency, and how should the contact effect be estimated?",
            "The treated and control Aedes noncontact chambers had identical escape, "
            "but treated-contact escape exceeded contact control. Is that a spatial "
            "effect or a contact-associated effect?",
            "Aedes aegypti treatment and control had the same proportion leaving "
            "without surface contact, while a greater proportion left under treatment "
            "than control with surface contact. What does leaving support?",
            "Aedes non-contact escape did not differ from vehicle, while escape rose "
            "when direct treated-paper contact was allowed. What does that pattern "
            "support and what remains unproven?",
            "Aedes escaped equally often from the mesh-separated treatment and "
            "control chambers, but contact-chamber escape increased under treatment. "
            "How should I interpret that?",
            "Non-contact Aedes escape was indistinguishable from vehicle, while "
            "treated-contact escape exceeded contact control. Is there evidence "
            "for a distance effect?",
            "The noncontact treatment and control produced comparable escape, but "
            "escape rose when direct treated-paper contact was allowed. Which effect "
            "does that support?",
            "The treated and vehicle mesh-separated chambers had the same escape, "
            "while mosquitoes escaped more after touching treated paper. What does "
            "this pattern support?",
            "Escape did not differ from control in non-contact treatment chambers, "
            "whereas treated-contact escape was greater than contact control.",
            "Compared with vehicle, the mesh-separated treatment produced "
            "indistinguishable escape; after direct treated-paper contact, escape rose.",
            "Noncontact treated and control chambers yielded the same number of "
            "escapes, but contact treatment yielded more escapes.",
            "After touching treated paper the mosquitoes escaped more, although "
            "treatment and control were indistinguishable in the mesh-separated chambers.",
            "The same escape was recorded for non-contact treatment and vehicle; "
            "increased escape was recorded when treated paper could be touched.",
            "In contact chambers, treatment produced higher escape than control; "
            "in noncontact chambers, escape matched vehicle.",
            "Touching treated paper increased escape, but the non-contact treatment "
            "and control did not differ.",
            "There was no difference from vehicle for escape in the mesh-separated "
            "treatment, while direct contact increased escape.",
            "Escape rates were equivalent between noncontact treatment and vehicle; "
            "allowing direct contact led to more escape.",
            "There was no detectable difference in escape between the mesh-barrier "
            "treatment and control, but treated-paper touch increased escape.",
            "Mosquitoes escaped at the same rate from treatment and control when mesh "
            "prevented contact, then escaped more when permitted to touch treated paper.",
            "With treated paper screened off, treatment escape equaled control; once "
            "surface contact was allowed, escape increased.",
            "In the no-contact chambers the treated side and vehicle yielded equal "
            "escape, while contact exposure produced elevated escape versus control.",
            "The noncontact pair had matching escape counts, treatment versus vehicle, "
            "and the contact pair had an elevated treated response. What can be inferred?",
            "No spatial contrast appeared: treatment and control escaped equally "
            "behind mesh, but contact with treated paper elicited more escape.",
            "Escape climbed with surface contact on treated paper, whereas treatment "
            "and vehicle were indistinguishable behind mesh.",
            "No excess escape appeared with treated paper behind mesh, but once "
            "mosquitoes could touch the surface they escaped more than contact controls.",
            "Treatment and vehicle produced indistinguishable escape without paper "
            "access; granting surface contact increased escape.",
            "The barrier-protected arm and control had equivalent escape, while the "
            "exposed-paper arm produced more escape.",
            "In an escape assay the screened treatment and vehicle were alike then "
            "physical access to treated paper raised the response",
            "When a screen blocked the treated surface, escape was unchanged from "
            "control; removing that separation and permitting touch increased escape.",
            "In the escape chambers direct-contact treated females exited more often "
            "than direct-contact controls while screened females left treatment and "
            "vehicle at the same rate",
            "The no-surface-access treatment equaled vehicle for escape; the accessible "
            "treated-paper condition yielded a larger escape response.",
            "Contact escape exceeded its control first; the corresponding no-contact "
            "escape later proved equal to vehicle.",
            "Despite elevated escape in the treatment-contact pair, the mesh-barrier "
            "treatment stayed level with its control.",
            "Treatment minus control was zero for mesh-separated escape and positive "
            "for contact escape. What does that imply?",
            "There was no noncontact treatment effect on escape relative to vehicle, "
            "only an excess after the mosquitoes contacted treated paper.",
            "Females escaped equally from screened treatment and control, then showed "
            "a larger response once paper contact was enabled.",
            "The mesh-isolated treated chamber tracked the vehicle for escape; the "
            "contact-permitted chamber produced extra escapes.",
            "No difference separated treatment from control with the paper inaccessible "
            "behind gauze; escape rose after actual paper contact.",
            "Escape under contact exposure was greater than control while the barrier "
            "arm remained comparable to vehicle.",
            "treated paper contact produced higher escape noncontact treatment equaled "
            "vehicle how should this be interpreted",
            "A physical divider kept treated-paper escape at the vehicle level, but "
            "taking the divider away increased exits under treatment.",
            "When the repellent surface was unreachable, the treated and control "
            "escape fractions were alike; allowing surface access gave a larger "
            "treated escape fraction.",
            "No-touch treatment and control had the same exit rate, whereas the "
            "touch-permitted treatment had a higher exit rate.",
            "A gauze partition yielded equivalent escape for treatment and vehicle, "
            "while paper contact yielded greater escape under treatment.",
            "With a screen between females and paper, treatment did not differ from "
            "control for escape; without the screen, treated escape exceeded control.",
            "Escape under the inaccessible-paper treatment overlapped vehicle, then "
            "rose when contact was enabled.",
            "The barrier comparison was null for escape, and the direct-touch "
            "comparison was positive.",
            "Contact-enabled escape was greater than control; the contact-blocked "
            "treatment stayed comparable to vehicle.",
            "Treated and vehicle females departed equally when a separator prevented "
            "touch, but treated females departed more after the separator was removed.",
            "The screened arm had no treatment-control difference in exits; the "
            "exposed arm had an excess of exits under treatment.",
            "Without access to the substrate, escape matched control; with access to "
            "treated paper, treatment caused extra escape.",
            "The two barrier arms had identical escape, treatment versus carrier, "
            "while the two open arms showed higher treated escape.",
            "Escape was unchanged by treatment relative to vehicle when mosquitoes "
            "could not reach the paper; it increased once they could reach it.",
            "Contact-first result: elevated treated escape. Noncontact result: "
            "treatment equal to carrier.",
            "A zero treatment effect appeared in the mesh-protected escape data, "
            "followed by a positive treatment effect in the touch-access data.",
            "There was parity between treatment and control for barrier escape, but "
            "a treated excess for contact escape.",
            "Escape curves coincided for the shielded treatment and vehicle, whereas "
            "the touchable-paper treatment escape curve sat above control.",
            "contact accessible mosquitoes escaped more than controls paper shielded "
            "mosquitoes escaped just as often in treatment and vehicle interpret this",
            "More exits occurred from treated contact exposure, despite no difference "
            "between treatment and vehicle when contact was prevented.",
            "The control and no-access treatment produced the same escape count; the "
            "accessible-surface treatment produced a larger count than control.",
            "Under contact, treatment minus control was positive for escape; under "
            "blocked contact it was zero.",
            "With a nylon screen between mosquitoes and the treated sheet, escape "
            "matched the carrier control; removing the screen produced more escape "
            "than the contact control.",
            "Opening the treated-paper face raised the exit rate above control, while "
            "the screened face gave the same exit rate as carrier.",
            "The netted treatment compartment and solvent control had indistinguishable "
            "egress, but the touch-access compartment had greater treated egress.",
            "A perforated divider prevented touching and left treatment escape equal "
            "to vehicle; direct paper access increased the proportion leaving.",
            "When treated paper sat inside a mesh sleeve, departures matched control; "
            "outside the sleeve, physical contact led to extra departures.",
            "With tarsal access denied, treatment and carrier produced equivalent "
            "chamber exits; with tarsal access permitted, treatment produced more exits.",
            "The treated surface being available to the feet increased escape, whereas "
            "escape stayed level with vehicle when a screen blocked access.",
            "Occluding the paper left treated escape no different from control; "
            "exposing it for touch raised escape.",
            "Closed-face treatment equaled carrier for exits, while open-face treatment "
            "exceeded its control.",
            "Carrier-only and treated noncontact chambers had the same leaving "
            "probability; treated contact chambers had a larger leaving probability "
            "than controls.",
            "Barrier-side egress was equivalent for treatment and vehicle, whereas "
            "exposed-side egress was higher under treatment.",
            "The chance of leaving was unchanged from control with the source fenced "
            "off, but increased with direct access to the source.",
            "Departure counts overlapped between protected treatment and carrier; "
            "contact-enabled treatment generated more departures than its comparator.",
            "The exit hazard was equal for treatment and control behind a mesh window, "
            "but higher for treatment when the window was absent.",
            "The fraction leaving the treatment chamber matched vehicle when a fabric "
            "barrier intervened and exceeded control when mosquitoes could touch the paper.",
            "Treatment and carrier escape curves were superimposed in the isolated "
            "format; in the accessible format, the treated escape curve was above control.",
            "There was no divergence from carrier in barrier egress, only an excess "
            "over control once the paper was reachable.",
            "sheet behind netting treatment exits equaled carrier sheet reachable "
            "treatment exits were higher than control interpret the contrast",
            "contact available escape exceeded control barrier enclosed escape matched "
            "vehicle what effect is supported",
            "For escape, the treatment-control contrast was nil with a screen and above "
            "zero with paper access.",
            "The no-touch treated source behaved like its carrier-only comparator for "
            "egress, but touchable treatment increased egress.",
            "Escape from treatment behind mesh equaled untreated-paper control; with no "
            "mesh, treated-paper escape was greater than untreated-paper escape.",
            "The isolated treatment matched the reference chamber for exits, and the "
            "direct-access treatment surpassed its reference.",
            "Aedes aegypti females left treatment and carrier equally when the paper "
            "was shrouded, but left treated contact chambers more often than controls.",
            "Mosquito egress was control-like while the active sheet was covered and "
            "elevated after the cover was removed for contact.",
            "Keeping mesh between mosquitoes and paper gave equal treated and vehicle "
            "escape, whereas removing mesh increased treated escape.",
            "When the paper was behind a screen, escape in treatment matched the "
            "carrier arm; when paper was exposed, treatment produced more escape.",
            "The screened treatment-control pair showed no escape difference, but the "
            "unscreened pair showed a higher treated escape rate.",
            "Mosquitoes that could not reach the treated paper escaped as often as "
            "controls; mosquitoes allowed to reach it escaped more.",
            "Preventing paper contact removed the treatment-control difference in "
            "escape, while allowing paper contact produced a positive difference.",
            "The proportion escaping was the same for treatment and vehicle without "
            "contact, but greater for treatment when contact was allowed.",
            "Escape counts were similar between treated and control mesh chambers; "
            "treated contact chambers recorded more escapes than contact controls.",
            "Noncontact escape was not significantly different from control, while "
            "direct-contact escape was significantly higher under treatment.",
            "Against the carrier control, the barrier treatment showed unchanged "
            "escape; against the contact control, exposed treatment showed increased escape.",
            "For Aedes aegypti, escape stayed at control levels behind mesh and rose "
            "above control when treated paper could be touched.",
            "In the paired chambers, the noncontact treated-control contrast was absent "
            "and the contact treated-control contrast was positive for escape.",
            "In the mesh-screen condition, escape did not differ between the treated "
            "paper and solvent control. In the contact condition, treated chambers "
            "had more escape than controls. Does that support a contact effect?",
            "When females were separated from the treated paper by mesh, their escape "
            "matched the untreated group; after mesh removal allowed contact, treated "
            "escape increased.",
            "Contact exposure produced a higher escape rate than contact control, but "
            "the corresponding mesh-separated treatment and control rates were equal.",
            "With the screen in place, treatment did not change escape compared with "
            "vehicle; with the screen out, treatment increased escape.",
            "Escape remained at the control rate while mosquitoes could not access the "
            "paper, then rose above control once access was allowed.",
            "Females escaped as often as controls when touching was prevented, but more "
            "often than controls when they could touch the treated paper.",
            "The contact-free treated pair matched the carrier pair for escape, while "
            "the contact-permitted treated pair exceeded its control.",
            "Treated paper under mesh produced the same escape as control paper; "
            "uncovered treated paper produced higher escape than uncovered control paper.",
            "Treatment and control escape curves overlapped in the screened chambers "
            "but separated in the contact chambers, with treatment higher.",
            "We counted similar numbers of escapes in the treated and control barrier "
            "chambers, then more escapes in the treated direct-contact chamber.",
            "The escape percentage matched vehicle in the no-contact condition and "
            "exceeded control in the contact condition.",
            "Our paired assay showed no escape effect without paper contact and a "
            "higher treated escape response with paper contact.",
            "Carrier and treatment gave comparable escape with the screen present, "
            "whereas treatment exceeded carrier with the screen removed.",
            "The fraction escaping was unchanged by treatment behind mesh but higher "
            "under treatment in the contact setup.",
            "Cumulative 30-minute escape overlapped control in the mesh condition and "
            "was higher than control in the contact condition.",
            "Brief access to the treated paper increased escape above contact control, "
            "although escape stayed at vehicle levels when direct touch was blocked.",
            "Paper behind mesh yielded control-level escape; the same paper without "
            "mesh yielded excess treated escape.",
            "non contact treated equals control contact treated greater than control "
            "for escape what can we claim",
            "No distance-associated escape difference was detected, but the "
            "contact-permitted treatment produced a larger escape response than its "
            "control. How should that be interpreted?",
            "The non-contact treatment escape curve sat on the control escape curve, and "
            "the contact treatment escape curve sat above the contact control. How should the contact "
            "component be estimated?",
            "Escape rates were the same with mesh between the mosquitoes and paper, "
            "but treatment escape was higher after the mesh was removed.",
            "Escape did not change when treated paper could not be touched, but it "
            "increased when females were able to touch it.",
            "A mesh barrier blocked paper contact and treatment matched control; "
            "without the barrier, treated escape exceeded control.",
            "We found control-level escape before paper contact and increased escape "
            "only when contact was possible. Does this support contact rather than "
            "spatial repellency?",
            "Screened treated and control chambers had indistinguishable escape, while "
            "treated contact chambers had a higher escape rate than contact controls.",
            "With mesh covering the paper, treatment did not alter escape; after the "
            "mesh was taken away, treated escape rose above control.",
            "Escape remained equal to control when paper contact was impossible and "
            "became higher under treatment when paper contact was possible.",
            "The noncontact escape response matched vehicle, and the contact "
            "treatment escape response exceeded the paired control.",
            "screened treated escape equal control exposed treated escape greater "
            "control explain the finding",
            "In our Aedes assay, only the contact-permitted treatment increased escape; "
            "the contact-blocked treatment stayed at control.",
            "The paired chamber data showed no treatment effect on noncontact escape "
            "and a positive treatment effect on contact escape.",
            "The no-contact treatment gave the vehicle escape rate, whereas the "
            "contact treatment gave a higher rate than its control.",
            "Higher escape occurred in the treated contact group, with no "
            "treated-control escape difference in the mesh group.",
            "Treatment and control escape curves were together in the non-contact assay and "
            "the treatment escape curve was higher in the contact assay.",
            "Aedes females had no escape response to treatment across the mesh, but "
            "showed increased escape when the treated paper was accessible.",
            "In chambers fitted with mesh, escape did not change between treatment and "
            "control. In chambers allowing paper contact, treated mosquitoes escaped more.",
            "Blocking access to the paper gave the same escape in treatment and vehicle; "
            "permitting access gave higher escape in treatment than control.",
            "Cumulative escape was alike for treatment and control behind the screen "
            "and greater for treatment during direct paper exposure.",
            "In the paired comparison, no-contact treatment matched its control and "
            "contact treatment exceeded its control.",
            "mesh arm treated equals control contact arm treated higher escape how do "
            "we read this",
            "No-contact exposure produced no change in escape relative to vehicle; "
            "permitting paper contact increased escape relative to the contact control.",
            "The control comparison was null when mosquitoes were kept off the paper "
            "and positive when mosquitoes were allowed onto the paper, using escape "
            "as the outcome.",
            "There was no treatment-control separation in non-contact escape, while "
            "a clear treated excess appeared in contact escape.",
            "The no-touch treatment did not affect the 30-minute escape total, but "
            "treatment increased the total in the touch condition.",
            "Aedes escape was control-like with mesh protection and above control in "
            "the paper-contact condition.",
            "The number leaving was similar for treatment and control with mesh present "
            "and larger for treatment with mesh absent.",
            "After 30 minutes, the non-contact treatment-control difference was zero "
            "and the contact treatment-control difference was positive.",
            "In Aedes aegypti, preventing treated-paper contact removed the escape "
            "difference, while allowing contact produced higher treated escape.",
            "Treated and control escape were alike when mesh separated mosquitoes from "
            "paper; with no separation, the treated group escaped more.",
            "When the paper could not be reached, treatment and vehicle had the same "
            "escape; when it could be reached, treatment had more escape.",
            "When mesh kept mosquitoes off the treated paper, treated and control "
            "escape were equal; when contact was allowed, the treated group escaped more.",
            "The screened treatment had the control escape rate, but the contact "
            "treatment had a rate above its control.",
            "Treated contact escape exceeded control, whereas treated escape through "
            "the mesh remained equal to vehicle.",
            "Escape counts matched between treatment and control when touch was blocked "
            "and were higher for treatment when touch was allowed.",
            "The proportion that escaped was the same under treatment and control in "
            "the mesh assay and greater under treatment in the contact assay.",
            "mesh blocks touch treated escape equals control mesh removed treated "
            "escape above control interpret",
            "For Aedes aegypti, contact prevention gave control-like escape and paper "
            "contact gave greater treated escape.",
            "Treated and control chambers recorded equal escape counts with the paper "
            "covered and more treated escapes with the paper uncovered.",
            "At 30 minutes, treatment matched vehicle in the mesh chambers and "
            "exceeded control in the contact chambers.",
            "paper covered treated control equal escape paper exposed treated more "
            "escape interpret result",
            "Blocking paper access made treatment escape equal to vehicle, while giving "
            "access made treatment escape higher than control.",
            "At the 30-minute endpoint, noncontact treatment equaled vehicle and contact "
            "treatment was above control.",
            "The paired treatment effect on escape was null across the screen and "
            "positive during contact.",
            "screen between paper and mosquitoes treatment control same escape no "
            "screen treatment higher escape meaning",
            "Aedes aegypti had equal treated and control escape when separated from "
            "paper and higher treated escape when contact was possible.",
            "With the mesh screen in place, treated and control escape rates were equal; "
            "after the screen was removed, the treated escape rate was higher.",
            "The treatment did not affect escape when females could not touch the paper, "
            "but increased escape when touching was allowed.",
            "mesh on treatment control equal escape mesh off treatment higher escape "
            "explain",
            "Excluding paper contact left treatment escape equal to control; including "
            "paper contact increased escape in treatment.",
            "When mosquitoes were prevented from contacting the treated paper, treatment "
            "and control escape were the same; when contact was permitted, treatment "
            "escape increased.",
            "More escape occurred in treated contact chambers than controls, but "
            "treated screen chambers were no different from their controls.",
            "The escaped fraction matched control in the barrier condition and exceeded "
            "control in the contact condition.",
            "When access to treated paper was blocked, escape matched vehicle; when "
            "access was allowed, treated escape was higher than control.",
            "The no-contact treatment and control escape rates were comparable, whereas the "
            "contact treatment escape rate was greater than the contact control escape rate.",
            "In the screen condition, treated and control mosquitoes escaped at the "
            "same rate; in direct contact, the treated group escaped more.",
            "Making the treated paper unavailable for touch produced no escape "
            "difference from control, but making it available produced higher treated escape.",
            "Treated contact chambers showed more escape than control chambers, while "
            "the screen-separated treatment matched its control.",
            "The percentage leaving remained at control in the mesh chamber and "
            "increased in the treated contact chamber.",
            "The paired difference in escape was absent in the noncontact arm and "
            "positive in the contact arm.",
            "screen condition treated control same escape direct contact treated more "
            "escape meaning",
            "In Aedes aegypti, treatment matched vehicle when the paper could not be "
            "touched and exceeded control when it could be touched.",
            "With mesh preventing touch, escape was equal in treated and control "
            "chambers; without mesh, treated escape was greater.",
            "Treatment escape matched vehicle when the paper was inaccessible and "
            "exceeded control when paper access was allowed.",
            "The contact treatment increased escape compared with control, whereas "
            "the mesh treatment showed no difference.",
            "mesh prevents touch treatment equals control no mesh treatment higher "
            "escape interpret",
            "With a screen between the paper and mosquitoes, treated and control "
            "escape were similar; in an open chamber, treated escape was higher.",
            "Blocking the treated paper from contact produced control-level escape, "
            "while unblocking it produced an increase in treated escape.",
            "The treatment-control effect on escape was zero in the screened comparison "
            "and positive in the contact comparison.",
            "paper screened treatment control same escape paper open treatment higher "
            "escape interpret",
            "Escape was higher for treated paper than control when the paper was "
            "exposed; with mesh preventing contact, treated escape stayed at the "
            "control rate.",
            "When a barrier kept mosquitoes off the paper, escape matched control. "
            "When the same paper was reachable, escape was greater than control.",
            "Escape was unchanged by treatment while mesh separated females from the "
            "paper; after the mesh was removed, treatment increased escape.",
            "When treated paper was out of reach, escape matched control, whereas "
            "reachable treated paper produced more escape than control.",
            "The treated contact chamber had an escape excess, while the treated screen "
            "chamber stayed at the vehicle rate.",
            "The 30-minute treatment effect on escape was zero in the screened pair "
            "and positive in the contact pair.",
            "Blocking contact with mesh left the treated escape rate unchanged from "
            "control; allowing contact raised treated escape above control.",
            "In the barrier pair, treatment did not affect escape. In the contact pair, "
            "treatment increased escape compared with the paired control.",
            "A larger escape response occurred in the treated contact chamber, while "
            "the mesh-separated treated chamber remained at the control response.",
            "Treated and control escape were alike when a screen stopped contact, and "
            "treated escape increased when the paper was available to touch. Is this "
            "contact-associated?",
            "Aedes treated and control groups did not differ in escape when a screen "
            "separated them from the paper; treated escape exceeded control when no "
            "screen separated them.",
            "With paper touch prevented, treated females left at the control frequency. "
            "With touch allowed, they left more often.",
            "The no-contact treatment-control comparison was flat, but the contact "
            "comparison showed excess escape for treatment.",
            "Screened treatment and carrier escape totals were alike; uncovered "
            "treatment escape total was above uncovered control.",
            "Only contact access separated treatment from control: escape matched "
            "without access and increased with access.",
            "This paired Aedes result has equal no-contact escape and higher contact "
            "escape. What can and cannot be concluded?",
            "The vehicle and treatment groups had equal exit rates with mesh in place; "
            "treatment produced more exits than control when direct contact was available.",
            "When mesh isolated the paper, treated escape equaled carrier; when "
            "mosquitoes had access to the paper, treated escape exceeded carrier.",
            "The paired result was a zero treated-control difference for barrier "
            "escape and a positive difference for contact escape.",
            "In Aedes, the control and treated escape curves coincided without surface "
            "contact, but the treated escape curve was higher when surface contact occurred.",
            "Contact-capable treatment had increased escape relative to contact control; "
            "contact-excluded treatment was equal to its control.",
            "Shielding the treated paper gave carrier-level escape, while exposing it "
            "gave higher treated escape than the exposed control.",
            "The paired escape comparison was null when contact was excluded and showed "
            "a treated increase versus paired control when contact access was provided.",
            "barrier present treated escape equals vehicle barrier absent treated escape "
            "exceeds control interpret the aedes result",
            "Aedes females escaped equally from treated and control chambers when mesh "
            "kept them off the paper; they escaped more from treatment than control "
            "when the mesh was absent.",
            "Treated and control escape totals overlapped in the screened test, whereas "
            "treated totals were higher in the contact test.",
            "Treatment raised escape over control during direct paper exposure; "
            "treatment had no escape effect relative to control when exposure was blocked.",
            "Making the paper inaccessible left treated escape at the vehicle value; "
            "making it reachable increased treated escape above control.",
            "Aedes showed no treatment effect on escape before contact and a treated "
            "increase after contact was permitted. Does this identify a contact response?",
            "The screened treated group had the same probability of leaving as the "
            "screened control; the contact treated group had a greater leaving "
            "probability than its control.",
            "Thirty-minute cumulative escape counts did not separate treatment from "
            "control in the barrier format and were higher for treatment in the contact "
            "format.",
            "Covering the paper kept treated escape equal to vehicle; uncovering it made "
            "treated escape greater than control.",
            "aedes screened escape matches control exposed paper escape increases over "
            "control what is the interpretation",
            "In Aedes, treated and control groups had indistinguishable escape under "
            "mesh separation, while the treated contact group exceeded its control.",
            "Blocking access to treated paper removed the escape difference between "
            "treatment and control; granting access generated higher treated escape "
            "than control.",
            "The contact treatment produced a larger escape response than contact "
            "control; the separated treatment produced the same response as separated "
            "control.",
            "Treatment did not change the proportion escaping relative to control with "
            "the barrier present and increased that proportion above control when the "
            "barrier was absent.",
            "Our Aedes experiment found no escape change with contact prevented and "
            "greater treated escape with contact permitted. Is this a contact-associated "
            "pattern?",
            "Keeping treated paper out of reach produced control-level escape; putting "
            "it within reach increased treated escape over control.",
            "In the Aedes assay, blocking paper contact left the escape proportion "
            "indistinguishable from control, whereas allowing contact produced a higher "
            "escape proportion. How would you read these findings?",
            "When Aedes could not reach the treated surface, treatment and solvent "
            "control gave comparable exit counts; permitting surface contact increased "
            "exits over solvent control. How should this be interpreted?",
            "Aedes escape matched the control with a barrier between insects and treated "
            "paper, but exceeded control once that barrier was removed and contact was "
            "possible. What does the contrast support?",
            "In Aedes trials, treatment behind the contact screen gave an escape curve "
            "that overlapped solvent control; once the screen was absent and paper could "
            "be contacted, the treatment escape curve was higher than control. What is the "
            "result pattern?",
            "Aedes escape did not differ between repellent and control when mesh stopped "
            "touching, but it was greater for repellent than control in the open-contact "
            "condition. How should these observations be interpreted?",
            "Separating Aedes from dosed paper left treated escape at the control "
            "baseline, while giving the insects access to the paper raised the number "
            "escaping above baseline. What does this finding support?",
            "Screened exposure caused no detectable change in Aedes escape compared with "
            "control, yet unscreened exposure increased escape compared with control. "
            "What can be concluded?",
            "Aedes exit probability was comparable for treatment and control when paper "
            "was shielded, and significantly larger under treatment when paper contact "
            "was enabled. How should this result be stated?",
            "Preventing Aedes from touching the dosed substrate produced a null escape "
            "contrast; allowing touch produced more treatment escapes than control "
            "escapes. What does the paired pattern indicate?",
            "Aedes left the no-access treatment chamber at the same frequency as the "
            "control chamber. When access to the treated sheet was allowed, the leaving "
            "frequency surpassed control. What does this pattern show?",
            "With a screen denying physical contact, Aedes treatment escape was "
            "statistically equivalent to solvent escape; after contact was permitted, "
            "the treatment caused a larger escape response than solvent. How should we "
            "read the result?",
            "There was no treatment effect on Aedes egress in the separated condition, "
            "followed by a positive treatment effect on egress in the touching "
            "condition. What does that mean?",
            "For the Aedes escape endpoint, treatment equaled control in the "
            "indirect-exposure arm and exceeded control in the direct-exposure arm. "
            "What conclusion fits?",
            "In the Aedes escape assay, shielding the impregnated strip yielded "
            "treatment values indistinguishable from vehicle, whereas exposing the "
            "strip yielded treatment values above vehicle. How should this be "
            "interpreted?",
            "When a barrier kept Aedes off the test paper, the fraction departing was "
            "the same for test and control. Once direct access was provided, a larger "
            "fraction departed from test than control. What does that indicate?",
            "Aedes egress showed a null treatment contrast in the protected-paper arm "
            "and an upward treatment contrast in the paper-contact arm. How would you "
            "summarize the result?",
            "The treatment did not change Aedes escape relative to control under "
            "non-touch exposure, but increased it relative to control under touch "
            "exposure. What interpretation fits?",
            "Aedes escape curves for treated and control chambers coincided with mesh in "
            "place; with mosquitoes free to reach the paper, the treated-chamber curve "
            "lay above control. What does the comparison show?",
            "For Aedes, denying substrate contact erased the treatment-control "
            "difference in escape; granting contact revealed higher escape under "
            "treatment. What conclusion is justified?",
            "Among Aedes replicates, no-contact treatment and control returned "
            "comparable escape counts, whereas contact treatment returned a surplus of "
            "escapees over control. How should this pattern be described?",
            "The Aedes response was treatment approximately equal to control for escape "
            "when surface access was blocked and treatment greater than control when "
            "surface access was open. What can be inferred?",
            "For Aedes, a nylon partition between mosquitoes and the treated panel left "
            "escape indistinguishable from carrier, while removing the partition and "
            "permitting contact increased escape over carrier. What does this result "
            "mean?",
            "Aedes departure from the treatment side was at the control level when the "
            "sample was out of reach; departure was above control when the sample was "
            "within reach. How should this be interpreted?",
            "The separated-paper Aedes run yielded no difference in escaped numbers "
            "between chemical and blank. The contact-paper run yielded more escaped "
            "mosquitoes for chemical than blank. What is the interpretation?",
            "Under distance-only exposure, Aedes treatment had a zero escape effect "
            "versus control. Under tactile exposure, it had a positive escape effect. "
            "What does this pattern support?",
            "Aedes escape proportions for treatment and solvent were alike with the "
            "barrier closed, then diverged in favor of greater treatment escape when the "
            "barrier was opened for contact. How should the result be described?",
            "Holding the treated liner beyond Aedes reach did not alter exits relative "
            "to control; allowing insects to reach the liner increased exits from the "
            "treated arm relative to control. What can we conclude?",
            "Aedes showed baseline-equivalent escape from a physically separated "
            "treatment and above-baseline escape from a contact-accessible treatment. "
            "What inference follows?",
            "In Aedes cages, escape from chemically treated versus vehicle paper did "
            "not differ when a guard prevented contact; with the guard removed, chemical "
            "treatment yielded a higher escape rate. How should this be interpreted?",
            "Aedes exited treated and reference compartments equally under remote "
            "presentation, then exited the treated compartment more often under contact "
            "presentation. How should we explain the contrast?",
            "Placing the treated card behind a guard produced no added Aedes escape "
            "relative to the blank card; making the card touchable produced added escape. "
            "What does the result indicate?",
            "The chemical-control contrast for Aedes escape was absent when surface "
            "access was denied and positive when surface access was granted. How should "
            "this be read?",
            "Treatment surpassed control for Aedes escaping during paper contact, "
            "whereas treatment tied control when paper contact was blocked. What can be "
            "inferred from the pair?",
            "Aedes had the same escape response to treatment and control through a guard "
            "but a stronger treatment escape response with no guard what can this result "
            "tell us",
            "The protected exposure produced no Aedes escape difference between "
            "formulation and vehicle; the unprotected exposure produced an increase for "
            "formulation over vehicle. How should this finding be read?",
            "For Aedes escape, the contrast was null when contact was impossible and "
            "positive when contact was possible. What interpretation is appropriate?",
            "Aedes leaving was unchanged versus control while treated paper was "
            "physically separated, then increased versus control once separation was "
            "removed. What conclusion follows?",
            "With mosquitoes unable to touch the insert, treated and control Aedes groups "
            "yielded the same escape proportion. With touch allowed, the treated group "
            "yielded a larger proportion. How should we describe the pair?",
            "A barrier made the Aedes treatment escape response look like control; "
            "access to the treated surface made escape exceed control. What does this "
            "pattern mean?",
            "In no-contact replicates, Aedes treatment did not add escapes over solvent. "
            "In contact replicates, treatment added escapes over solvent. What can be "
            "inferred?",
            "For Aedes escape the covered sample matched the control and the uncovered "
            "touchable sample was higher than the control how should this pattern be stated",
            "Aedes escape remained at vehicle levels when the dosed surface could not be "
            "touched; it increased above vehicle when mosquitoes could touch the surface. "
            "What inference is warranted?",
            "Aedes did not leave the treated chamber more often than control with a mesh "
            "barrier, but did leave more often with direct paper access. What can we "
            "conclude?",
            "With the formulation isolated from Aedes, treatment and control escape rates "
            "were equivalent. With the formulation accessible, the treatment escape rate "
            "exceeded control. What does the contrast mean?",
            "Shielding the dose yielded no excess Aedes escapes over blank, while exposing "
            "it for touch yielded a clear excess. How should we interpret the finding?",
            "Directly exposed Aedes escaped more under treatment than control; remotely "
            "exposed Aedes showed no treatment-control difference. What is the appropriate "
            "interpretation?",
            "When the treated strip was inaccessible, Aedes exited at the same rate as "
            "control; when it was accessible, they exited at a higher rate than control. "
            "What does this result indicate?",
            "The non-touch Aedes condition gave a treatment-control escape ratio near one, "
            "whereas the touch condition gave a ratio above one. How should we read this "
            "pattern?",
            "For Aedes, no additional escape was associated with treatment across the "
            "barrier, while additional escape was associated with treatment after barrier "
            "removal. What conclusion is supported?",
            "Aedes escape under separated treatment was statistically similar to the blank, "
            "then exceeded the blank under direct exposure. What does the contrast mean?",
            "The shielded Aedes assay had equivalent treatment and control escape "
            "percentages; the contact-enabled assay had a larger percentage for treatment. "
            "What interpretation fits?",
            "In the paired experiment, Aedes showed no treatment effect on escape if "
            "touching was prevented and a positive treatment effect if touching was allowed. "
            "What can be inferred?",
            "Under direct access the formulation produced more Aedes escape than vehicle, "
            "but under screened access it produced the same escape as vehicle. What "
            "conclusion follows?",
            "For Aedes the test paper caused no extra escape behind mesh and caused extra "
            "escape over control when mosquitoes could reach it what does that mean",
            "When dosed paper was enclosed, the number of escaping Aedes matched the vehicle "
            "count; when the enclosure was opened for contact, the treated count exceeded "
            "vehicle. What conclusion fits?",
            "No evidence of extra Aedes escape appeared during distant exposure, but clear "
            "extra escape over control appeared with surface access. How should we read "
            "this result?",
            "The Aedes treatment-control escape contrast was zero with a physical screen "
            "and above zero without the screen. What can be inferred?",
            "Contact-prohibited Aedes trials returned equivalent escape for chemical and "
            "carrier. Contact-permitted trials returned higher escape for chemical. What is "
            "the appropriate interpretation?",
            "Aedes escaped from treatment at the baseline control rate when paper remained "
            "untouchable, then above baseline when the paper became touchable. What does "
            "the finding support?",
            "The formulation failed to raise Aedes escape under barrier separation but "
            "raised escape under direct contact. How should this outcome be described?",
            "With Aedes unable to reach the sample treatment escape equaled vehicle escape "
            "with reach allowed treatment escape exceeded vehicle escape how do I interpret "
            "this",
            "Aedes escape did not rise above control in the physically isolated condition, "
            "but did rise above control in the direct-access condition. What result does "
            "this represent?",
            "The treatment-control comparison for Aedes escape was nonsignificant with "
            "contact excluded and showed a significant treatment increase with contact "
            "included. How should the pattern be described?",
            "Aedes left treated and control chambers in similar numbers when the sample was "
            "fenced off; more left the treated chamber once touching was allowed. What does "
            "this finding mean?",
            "Remote exposure gave an Aedes escape response matching the solvent blank. "
            "Contact exposure gave an escape response exceeding the solvent blank. What "
            "conclusion is appropriate?",
            "With the paper behind a separator there was no Aedes escape advantage for "
            "treatment; with the paper exposed there was a treatment escape advantage. How "
            "should this be read?",
            "Aedes escaped no more from treatment than control with paper blocked but escaped "
            "more from treatment with paper available to touch what is the interpretation",
            "In the Aedes assay, escape was the same as control when mosquitoes could not "
            "contact the treated paper, but higher than control when contact was allowed. "
            "How should we interpret this result?",
            "We saw no increase in Aedes escape across the barrier, but we did see an "
            "increase after mosquitoes touched the treated surface. How should we interpret "
            "that?",
            "The no-contact Aedes arm was negative for an escape effect, while the contact "
            "arm showed increased escape. What does this pattern mean?",
            "We observed control-like Aedes escape without touching and greater escape after "
            "direct contact with treated paper. What does the result indicate?",
            "Preventing contact removed any treatment effect on Aedes escape; allowing "
            "contact produced more escape under treatment than control. What can we "
            "conclude?",
            "The treatment increased Aedes escape in the contact assay, but not in the "
            "matched no-contact assay. What interpretation is appropriate?",
            "Aedes did not escape more than control behind the screen but did escape more "
            "than control after the screen was removed what is the interpretation",
            "In the no-contact test, Aedes treatment escape stayed at baseline. In the "
            "contact test, treatment escape rose above baseline. What does this pattern "
            "show?",
            "Aedes showed similar escape from treatment and solvent when the paper was "
            "screened, but more escape from treatment when the paper was unscreened. What "
            "conclusion follows?",
            "Aedes treatment and control escape were equal when paper was out of reach and "
            "treatment escape was higher when paper was in reach how should I interpret it",
            "In Aedes, treatment did not increase escape over control when contact with the "
            "paper was prevented, but treatment did increase escape over control when "
            "contact was permitted. How should this result be interpreted?",
            "The Aedes no-contact arm showed no treatment-control increase in escape; the "
            "contact arm showed higher treatment escape than control. What does this "
            "pattern indicate?",
            "Aedes treatment escape was not above vehicle escape in the noncontact setup, "
            "whereas it was above vehicle escape in the contact setup. How should this be "
            "interpreted?",
            "Aedes escape was not increased by treatment relative to control when paper "
            "contact was blocked, but was increased relative to control when contact was "
            "allowed. What does this result mean?",
            "In the screened condition, treatment produced no increase in Aedes escape over "
            "vehicle; in the open-contact condition, treatment produced a higher escape "
            "response than vehicle. What conclusion follows?",
            "Aedes treatment escape did not exceed control without contact and did exceed "
            "control with contact how should this observed result be interpreted",
            "In the Aedes trials, treatment did not raise escape above control in the "
            "no-contact condition, whereas it raised escape above control in the contact "
            "condition. How should this be interpreted?",
            "Aedes treatment and control escape rates were identical in the separated "
            "setup, and the treatment escape rate was higher than control in the "
            "direct-contact setup. What interpretation fits?",
            "Aedes escape showed no treatment increase versus control without contact and a "
            "treatment increase versus control with contact what does this mean",
            "There was no treatment-related increase over control in Aedes escape without "
            "contact, while there was a treatment-related increase over control with "
            "contact. How should we describe the result?",
            "Treatment escape was higher than control for contact-exposed Aedes, whereas it "
            "was not higher than control for no-contact Aedes. What does this pair show?",
            "Aedes showed no treatment over control increase in escape without touching and "
            "showed a treatment over control increase with touching how should this be "
            "interpreted",
            "In Aedes, the treatment group did not show more escape than control without "
            "contact, but did show more escape than control with contact. How should this "
            "be interpreted?",
            "When a barrier prevented touching, Aedes escape under treatment was no higher "
            "than control. When touching was allowed, escape under treatment was higher than "
            "control. What conclusion follows?",
            "Aedes treatment escape matched control when insects were separated from the "
            "surface and increased above control when insects could touch the surface. What "
            "does the finding mean?",
            "For Aedes treatment produced no escape increase over control in the mesh arm "
            "and produced an escape increase over control in the contact arm what does this "
            "show",
            "In Aedes assays, treatment escape was no greater than control when insects were "
            "kept off the treated paper, but was greater than control when they contacted "
            "the paper. How should this be interpreted?",
            "Aedes showed no treatment-versus-control increase in escape through mesh, "
            "followed by an increase for treatment versus control during direct contact. How "
            "should we describe the pattern?",
            "When treated paper could not be touched, treatment did not elevate Aedes escape "
            "over vehicle; when it was touched, treatment elevated escape over vehicle. "
            "What does the finding mean?",
            "For Aedes escape treatment equaled control without direct paper contact and "
            "treatment was greater than control with direct paper contact how should this be "
            "interpreted",
            "Aedes escape from treatment matched control without paper contact and exceeded "
            "control with paper contact. What can we infer?",
            "For Aedes, treatment did not increase escape relative to control in the absence "
            "of contact, but increased escape relative to control when paper contact "
            "occurred. How should this be interpreted?",
            "Aedes treatment produced no extra escape beyond control when paper was "
            "unreachable and produced extra escape beyond control when paper was reachable "
            "how should I interpret this",
            "The screened Aedes condition showed no increase for treatment over control, "
            "while the contact condition showed more escape for treatment than control. How "
            "should we describe the pattern?",
            "Aedes treatment did not produce more escape than control without contact, and "
            "did produce more escape than control with contact. What can we infer?",
            "Aedes treated and control groups escaped equally with mesh separating them from "
            "the paper, but the treated group escaped more with direct paper contact. What "
            "conclusion follows?",
            "The treated Aedes group had control-level escape without touching the paper and "
            "above-control escape while touching it. How should this be interpreted?",
            "Blocking treated-paper access left Aedes aegypti treatment escape no greater "
            "than control, but allowing access produced higher treatment escape than "
            "control. What is the appropriate interpretation?",
            "When the treated source was inaccessible, Aedes aegypti escape under treatment "
            "did not exceed control; when the source was reachable, treatment escape exceeded "
            "control. Which response is indicated?",
            "Separating Aedes aegypti from the treated surface produced no treatment-control "
            "increase in escape, but allowing surface contact produced an increased treatment "
            "escape relative to control. How do we report this pattern?",
            "When Aedes aegypti were kept away from the treated paper, treatment did not "
            "increase escape relative to control; when they could contact it, treatment "
            "increased escape relative to control. What is supported?",
            "Aedes aegypti showed no treatment-control elevation in escape across the barrier "
            "and a treatment-control elevation in escape after direct paper contact. How "
            "should this observed result be reported?",
            "Under paper isolation, Aedes aegypti treatment escape stayed at the control rate; "
            "under direct paper exposure, treatment escape rose above the control rate. Which "
            "response does this support?",
            "Without direct access to the paper, Aedes aegypti treatment generated no more "
            "escape than control; with direct access, treatment generated more escape than "
            "control. What is supported by these observations?",
            "In contact-free Aedes aegypti chambers, the treated group did not show higher "
            "escape than control; in contact chambers, treated escape was higher than control. "
            "How should this be interpreted?",
            "The Aedes aegypti no-contact escape contrast did not favor treatment over control, "
            "whereas the contact escape contrast favored treatment with more escape than control. "
            "What does that indicate?",
            "The treatment-control relation for Aedes aegypti escape was no increase under "
            "no-contact exposure and an increase under contact exposure. What can and cannot "
            "be claimed?",
            "In the Aedes aegypti no-contact portion, treated and control escape proportions "
            "were alike; in the contact portion, treated escape exceeded control. What "
            "interpretation follows?",
            "Treatment added no Aedes aegypti escape beyond control without contact, but added "
            "escape beyond control when contact was available. What does the result indicate?",
            "The paired Aedes aegypti readout showed no treatment-control increase in escape "
            "for no-contact exposure and a higher treatment escape than control for contact "
            "exposure. What is supported?",
            "The treated Aedes aegypti group's escape probability matched control in the "
            "no-contact assay and surpassed control in the contact assay. How should the "
            "contrast be read?",
            "In the contact-barred Aedes aegypti assay, treatment did not produce a larger "
            "escaped fraction than control; in the contact-access assay, the treated fraction "
            "was larger than control. What does this support?",
            "The study observed no treatment-control rise in Aedes aegypti escape under "
            "no-contact exposure and a treatment-control rise under contact exposure, with "
            "treatment higher. What can and cannot be concluded?",
            "Aedes aegypti treatment left escape unchanged versus control when the paper was "
            "separated by mesh, but increased escape versus control when contact with paper "
            "was possible. How should this be interpreted?",
            "There was no treatment-related excess in Aedes aegypti escape without contact "
            "and there was a treatment-related excess over control with contact. What "
            "conclusion is supported?",
            "The treated-control gap in Aedes aegypti escape was absent without contact and "
            "present with contact, where treated escape was higher. Which response fits "
            "these data?",
            "Treatment failed to increase Aedes aegypti escape relative to control when contact "
            "was excluded, but succeeded in increasing escape relative to control when contact "
            "was included. What does the pattern indicate?",
            "Only the contact-present Aedes aegypti condition showed treatment escape above "
            "control; the contact-absent condition showed no treatment-control increase. How "
            "should we read this result?",
            "A treatment-specific increase in Aedes aegypti escape appeared with contact but "
            "not without contact, where treatment remained at control. What is supported?",
            "No Aedes aegypti treatment effect on escape was seen in the separated-paper "
            "condition, while increased treatment escape over control was seen in the contact "
            "condition. What can be concluded?",
            "In summary, Aedes aegypti treatment showed no escape increase over control without "
            "contact and showed an escape increase over control with contact. What can and "
            "cannot be claimed?",
            "When direct touch was excluded, Aedes aegypti treatment did not increase escape "
            "relative to control; when touch was permitted, treatment increased escape relative "
            "to control. What conclusion follows?",
            "Escape under treatment and control was equivalent for Aedes aegypti with the "
            "surface screened off, while treatment escape was greater than control with the "
            "surface exposed. What can be inferred?",
            "There was no evidence of higher treated Aedes aegypti escape than control without "
            "contact, but treated escape was higher than control with contact. What is the "
            "appropriate interpretation?",
            "No-contact Aedes aegypti results had no upward shift in treatment escape versus "
            "control, while contact results had an upward shift with treatment above control. "
            "How should this be read?",
            "Direct contact gave higher Aedes aegypti treatment escape than control, but "
            "preventing direct contact gave no treatment-control increase in escape. What can "
            "be inferred?",
            "Treatment was unable to raise Aedes aegypti escape above control in the no-contact "
            "arm but raised it above control in the contact arm. How should this be reported?",
            "Across mesh and no-mesh Aedes aegypti tests, treatment escape matched control with "
            "mesh and exceeded control with contact allowed. What conclusion is justified?",
            "Escape under no-touch exposure was not higher for treated Aedes aegypti than "
            "controls, while escape under touch exposure was higher for treated females than "
            "controls. What is supported?",
            "In the Aedes aegypti ER assay, treatment did not raise escape relative to control "
            "behind the barrier; with paper contact available, treatment raised escape above "
            "control. Is this a contact-associated result?",
            "Aedes aegypti escape under no-contact treatment was not above the paired control, "
            "but escape under contact treatment was above the paired control. How should that "
            "finding be classified?",
            "The Aedes aegypti no-touch treatment arm stayed even with control for escape, and "
            "the touch-enabled treatment arm exceeded control for escape. How should this be "
            "interpreted?",
            "Aedes aegypti had no treatment-control escape increase in screened chambers, "
            "followed by greater treatment than control escape in chambers permitting contact. "
            "What is supported?",
            "Aedes aegypti showed matching treatment and control escape in the contact-blocked "
            "condition, alongside higher treatment escape in the contact-allowed condition. "
            "Which interpretation is justified?",
            "Escape did not rise above control for treated Aedes aegypti without surface access, "
            "whereas it did rise above control with surface access. What does the combined "
            "result indicate?",
            "For Aedes aegypti, contact prevention yielded no treatment-control difference in "
            "escape, and contact permission yielded a larger treated escape response than "
            "control. What is supported?",
            "The Aedes aegypti treatment-control difference in escape was zero with a contact "
            "barrier and positive without the barrier. What result does that support?",
            "For Aedes aegypti, treated escape did not exceed control when direct access was "
            "denied, whereas treated escape exceeded control when direct access was granted. "
            "What can we infer?",
            "With the treated surface shielded, Aedes aegypti treatment escape remained at "
            "control; with the surface unshielded for contact, treatment escape rose above "
            "control. What does the result mean?",
            "The screened Aedes aegypti treatment group had the same escape as its control, "
            "while the contact-capable treatment group had more escape than its control. What "
            "conclusion is warranted?",
            "Aedes aegypti escape was unchanged by treatment relative to control before surface "
            "contact was possible, but higher under treatment once surface contact was possible. "
            "How should this pattern be classified?",
            "In Aedes aegypti, denying surface contact gave no treatment-related escape increase, "
            "while permitting surface contact gave higher treatment escape than control. Which "
            "effect is supported?",
            "Our Aedes aegypti comparison showed a zero treatment-control escape contrast in the "
            "separated arm and a positive contrast in the touching arm. What is the "
            "interpretation?",
            "Treatment and control Aedes aegypti escaped equally when contact was unavailable; "
            "treatment produced more escape than control when contact was available. Is the "
            "signal spatial or contact-associated?",
            "Aedes aegypti treatment escape showed no increase over control in the arm with the "
            "surface inaccessible and an increase over control in the arm with the surface "
            "accessible. How should this be interpreted?",
            "Treatment did not raise Aedes aegypti escape in the non-touch arm relative to "
            "control, but did raise it in the touch arm. What does this support?",
            "Aedes aegypti escaped at equal rates under treatment and control when separated "
            "from residue, then at a higher rate under treatment than control when residue "
            "contact was possible. What can we infer?",
            "For Aedes aegypti, treatment and control produced the same escape when a mesh kept "
            "mosquitoes from the surface, but treatment produced greater escape than control "
            "when the surface could be touched. What does this support?",
            "The escape response of treated Aedes aegypti matched control with physical access "
            "blocked, then exceeded control with physical access allowed. Is this evidence for "
            "contact-associated activity?",
            "Our Aedes aegypti data showed a null treatment effect on escape while contact was "
            "impossible and a positive treatment effect while contact was possible. Which "
            "interpretation follows?",
            "No treatment-control increase in Aedes aegypti escape occurred with surface access "
            "closed, whereas a treatment-control increase occurred with surface access open. "
            "What does that indicate?",
            "Aedes aegypti escaped equally under treatment and control when contact with residue "
            "was prevented, but escaped more under treatment when residue contact was allowed. "
            "Is the effect contact-associated?",
            "The treatment-control escape comparison in Aedes aegypti was flat when paper contact "
            "could not occur and positive when paper contact could occur. Which response is "
            "supported?",
            "In our Aedes aegypti trial, the contact-restricted treatment had the control escape "
            "rate, while the contact-unrestricted treatment had a higher escape rate than "
            "control. What is the conclusion?",
            "For Aedes aegypti, treated escape matched control while contact with the test surface "
            "was blocked, then exceeded control when access to the test surface was opened. What "
            "does this result support?",
            "In Aedes aegypti, contact exclusion left treatment escape unchanged from control, "
            "whereas contact inclusion raised treatment escape above control. Which effect is "
            "present?",
            "Aedes aegypti had equal treatment and control escape under restricted paper access "
            "and higher treatment than control escape under unrestricted paper access. How "
            "should this be reported?",
            "With direct touch ruled out, Aedes aegypti treatment produced no excess escape; with "
            "direct touch enabled, treatment produced excess escape over control. What is "
            "supported?",
            "The Aedes aegypti treatment-control escape contrast was absent for inaccessible "
            "residue and positive for accessible residue. What may we claim?",
            "For Aedes aegypti, there was no treated escape increase in the no-access condition "
            "and a treated escape increase over control in the access condition. What is "
            "supported?",
            "In Aedes aegypti, treated and control groups escaped equally from contact-blocking "
            "chambers, while treated groups escaped more than controls from contact-permitting "
            "chambers. What can we conclude?",
            "Our Aedes aegypti results showed control-level escape under treatment when direct "
            "surface access was absent and above-control escape when direct surface access was "
            "present. Is this contact-associated?",
            "Keeping Aedes aegypti away from treated residue produced no extra treatment escape; "
            "letting them reach the residue produced more treatment escape than control. Which "
            "interpretation follows?",
            "Aedes aegypti had no treatment-related escape elevation with the contact barrier "
            "installed and a clear elevation with the barrier removed. How should this pattern "
            "be classified?",
            "The separated Aedes aegypti treatment arm matched its control for escape, whereas "
            "the touching treatment arm exceeded its control. What is justified?",
            "Treatment failed to increase Aedes aegypti escape when surface contact was "
            "disallowed, yet increased escape versus control when surface contact was allowed. "
            "What does that indicate?",
            "The Aedes aegypti escape contrast between treatment and control was zero when access "
            "to residue was denied and positive when access was granted. What does that mean?",
            "Under no-contact exposure, Aedes aegypti treatment did not elevate escape over "
            "control; under contact exposure, it did. Which result follows?",
            "Aedes aegypti showed equal escape for treatment and control behind the contact "
            "barrier and higher treated escape after contact access was restored. What can be "
            "claimed?",
            "When the test surface was off limits, treated Aedes aegypti did not escape more than "
            "controls; when it was available for contact, they did. How should this be reported?",
            "Aedes aegypti treatment escape had no elevation in the residue-separated condition "
            "but a positive elevation over control in the residue-accessible condition. What "
            "does this support?",
            "For Aedes aegypti, treatment escape was no different from control in chambers "
            "preventing touch, but was higher than control in chambers permitting touch. What "
            "is the supported interpretation?",
            "The Aedes aegypti treatment-control escape response was neutral when the paper was "
            "out of reach and positive when the paper was reachable. How should this be "
            "classified?",
            "Aedes aegypti treated groups escaped at the same frequency as controls with residue "
            "isolated, whereas treated groups escaped at a greater frequency with residue "
            "accessible. What can be concluded?",
            "When access to treated paper was shut, Aedes aegypti treatment escape stayed level "
            "with control; when access was opened, it rose above control. What is supported?",
            "Treatment caused no escape elevation in Aedes aegypti under physical separation, "
            "but caused escape above control under direct paper access. Which effect follows?",
            "For Aedes aegypti, the no-surface-contact arm showed equal treated and control "
            "escape, and the surface-contact arm showed greater treated escape. What does that "
            "support?",
            "The Aedes aegypti treatment produced the same escape as control with residue "
            "screened off, but more escape than control with residue exposed for contact. What "
            "can be concluded?",
            "In Aedes aegypti, blocking touch removed any treatment-control escape increase; "
            "allowing touch produced an increase under treatment. Is that contact-associated?",
            "Our Aedes aegypti comparison showed no escape gain over control in the access-blocked "
            "condition and an escape gain in the access-allowed condition. Which interpretation "
            "follows?",
            "When paper contact was unavailable, treated Aedes aegypti escaped at the control "
            "rate; when it was available, treated mosquitoes escaped at a higher rate. What is "
            "supported?",
            "Aedes aegypti had matching treatment and control escape with the contact surface "
            "closed off and higher treated escape with it open to contact. How should this be "
            "classified?",
            "No treatment-related escape increase appeared for Aedes aegypti under physical "
            "isolation from the paper, but one appeared under physical contact. What does the "
            "pattern mean?",
            "Aedes aegypti treatment did not exceed control for escape without residue access "
            "and did exceed control with residue access. Is the response contact-associated?",
            "For Aedes aegypti, treated escape remained at the control value when the paper "
            "could not be contacted, but exceeded control when paper contact was possible. "
            "What does this support?",
            "Aedes aegypti showed no treatment-associated increase in escape in the "
            "contact-excluded setup and higher treated escape in the contact-included setup. "
            "How should this be interpreted?",
            "Our Aedes aegypti data had treated escape equal to control with residue out of "
            "reach and above control with residue within reach. What can be inferred?",
            "Blocking Aedes aegypti from the paper produced no excess treatment escape, whereas "
            "allowing them onto the paper produced more escape than control. Which "
            "interpretation is justified?",
            "Aedes aegypti treatment escape was neutral versus control under surface separation "
            "and elevated under surface contact. How should this pattern be reported?",
            "When contact was not allowed, Aedes aegypti did not escape more from treatment "
            "than control; when contact was allowed, they did. What does that indicate?",
            "Aedes aegypti had a zero treatment contrast for escape in the screened-off "
            "condition and a greater-than-zero contrast in the exposed condition. What may "
            "we claim?",
            "In Aedes aegypti, preventing contact yielded no extra treatment escape, whereas "
            "enabling contact yielded more treatment escape than control. Is that "
            "contact-associated?",
            "When the residue was screened away, Aedes aegypti treatment escape equaled "
            "control; when residue contact was available, it was higher. What does the "
            "result mean?",
            "Aedes aegypti treatment produced control-level escape with access prohibited "
            "and above-control escape with access permitted. Which interpretation follows?",
            "Aedes aegypti egress under treatment was no higher than control egress when "
            "residue was inaccessible, but treatment egress was higher than control egress "
            "when residue was accessible. How should this be reported?",
            "In the screened Aedes aegypti pair, treatment escape equaled control escape; "
            "in the direct-contact pair, treatment escape rose above control escape. Which "
            "interpretation is justified?",
            "The Aedes aegypti exit probability under treatment was no higher than the "
            "control exit probability when contact was blocked, then exceeded control when "
            "contact was possible. What does this show?",
            "Among Aedes aegypti, treatment caused no increase over control in leaving when "
            "the surface could not be contacted, whereas leaving under treatment was greater "
            "than control when surface contact was allowed. Is this contact-associated?",
            "In Aedes aegypti, no-contact treatment exits were equal to no-contact control "
            "exits, but contact treatment exits outnumbered contact control exits. Which "
            "effect is indicated?",
            "Aedes aegypti no-contact treatment escape matched control, while contact "
            "treatment escape exceeded control. What does this support?",
            "Aedes aegypti treatment escape matched control when contact was blocked "
            "(p = 0.70), while treatment escape exceeded control when contact was allowed "
            "(p = 0.01). What does this support?",
            "Aedes aegypti treatment-control escape was null when contact was blocked and "
            "its interval included zero, while treatment escape exceeded control when "
            "contact was allowed and its interval was entirely above zero. What does this "
            "support?",
            "Aedes aegypti treatment escape matched control when contact was blocked, while "
            "treatment escape exceeded control when contact was allowed and mortality "
            "matched control. Does this support contact-associated escape?",
            "Aedes aegypti treatment escape matched control at 10 minutes and 30 minutes "
            "when contact was blocked, while treatment escape exceeded control at 10 minutes "
            "and 30 minutes when contact was allowed. What does this support?",
            "With transfluthrin, Aedes aegypti treatment escape matched control when contact "
            "was blocked, while treatment escape exceeded control when contact was allowed. "
            "What does this support?",
            "For Aedes aegypti, treatment escape matched control without contact "
            "(p = 0.62), whereas treatment escape exceeded control with contact "
            "(p = 0.004; q = 0.012). What interpretation is supported?",
            "The Aedes aegypti no-contact treatment-control difference in egress had a 95% "
            "confidence interval from -0.08 to 0.07, while the contact treatment egress was "
            "greater than control with a confidence interval from 0.12 to 0.31. How should "
            "this be interpreted?",
            "At both 5 minutes and 25 minutes, Aedes aegypti treatment departure matched "
            "control without contact and treatment departure exceeded control with contact. "
            "What does the repeated departure result support?",
            "In Aedes aegypti, treatment and control had the same proportion leaving without "
            "contact (q = 0.73), but a greater proportion was leaving under treatment than "
            "control with contact (q = 0.018); 24-hour mortality did not differ. What is "
            "supported?",
            "Aedes aegypti treatment departure equaled control departure without contact at "
            "15 and 30 minutes, while treatment departure was greater than control departure "
            "with contact at the same 15- and 30-minute observations. How should we report "
            "this?",
            "In Aedes aegypti, the no-contact treatment-control escape contrast was null "
            "(p = 0.48; q = 0.61), while the contact treatment-control escape contrast was "
            "positive, with treatment escape greater than control escape (p = 0.006; "
            "q = 0.019). What does this support?",
            "For Aedes aegypti, treatment minus control for exit was centered on zero without "
            "contact (95% confidence interval -0.05 to 0.06), but treatment exit was greater "
            "than control exit with contact (95% confidence interval 0.09 to 0.27). How "
            "should this be interpreted?",
            "At 10 minutes, 20 minutes, and 30 minutes, Aedes aegypti treatment departure "
            "matched control departure without contact, while at the same three timepoints "
            "treatment departure exceeded control departure with contact. What pattern is "
            "supported?",
            "TFT-treated Aedes aegypti had no treatment-control increase in egress without "
            "contact, with a credible interval spanning zero, but had greater treatment "
            "egress than control with contact, with the credible interval wholly positive. "
            "Which interpretation follows?",
            "Aedes aegypti treatment minus control for exit was null in the no-contact "
            "condition, with a 95% confidence interval of -0.04 to 0.05, whereas treatment "
            "exit exceeded control exit in the contact condition, with a 95% confidence "
            "interval of 0.11 to 0.29. What is supported?",
            "At 8 minutes, 16 minutes, and 30 minutes, Aedes aegypti treatment departure "
            "equaled control departure in the no-contact arm and exceeded control departure "
            "in the contact arm. How should this repeated result be interpreted?",
            "TFT exposure produced no treatment-control increase in Aedes aegypti egress "
            "without contact, and the credible interval covered zero; with contact, "
            "treatment egress was greater than control and the credible interval remained "
            "above zero. Which effect is indicated?",
            "For Aedes aegypti, the 95% confidence interval for the no-contact "
            "treatment-control exit difference was -0.03 to 0.04, while the contact "
            "treatment exit was greater than control exit with a confidence interval of "
            "0.08 to 0.22. How should this be interpreted?",
            "With TFT, Aedes aegypti treatment egress matched control egress without contact "
            "and its credible interval included zero, but treatment egress exceeded control "
            "egress with contact and the credible interval had a positive lower bound. Which "
            "response is supported?",
            "The Aedes aegypti treatment-control difference in exit straddled zero without "
            "contact, with a 95% confidence interval of -0.06 to 0.03, but treatment exit "
            "exceeded control exit with contact, with a confidence interval of 0.10 to 0.26. "
            "How should the result be interpreted?",
            "Aedes aegypti treatment escape remained at control escape without contact and "
            "rose above control escape with contact; separately measured knockdown and "
            "mortality did not differ from control. Is escape contact-associated?",
            "Aedes aegypti treatment escape matched control escape when contact was prevented "
            "and exceeded control escape when contact was permitted; the separately reported "
            "feeding rate was unchanged. Does the escape result support a contact-associated "
            "response?",
            "In Aedes aegypti, treatment departure remained at the control level without "
            "contact, with a confidence interval spanning zero, whereas it rose above control "
            "with contact, with a wholly positive confidence interval; landing frequency did "
            "not change. How should departure be interpreted?",
            "At 9 minutes and 23 minutes in each arm, Aedes aegypti treatment egress was no "
            "higher than control egress without contact, while treatment egress was higher "
            "than control egress with contact. Is this contact-associated egress?",
            "Treatment escape in Aedes aegypti did not rise above control when contact was "
            "excluded but did rise above control when contact was available; wing-beat "
            "frequency was reported separately and remained unchanged. Is the escape effect "
            "contact-associated?",
            "Without contact, Aedes aegypti treatment leaving was no greater than control "
            "leaving (q = 0.67); with contact, treatment leaving was greater than control "
            "leaving (q = 0.011), and recovery at 24 hours was similar. How should leaving "
            "be described?",
            "Without surface contact, Aedes aegypti treatment departure matched control and "
            "its credible interval included zero; with surface contact, treatment departure "
            "exceeded control and its credible interval stayed above zero. Separately, "
            "probing duration matched control. What does departure support?",
            "Across the shared 12-minute and 26-minute readings, Aedes aegypti treatment "
            "egress equaled control egress in the contact-prevented condition and exceeded "
            "control egress in the contact-permitted condition. Is the egress response "
            "contact-associated?",
            "For Aedes aegypti, the no-contact treatment-control exit estimate was "
            "consistent with zero, with a 95% confidence interval from -0.05 to 0.08, "
            "whereas the contact estimate was positive and treatment exit was greater "
            "than control, with a confidence interval from 0.04 to 0.17. How should this "
            "be read?",
            "TFT-treated Aedes aegypti showed treatment egress equal to control egress "
            "while contact was prevented, with a credible interval overlapping zero; "
            "once contact was allowed, treatment egress was greater than control and the "
            "credible interval was wholly above zero. What does this support?",
            "Aedes aegypti treatment escape was no higher than control when contact was "
            "blocked and higher than control when contact was possible; the separate "
            "fecundity measure was unchanged. What interpretation applies to escape?",
            "Aedes aegypti treatment egress equaled control egress without contact "
            "(p = 0.55), but was greater than control egress with contact (q = 0.022); "
            "flight speed was separately reported as unchanged. How should egress be "
            "interpreted?",
            "Without contact, Aedes aegypti treatment leaving matched control leaving and "
            "the confidence interval covered zero. With contact, treatment leaving exceeded "
            "control leaving and the confidence interval had a positive lower bound. "
            "Antennal grooming did not differ. What does leaving support?",
            "Using the same 7-minute and 24-minute readouts for both conditions, Aedes "
            "aegypti treatment escape equaled control without contact and exceeded control "
            "with contact. What pattern does this show?",
            "Aedes aegypti treatment escape matched control without contact, with a 95% "
            "confidence interval from -0.05 to 0.04, and treatment escape exceeded control "
            "with contact, with a 95% confidence interval from 0.10 to 0.25. What does this "
            "support?",
            "Without contact, Aedes aegypti treatment escape matched control and its "
            "confidence interval included zero, and with contact treatment escape exceeded "
            "control and its confidence interval stayed above zero. What does this support?",
            "Aedes aegypti treatment exit matched control without residue contact "
            "(p = 0.58), and treatment exit exceeded control with residue contact "
            "(p = 0.014). What does exit support?",
            "Aedes aegypti treatment departure matched control without direct contact "
            "(q = 0.63), and treatment departure exceeded control with direct contact "
            "(q = 0.012). What does departure support?",
            "With TFT, Aedes aegypti treatment egress remained equal to control egress "
            "when surface contact was blocked and the credible interval contained zero; "
            "when surface contact was permitted, treatment egress exceeded control and "
            "the credible interval was entirely above zero. What is supported?",
            "Aedes aegypti treatment escape did not exceed control when contact was "
            "unavailable but exceeded control when contact was available; walking speed "
            "was analyzed separately and matched control. Is the escape pattern "
            "contact-associated?",
            "Aedes aegypti treatment leaving was indistinguishable from control leaving "
            "without contact (p = 0.61; q = 0.72) and greater than control leaving with "
            "contact (p = 0.006; q = 0.016); mortality was unchanged. What does leaving "
            "support?",
            "Without contact, Aedes aegypti treatment exit matched control and its "
            "confidence interval included zero; with contact, treatment exit was higher "
            "than control and its confidence interval stayed positive. Oviposition was "
            "separately unchanged. How should exit be interpreted?",
            "Aedes aegypti treatment egress was no higher than control egress without "
            "contact and its confidence interval included zero; treatment egress was "
            "higher than control with contact and its confidence interval lay above zero. "
            "Biting frequency was separately unchanged. What does egress support?",
            "Transfluthrin-exposed Aedes aegypti had treatment egress equal to control "
            "when contact was excluded and a credible interval spanning zero; with "
            "contact included, treatment egress exceeded control and the credible interval "
            "was fully above zero. Which interpretation is warranted?",
            "At the identical 6-minute and 25-minute checks in both Aedes aegypti arms, "
            "treatment departure matched control without contact and was higher than "
            "control with contact. What does the departure pattern show?",
            "Aedes aegypti treatment escape did not rise above control without contact "
            "but rose above control with contact. Biting duration was evaluated separately "
            "and remained at the control level. Is the escape response contact-associated?",
            "For Aedes aegypti, treated escape was indistinguishable from control escape "
            "with contact prevented (p = 0.68; q = 0.79), but treated escape was greater "
            "than control escape with contact allowed (p = 0.006; q = 0.017). What is "
            "supported?",
            "In the TFT assay, Aedes aegypti treatment egress equaled control egress in "
            "the no-touch condition and the credible interval crossed zero, whereas "
            "treatment egress was greater than control in the touch-enabled condition and "
            "the interval was wholly positive. What does this support?",
            "Aedes aegypti treatment egress remained at control egress without contact "
            "and its confidence interval contained zero; with contact, treatment egress "
            "rose above control and its confidence interval had a positive lower bound. "
            "Takeoff count was separately unchanged. How should egress be interpreted?",
            "In Aedes aegypti, treatment escape was not elevated above control in the "
            "contact-barred condition (p = 0.56; q = 0.67), but treatment escape was "
            "elevated above control in the contact-open condition (p = 0.003; q = 0.012). "
            "What does this result support?",
            "With TFT treatment, Aedes aegypti egress matched control when a mesh blocked "
            "contact and the credible interval included zero; when the mesh no longer "
            "blocked contact, treatment egress exceeded control and the interval stayed "
            "entirely positive. What is supported?",
            "For Aedes aegypti, treatment escape did not exceed control when contact was "
            "denied (p = 0.64; q = 0.76), whereas treatment escape exceeded control when "
            "contact was permitted (p = 0.005; q = 0.016). What does this support?",
            "In a transfluthrin assay, Aedes aegypti treatment egress matched control "
            "behind the contact barrier and the credible interval covered zero; after "
            "contact access was allowed, treatment egress was greater than control and "
            "the interval remained entirely above zero. Which effect is supported?",
            "Aedes aegypti treatment escape equaled control without contact and exceeded "
            "control with contact. Host-seeking orientation was reported separately and "
            "did not change. Is the escape finding contact-associated?",
            "Aedes aegypti treatment exit remained at control exit without contact "
            "(p = 0.58; q = 0.69) and rose above control exit with contact (p = 0.009; "
            "q = 0.021); mortality stayed equal to control. What does exit support?",
            "Using matched 6-minute and 23-minute readouts in both formats, Aedes aegypti "
            "treatment escape was no higher than control without contact and higher than "
            "control with contact. Does this support contact-associated escape?",
            "For Aedes aegypti, treatment escape matched control while contact was "
            "restricted (p = 0.60; q = 0.72), but treatment escape was greater than "
            "control while contact was available (p = 0.004; q = 0.013). Which "
            "interpretation is supported?",
            "For TFT-treated Aedes aegypti, egress under treatment equaled control while "
            "the paper was inaccessible and the credible interval overlapped zero; when "
            "the paper became reachable for contact, treatment egress exceeded control "
            "and the interval stayed wholly above zero. How should this be interpreted?",
            "Aedes aegypti treatment escape was no higher than control without contact "
            "and higher than control with contact. Feeding attempts were analyzed "
            "separately and did not differ from control. Is the escape result "
            "contact-associated?",
            "In Aedes aegypti, treatment escape remained equal to control with contact "
            "blocked (p = 0.62; q = 0.73), while treatment escape exceeded control with "
            "contact allowed (p = 0.003; q = 0.011). What interpretation follows?",
            "Transfluthrin-treated Aedes aegypti showed egress equal to control when "
            "direct contact was prevented and the credible interval encompassed zero; "
            "when direct contact was possible, treatment egress was greater than control "
            "and the interval was entirely positive. How should this be interpreted?",
            "Aedes aegypti treatment escape equaled control when contact was not possible "
            "and was greater than control when contact was possible. Wing movement was "
            "measured separately and did not differ. Does escape support a "
            "contact-associated effect?",
            "In TFT-exposed Aedes aegypti, treatment egress matched control while a "
            "screen separated mosquitoes from the paper and the credible interval included "
            "zero; after paper contact was enabled, treatment egress exceeded control and "
            "the interval stayed above zero. Which interpretation follows?",
            "At common 5-minute and 29-minute observations in both conditions, Aedes "
            "aegypti treatment departure equaled control without contact and exceeded "
            "control with contact. What departure response is present?",
            "Aedes aegypti treatment escape remained at control without contact and was "
            "greater than control with contact. Flight velocity was assessed separately "
            "and remained unchanged. Does escape support a contact-associated effect?",
            "Using identical 8-minute and 19-minute readings for each arm, Aedes aegypti "
            "treatment escape did not exceed control without contact and did exceed "
            "control with contact. Is this contact-associated escape?",
            "For Aedes aegypti, treatment escape matched control with the contact barrier "
            "in place (p = 0.61; q = 0.70), whereas treatment escape exceeded control "
            "with the barrier absent (p = 0.004; q = 0.015). What result is supported?",
            "With TFT, Aedes aegypti treatment egress equaled control while mesh prevented "
            "paper contact and the credible interval crossed zero; after the mesh was "
            "removed for contact, treatment egress exceeded control and the interval was "
            "wholly above zero. What does this support?",
            "For Aedes aegypti, treatment escape equaled control with the contact screen "
            "present (p = 0.54; q = 0.65), while treatment escape was greater than control "
            "with the screen removed (p = 0.003; q = 0.010). What does this support?",
            "For transfluthrin-treated Aedes aegypti, egress under treatment matched "
            "control while the treated surface was out of reach and the credible interval "
            "contained zero; once the surface was reachable for contact, treatment egress "
            "exceeded control and the interval was fully positive. Which interpretation "
            "is supported?",
            "Aedes aegypti treatment escape matched control in the absence of contact and "
            "exceeded control in the presence of contact. Feeding duration was evaluated "
            "separately and remained unchanged. Is escape contact-associated?",
            "For Aedes aegypti, treatment escape stayed at control with the contact shield "
            "active (p = 0.58; q = 0.69), whereas treatment escape exceeded control with "
            "the shield inactive (p = 0.004; q = 0.012). Which interpretation is "
            "supported?",
            "In TFT-treated Aedes aegypti, egress matched control while the barrier "
            "prevented treated-paper contact and the credible interval overlapped zero; "
            "once treated-paper contact was allowed, treatment egress exceeded control "
            "and the interval stayed entirely positive. How should this be interpreted?",
            "Aedes aegypti treatment escape matched control without contact and exceeded "
            "control with contact. Takeoff latency was analyzed separately and remained "
            "unchanged. Is the escape response contact-associated?",
            "In an Aedes aegypti excito-repellency assay, treated and control escape were "
            "equal behind a mesh barrier, but treated mosquitoes escaped more than "
            "controls when they could touch the treated paper. What can this result "
            "support, and what can it not support?",
            "For Aedes aegypti, normalized exit was unchanged from control in the "
            "no-contact treatment arm (q = 0.71), whereas normalized exit in the "
            "contact-treatment arm exceeded its control (q = 0.02). Is this a "
            "contact-only response?",
            "The Aedes aegypti treatment-control difference in leaving was zero without "
            "access to the paper (95% CI -0.05 to 0.05), while treatment produced more "
            "leaving than control with paper contact (difference 0.18, 95% CI 0.07 to "
            "0.29). How should we interpret it?",
            "At 8, 16, and 24 minutes, Aedes aegypti escape in the separated treatment "
            "chamber never exceeded its time-matched control, whereas at each same time "
            "point escape with surface contact was higher for treatment than control. "
            "Is the response confined to contact?",
            "After scaling each chamber to its paired control, Aedes aegypti no-contact "
            "escape showed no treatment-control increase, but contact-treatment escape "
            "remained greater than contact-control escape. How should the adjusted "
            "pattern be described?",
            "For Aedes aegypti, the mesh-separated escape contrast was null (p = 0.58) "
            "and the allowed-contact escape contrast was positive (q = 0.014); knockdown "
            "did not differ between treatment and control. Does this support "
            "contact-associated escape?",
            "Aedes aegypti had equal treatment and control egress without paper contact "
            "at both 15 and 30 minutes, yet TFT-treated contact chambers had greater "
            "egress than contact controls at those same readings. What is the appropriate "
            "result interpretation?",
            "Aedes aegypti leaving under no-contact treatment was no higher than under "
            "its vehicle control, while leaving from the treated contact chamber was "
            "higher than from the contact control; recovery at 24 hours was the same in "
            "all groups. What is the escape interpretation?",
            "In Aedes aegypti tests of transfluthrin, screened treatment and vehicle "
            "chambers had equal exit (q = 0.63), but treatment exit exceeded vehicle in "
            "chambers allowing touch (p = 0.017). What can be inferred?",
            "Aedes aegypti egress did not rise above control when contact was prevented "
            "(posterior interval -0.03 to 0.06), yet treated egress was greater than "
            "control with contact (posterior interval 0.05 to 0.24). How should the "
            "two-arm finding be described?",
            "For Aedes aegypti, the treated-minus-control exit estimate without contact "
            "was -0.01 (95% CI -0.07 to 0.05), so there was no increase; with contact, "
            "treated exit was greater than control by 0.16 (95% CI 0.06 to 0.26). What "
            "does this support?",
            "Transfluthrin caused no treatment-control increase in Aedes aegypti egress "
            "behind the barrier, and its credible interval covered zero, but contact "
            "egress was greater for transfluthrin than carrier with a positive credible "
            "interval; mortality was unchanged. What is the behavioral inference?",
            "After normalizing each response to its arm-specific control, Aedes aegypti "
            "escape had no treatment-control increase without contact and a greater "
            "treatment than control value with contact. How should this normalized "
            "result be stated?",
            "Aedes aegypti egress showed no increase over control with contact blocked "
            "(Bayesian interval -0.04 to 0.04), while treated egress exceeded control "
            "with contact allowed (Bayesian interval 0.07 to 0.22). Is that a "
            "contact-only result pattern?",
            "Aedes aegypti had no treatment-control increase in exit without access to "
            "the surface: the contrast was 0.00 with a 95% confidence interval of -0.08 "
            "to 0.08. With contact, treated exit exceeded control by 0.14 with a 95% "
            "interval of 0.04 to 0.24. How should this be interpreted?",
            "At minutes 4, 17, and 29, Aedes aegypti departure under no-contact treatment "
            "was no higher than control, while departure under contact treatment exceeded "
            "control at the same three readings. What conclusion follows?",
            "Relative to the respective arm controls, normalized Aedes aegypti escape "
            "showed no increase for the no-contact treatment and a greater response for "
            "the contact treatment than its control. How should we label the observed "
            "effect?",
            "Transfluthrin gave Aedes aegypti exit equal to vehicle while the barrier "
            "remained in place (q = 0.67), but gave higher exit than vehicle after the "
            "barrier was removed and paper contact became possible (p = 0.015). What can "
            "be claimed?",
            "At both 11 and 23 minutes, Aedes aegypti no-contact treatment and control "
            "had equal departure, whereas TFT contact treatment had greater departure "
            "than control at both matched times. How should the result be summarized?",
            "For Aedes aegypti, transfluthrin did not increase egress over vehicle "
            "through the contact-blocked chamber and its credible interval included zero, "
            "while transfluthrin egress exceeded vehicle under direct contact with a "
            "credible interval above zero; mortality was unchanged. What conclusion is "
            "justified?",
            "Using arm-to-control normalized ratios, Aedes aegypti escape had no "
            "treatment increase in the no-contact pair and a greater treatment ratio "
            "than control in the contact pair. How should this result be described?",
            "TFT and vehicle gave equal Aedes aegypti exit with the barrier lowered "
            "(q = 0.62), but TFT gave higher exit than vehicle with the barrier raised "
            "so mosquitoes could contact the paper (p = 0.014). What does the pattern "
            "support?",
            "No treatment-control increase in Aedes aegypti escape appeared behind the "
            "mesh, but treated escape was greater than control after surface contact; "
            "knockdown, reported as a distinct endpoint, remained unchanged. What can be "
            "inferred from escape?",
            "In Aedes aegypti, no-contact treatment escape was not greater than control "
            "(p = 0.70), but contact-treatment escape was greater than contact control "
            "(q = 0.005). What interpretation fits this result?",
            "No-contact Aedes aegypti leaving was the same under treatment and control, "
            "whereas treated contact chambers had greater leaving than contact controls; "
            "post-assay recovery, considered separately, was unchanged. Is the escape "
            "effect contact-associated?",
            "At 5, 19, and 30 minutes, Aedes aegypti departure in the no-contact treatment "
            "equaled control, while departure in the contact treatment exceeded control "
            "at all three matching observations. How should this pattern be reported?",
            "After normalizing treatment values to their own arm controls, Aedes aegypti "
            "escape had no increase in the no-contact arm and a greater treated value than "
            "control in the contact arm. What conclusion follows?",
            "With the screen inserted, transfluthrin and vehicle produced equal Aedes "
            "aegypti exit (q = 0.65); with the screen withdrawn so contact could occur, "
            "transfluthrin produced higher exit than vehicle (p = 0.011). What does this "
            "indicate?",
            "Treatment did not increase Aedes aegypti escape above control when mesh "
            "prevented contact, but treated escape exceeded control with direct contact; "
            "the independently tabulated knockdown endpoint did not differ. What does "
            "escape support?",
            "In an Aedes aegypti run, no-contact treatment escape did not surpass control "
            "(p = 0.68), whereas contact treatment escape surpassed contact control "
            "(q = 0.004). What does this observed pattern mean?",
            "At 1, 12, and 24 minutes, Aedes aegypti departure under no-contact treatment "
            "was equal to control, while contact treatment departure was greater than "
            "control at the same three time points. What conclusion fits?",
            "With the mesh panel present, Aedes aegypti exit under transfluthrin equaled "
            "vehicle (q = 0.60); with the panel absent and contact possible, "
            "transfluthrin exit exceeded vehicle (p = 0.013). What can be concluded?",
            "At 4, 15, and 28 minutes, Aedes aegypti departure under no-contact treatment "
            "matched control, while treated contact departure was greater than control at "
            "every corresponding measurement. What pattern was observed?",
            "When mesh covered the paper, TFT and vehicle produced equal Aedes aegypti "
            "exit (q = 0.58); when the mesh was moved aside to allow contact, TFT "
            "produced higher exit than vehicle (p = 0.016). What does the two-arm result "
            "mean?",
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
                    {record_id},
                )
                for fragment in (
                    "Interpretation of the stated result pattern:",
                    "no spatial-repellency signal was detected under those assay conditions",
                    "treated-contact escape exceeds its paired contact control",
                    "simultaneous paired non-contact adjustment",
                    "supports a contact-associated behavioral effect, not spatial repellency",
                    "does not identify a sensory receptor or molecular mechanism",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

        negative_questions = (
            "Aedes aegypti escape matched control without paper contact; after paper "
            "contact was enabled, the treated group exceeded the control group. Is "
            "escape contact-associated?",
            "Without contact, Aedes aegypti departure equaled control; the treatment "
            "effect became greater than control under contact. Does departure support "
            "a contact effect?",
            "The treated group was above the control group with paper contact, while "
            "Aedes aegypti exit matched control without paper contact. Is exit "
            "contact-associated?",
            "Aedes aegypti escape matched control without direct contact and showed a "
            "positive treatment effect relative to control with direct contact. Is "
            "escape contact-associated?",
            "Aedes aegypti escape matched control without contact; with contact, "
            "treatment was higher than control. Is this contact-associated?",
            "Without contact, Aedes aegypti treatment matched control; with contact, "
            "treatment escape exceeded control escape. Is this a contact-only escape result?",
            "Without contact, Aedes aegypti treatment matched control; with contact, "
            "treatment exceeded control. Is this contact-associated escape?",
            "Aedes aegypti departure matched control without contact; with surface contact, "
            "the treatment response exceeded control. Does departure support contact "
            "association?",
            "Aedes aegypti exit matched control without residue contact; with residue "
            "contact, the treated group was higher than control. Is exit contact-associated?",
            "Aedes aegypti leaving equaled control without direct contact; with direct "
            "contact, the treatment effect exceeded control. Does leaving support contact "
            "association?",
            "Aedes aegypti exit matched control without contact; with contact, the treatment "
            "rate exceeded the control rate. Is exit contact-associated?",
            "Aedes aegypti egress equaled control without contact; with contact, the "
            "treatment estimate was above control. Is egress contact-associated?",
            "Aedes aegypti departure matched control without contact; with contact, the "
            "treated proportion exceeded the control proportion. Is departure "
            "contact-associated?",
            "Aedes aegypti treatment equaled control with contact absent; treatment exceeded "
            "control with contact present. Is this an egress result?",
            "Aedes aegypti treatment escape matched control when contact was blocked, while "
            "treatment escape failed to be higher than control when contact was allowed. "
            "Does this support contact-associated escape?",
            "Aedes aegypti treatment escape matched control when contact was blocked, while "
            "treatment escape could not be shown to exceed control when contact was allowed. "
            "Does this support contact-associated escape?",
            "Aedes aegypti treatment exit equaled control with contact blocked, but the "
            "contact treatment exit was unable to rise above control. Is exit increased by "
            "contact?",
            "Aedes aegypti no-contact testing occurred at 09:00 with escape matching control, "
            "whereas contact testing occurred at 21:00 with treatment escape exceeding "
            "control. Can the result be attributed to contact?",
            "Aedes aegypti no-contact egress matched control, whereas contact treatment "
            "egress was not shown to be above control egress. What does the result support?",
            "Aedes aegypti no-contact escape equaled control, while the 95% confidence "
            "interval for the contact treatment-control escape increase included zero. Can "
            "contact escape be called greater?",
            "Aedes aegypti treatment exit equaled control without contact, and treatment "
            "exit was estimated above control with contact, but the contact confidence "
            "interval ran from -0.04 to 0.16. Can a contact increase be claimed?",
            "Aedes aegypti exit showed no treatment-control difference without contact, but "
            "an increase in treatment exit was not seen when contact was allowed. Is contact "
            "exit elevated?",
            "Aedes aegypti treatment departure stayed at the control rate without contact, "
            "and there was no evidence that treatment departure was greater than control "
            "with contact. What does this support?",
            "No increase over control occurred for treated Aedes aegypti in the "
            "touch-blocked condition, but an increase occurred in the touch-allowed "
            "condition. What is supported?",
            "Aedes non-contact escape exceeded control while contact escape was "
            "unchanged. Which component is spatial?",
            "Reduced Aedes non-contact escape followed knockdown in the treated "
            "chamber. How should I separate motor impairment from avoidance?",
            "Which genes control non-contact escape and contact excitation in Aedes?",
            "Which experimental control should I use in a non-contact escape assay "
            "with a matched contact chamber?",
            "Aedes contact escape matched control, but non-contact escape increased. "
            "Does that support spatial repellency?",
            "Aedes contact-chamber escape was identical to control while noncontact "
            "escape was higher. Which component changed?",
            "Aedes noncontact escape increased over control, but contact escape was "
            "the same as control. How should I interpret the two formats?",
            "How should I design an experiment to test whether non-contact escape "
            "matches control while contact escape increases after touching treated paper?",
            "Which genes should I knock out to test why non-contact escape matches "
            "control but contact escape rises after touching treated paper?",
            "Could knockdown explain a result where non-contact escape matches "
            "control but contact escape increases after touching treated paper?",
            "Noncontact escape was identical to control, but treated-contact escape "
            "decreased rather than increased.",
            "Would an Orco mutant explain why noncontact escape matches vehicle but "
            "treated-contact escape is higher?",
            "Was the higher treated-contact escape caused by knockdown even though "
            "noncontact escape matched control?",
            "Noncontact escape was identical to vehicle; treated-contact escape was "
            "not increased by the paper.",
            "Noncontact escape matched vehicle and treated-contact escape was lower, "
            "not higher, than control.",
            "Could the Orco pathway be responsible for noncontact escape matching "
            "control while direct-contact escape rises?",
            "Could contact chemosensation be the cause of higher treated-contact "
            "escape when noncontact escape matches control?",
            "In an escape chamber noncontact landing equaled vehicle contact landing "
            "rose after touching treated paper",
            "Noncontact escape matched control contact-chamber mortality was elevated "
            "under treatment",
            "No extra exits occurred after paper contact, even though no-contact "
            "escape equaled vehicle.",
            "Treatment contact escape failed to exceed control while mesh-isolated "
            "escape remained equal to vehicle.",
            "Which statistical model should estimate higher treated-contact escape "
            "when noncontact treatment matches control?",
            "How would I build an apparatus to compare a zero noncontact effect with "
            "a positive contact escape effect?",
            "For Musca domestica, screened treatment escape equaled vehicle but "
            "contact escape rose.",
            "Which hypothesis test compares a zero no-touch effect with a larger "
            "touch-enabled escape effect?",
            "Is motor activation responsible for extra exits after touch when "
            "screened treatment matches carrier?",
            "Apis mellifera showed no barrier escape difference and a positive "
            "treated-contact escape difference.",
            "Treatment and control had equal noncontact escape, but flight activity "
            "increased in the contact assay.",
            "Noncontact escape did not differ from control, while time spent in the "
            "contact chamber increased.",
            "How many mosquitoes per replicate are needed if noncontact escape matches "
            "control and contact escape is higher?",
            "Which regression model should compare a null noncontact effect with an "
            "increased contact escape effect?",
            "How should treatment sides be randomized when contact escape is higher "
            "but noncontact escape matches vehicle?",
            "Which receptor explains higher contact escape when noncontact escape is "
            "unchanged from vehicle?",
            "No-contact escape equaled vehicle, while probing attempts increased after "
            "paper contact.",
            "What statistical model should I fit when non-contact escape matches control "
            "but contact escape is elevated?",
            "Which chemosensory receptor causes the higher contact escape when "
            "non-contact escape matches control?",
            "Which sensory neurons drive the contact escape increase despite no "
            "non-contact effect?",
            "What sample size is needed to detect no non-contact difference and a "
            "higher contact escape rate?",
            "Which test determines whether contact escape exceeds control when "
            "non-contact escape does not differ?",
            "Could toxic motor stimulation explain higher contact escape with no "
            "non-contact difference?",
            "Non-contact escape matched control, but walking speed was higher in the "
            "contact treatment.",
            "What model should analyze a non-contact null result and a higher contact "
            "escape result?",
            "No-contact escape matched control, while movement speed increased in the "
            "treated contact chamber.",
            "Which model should be used for a null no-contact result and an increased "
            "contact escape result?",
            "Could a toxic effect cause elevated contact escape while no-contact escape "
            "remains equal to vehicle?",
            "Culex pipiens matched control without contact and escaped more with "
            "treated-paper contact.",
            "The noncontact groups had the same escape, but more treated mosquitoes "
            "were knocked down in the contact chamber.",
            "What analysis should be used for a no-contact null and a contact escape "
            "increase?",
            "How many mosquitoes should each group contain to detect a null noncontact "
            "result and increased contact escape?",
            "What statistical approach should be used when noncontact escape matches "
            "control and contact escape is higher?",
            "How many mosquitoes are needed to compare a zero no-contact effect with "
            "increased contact escape?",
            "Noncontact escape matched control, while more mosquitoes landed in the "
            "treated contact chamber.",
            "Non-contact escape matched control, but general movement increased in the "
            "treated contact group.",
            "Is toxicity causing the higher contact escape despite no effect through mesh?",
            "Noncontact escape was unchanged, but movement rate increased in the treated "
            "contact group.",
            "How many females should be tested to detect equal noncontact escape and "
            "higher contact escape?",
            "No-contact escape matched control, while distance walked increased after "
            "contact treatment.",
            "No-contact escape was equal to vehicle, but path length increased after "
            "contact treatment.",
            "How many mosquitoes per chamber are needed for equal barrier escape and "
            "increased contact escape?",
            "Which statistical method should evaluate a null no-contact result and a "
            "positive contact escape result?",
            "Could a toxic action explain increased contact escape with unchanged "
            "no-contact escape?",
            "No-contact escape was equal to control, but total movement increased in "
            "the contact treatment group.",
            "How many mosquitoes per condition should be used to detect equal "
            "no-contact escape and higher contact escape?",
            "How many insects should go into each arm to detect equal noncontact escape "
            "and higher contact escape?",
            "Could a toxic response cause greater contact escape while noncontact "
            "escape stays equal to control?",
            "Noncontact escape was equal to control, but time active increased in the "
            "contact treatment group.",
            "What test should compare a null noncontact result with an increased "
            "contact escape result?",
            "Noncontact escape was unchanged, but the amount of time moving increased "
            "during contact treatment.",
            "With mesh escape matched vehicle, and without mesh treatment did not "
            "increase escape above vehicle.",
            "How should we set up screened and unscreened chambers to measure equal "
            "noncontact escape and higher contact escape?",
            "Should we use a paired logistic model when no-contact escape matches "
            "control and contact escape exceeds control?",
            "Noncontact escape matched vehicle, but average speed increased in the "
            "treated contact chamber.",
            "How many females per arm are needed to detect equal noncontact escape and "
            "higher contact escape?",
            "Aedes barrier escape equaled vehicle, but blood-feeding attempts "
            "increased after paper contact.",
            "Aedes barrier escape equaled vehicle, while probing was higher in the "
            "treated contact chamber.",
            "What number of Aedes females is required to detect no non-contact effect "
            "and increased contact escape?",
            "Could toxic stimulation be the reason Aedes contact escape rises while "
            "barrier escape matches control?",
            "What power is needed to detect a null Aedes no-contact result and an "
            "increased contact escape result?",
            "How many Aedes batches are needed to detect equal no-contact escape and "
            "increased contact escape?",
            "What statistical method should compare an Aedes no-contact null with "
            "higher contact escape?",
            "Could treatment toxicity create higher Aedes contact escape despite equal "
            "barrier escape?",
            "Culex pipiens pallens showed equal no-contact escape and increased treated "
            "contact escape.",
            "How many Aedes groups should be tested for a null barrier escape result and "
            "a higher contact escape result?",
            "Which analytical test should evaluate equal Aedes no-contact escape and "
            "increased contact escape?",
            "Could partial paralysis create an apparent Aedes contact escape increase "
            "while barrier escape matches control?",
            "How many Aedes trials are required for equal barrier escape and higher "
            "contact escape?",
            "Which link function should be used for a model of null non-contact escape "
            "and elevated contact escape?",
            "Could treatment-induced sedation account for an apparent contact escape "
            "increase despite equal barrier escape?",
            "Aedes screened escape equaled vehicle, while blood-feeding rate was higher "
            "after treated-paper contact.",
            "Does TRPA1 mediate the Aedes contact escape increase when no-contact escape "
            "matches control?",
            "Which generalized linear mixed model should analyze a null Aedes "
            "no-contact result and positive contact escape result?",
            "Which mixed-effects analysis should compare an Aedes no-contact arm that "
            "matches control with a contact arm that has higher escape?",
            "What paired statistical test should be used when Aedes treatment escape "
            "equals control behind mesh and exceeds control with direct contact?",
            "Is absorption through the Aedes tarsi the cause of unchanged escape behind "
            "a screen and greater escape with paper access?",
            "What mesh opening and chamber dimensions should be used to test equal "
            "escape without contact and increased escape with contact in Aedes?",
            "Does olfactory adaptation explain why Aedes escape is control-like without "
            "contact but greater after contact?",
            "Culex pipiens escape was equal to control across mesh and higher than "
            "control with treated paper exposed. How should that species result be "
            "classified?",
            "How should the interaction term be calculated for equal treatment-control "
            "Aedes escape without contact and higher treatment escape with contact?",
            "Aedes escape was unchanged from control behind the screen, and the observed "
            "contact increase failed the significance test against control. Is a contact "
            "increase supported?",
            "How should confidence intervals be computed for a null Aedes no-contact "
            "contrast and a positive contact escape contrast?",
            "What multiplicity correction should be applied when testing null noncontact "
            "escape and elevated contact escape against control in Aedes?",
            "Aedes escape matched control without contact, but the apparent contact "
            "increase disappeared after adjustment for replicate. Can we still claim "
            "increased contact escape?",
            "Which contrast coding should be used for Aedes data with equal no-contact "
            "escape and greater contact escape under treatment?",
            "Should a mesh separator be mounted upstream or downstream when testing "
            "control-like no-contact escape and increased contact escape in Aedes?",
            "Aedes escape matched control in the no-contact arm, while the contact arm ran "
            "five degrees warmer and showed higher treatment escape. Can the increase be "
            "assigned to contact?",
            "Aedes escape matched control without contact and fell below control after "
            "treatment contact. Is this evidence of increased contact escape?",
            "The Aedes contact estimate has p = 0.08 after a null noncontact result. May I "
            "report a significant increase in contact escape?",
            "Which post hoc test should compare Aedes treatment with control after finding "
            "no noncontact escape effect and a positive contact escape effect?",
            "What mesh pore size is appropriate for an Aedes assay intended to compare null "
            "no-contact escape with elevated contact escape?",
            "The Aedes no-contact arm matched control, but humidity was much lower in the "
            "contact arm where treatment escape increased. Can contact explain the "
            "difference?",
            "Aedes escape equaled control at the low dose used without contact, while a "
            "tenfold dose in the contact arm increased escape. Does this isolate a contact "
            "effect?",
            "How many chambers are needed to test a null Aedes no-contact effect alongside "
            "a positive contact escape effect?",
            "Does IR25a mediate the Aedes pattern of control-level escape without contact "
            "and increased escape after contact?",
            "Should a paired t-test or a binomial model analyze equal no-contact Aedes "
            "escape and higher contact escape?",
            "What chamber length is required to test unchanged Aedes escape without contact "
            "and increased escape with contact?",
            "The Aedes screened arm ran in the morning and matched control, while the contact "
            "arm ran at dusk and showed increased escape. Does this establish a contact "
            "effect?",
            "Which random-slope structure should be fitted to Aedes escape with a null "
            "mesh-arm contrast and a positive contact-arm contrast?",
            "How should Aedes escape percentages be transformed before analyzing equal "
            "no-contact and higher contact treatment effects?",
            "Where should the escape outlet be positioned in an apparatus testing null "
            "noncontact and positive contact effects in Aedes?",
            "The Aedes no-contact arm ran at 25 C and matched control, while the contact arm "
            "ran at 30 C and showed higher treatment escape. Can we attribute the increase "
            "to contact?",
            "Aedes escape matched control in the no-contact arm and was lower than control "
            "in the contact arm. Does this indicate increased contact escape?",
            "Aedes contact escape was higher before correction but no longer significant "
            "after multiple-testing adjustment; no-contact escape matched control. What "
            "should we report?",
            "How should we calculate the treatment-by-contact interaction for equal "
            "no-contact escape and increased contact escape in Aedes?",
            "Aedes contact escape was initially higher, but the difference disappeared after "
            "adjusting for cage; no-contact escape matched control. What conclusion is "
            "supported?",
            "Treatment affected Aedes escape only when they could touch the treated "
            "substrate; with contact prevented, escape matched control. What can be inferred?",
            "The Aedes no-contact arm was run during the light phase and matched control, "
            "while the contact arm was run in darkness and showed increased escape. Can this "
            "be attributed to contact?",
            "Aedes contact escape appeared higher before adjustment but matched control "
            "after accounting for batch; no-contact escape also matched control. What should "
            "be reported?",
            "Male Aedes were used in the no-contact arm and matched control, while females "
            "were used in the contact arm and showed higher treatment escape. Can contact "
            "explain the difference?",
            "The Aedes no-contact exposure lasted two minutes and matched control, while the "
            "contact exposure lasted twenty minutes and increased escape. Is contact "
            "isolated?",
            "Fed Aedes were used in the no-contact arm and matched control, while starved "
            "Aedes were used in the contact arm and showed increased escape. Can this be "
            "attributed to contact?",
            "The no-contact Aedes arm used 20 mosquitoes per cage and matched control, while "
            "the contact arm used 60 per cage and showed increased escape. Can contact "
            "explain the difference?",
            "Aedes contact escape was higher before correction but had an FDR-adjusted q = "
            "0.20; no-contact escape matched control. What should be claimed?",
            "The Aedes no-contact arm had no host odor and matched control, while host odor "
            "was added to the contact arm where treatment escape increased. Can contact "
            "explain the difference?",
            "The no-contact Aedes arm ran in one room and matched control, while the contact "
            "arm ran in another room and showed increased treatment escape. Is contact "
            "isolated?",
            "A permutation test found no significant Aedes contact increase, while "
            "no-contact escape matched control. What should be reported?",
            "The Aedes no-contact arm had no carbon dioxide source and matched control, "
            "while carbon dioxide was added in the contact arm where treatment escape "
            "increased. Can contact explain the result?",
            "Aedes treatment escape matched control without contact and was below control "
            "with contact. Does this show increased contact escape?",
            "The Aedes no-contact arm used small cages and matched control, while the "
            "contact arm used cages twice as large and showed increased treatment escape. "
            "Can contact explain the difference?",
            "The escape opening was larger in the Aedes contact cages than in the no-contact "
            "cages, where treatment matched control. Is contact isolated?",
            "Nulliparous Aedes were used without contact and matched control, while gravid "
            "Aedes were used with contact and showed increased escape. Can contact explain "
            "the difference?",
            "The Aedes no-contact cages were horizontal and matched control, while the "
            "contact cages were vertical and showed increased treatment escape. Is contact "
            "isolated?",
            "The Aedes no-contact cages were freshly cleaned and matched control, while the "
            "contact cages carried residual odor and showed increased treatment escape. Can "
            "contact explain the difference?",
            "Aedes treatment escape exceeded control with contact. What can be concluded "
            "when no-contact results are absent?",
            "The no-contact Aedes arm used 3-day-old females and matched control, while the "
            "contact arm used 9-day-old females and showed higher treated escape. Can the "
            "difference be attributed to contact?",
            "Rockefeller Aedes matched control in the no-contact arm, while Liverpool Aedes "
            "showed increased treated escape in the contact arm. Does this isolate a contact "
            "effect?",
            "The no-contact Aedes pair ran at 0.1 m/s airflow and matched control, while the "
            "contact pair ran at 1.0 m/s and showed higher treated escape. Is contact the "
            "explanation?",
            "The no-contact arm used twenty Aedes per cage and matched control, while the "
            "contact arm used sixty per cage and showed increased escape. Can contact explain "
            "the result?",
            "Colony Aedes matched control in the no-contact arm, while field Aedes showed "
            "increased treated escape in the contact arm. Does this isolate contact?",
            "Unmated Aedes matched control without contact, while mated Aedes showed higher "
            "treated escape with contact. Can the result be attributed to contact?",
            "One operator ran the no-contact Aedes arm and another operator ran the contact "
            "arm, where treatment escape increased. Is contact isolated?",
            "In a Culex tarsalis assay, treatment escape matched control without contact and "
            "exceeded control with contact. What does that pattern support?",
            "Ochlerotatus triseriatus treatment matched control for no-contact escape but "
            "produced higher treated escape with contact. How should we interpret it?",
            "culex tarsalis matched control without contact, while treated escape was higher "
            "than control with contact. What can be inferred?",
            "Aedes albopictus treatment escape matched control without contact and exceeded "
            "control with contact. How should this species result be interpreted?",
            "Rockefeller-strain Aedes aegypti matched control without contact, whereas New "
            "Orleans-strain females had increased treatment escape versus control with "
            "contact. Does that isolate a contact response?",
            "Freshly treated paper produced no escape increase over control in the Aedes "
            "aegypti no-contact arm, while paper aged for seven days produced higher "
            "treatment escape than control in the contact arm. Is contact isolated?",
            "Under 50 lux, Aedes aegypti treatment did not increase no-contact escape over "
            "control; under 500 lux, contact treatment increased escape over control. Is "
            "that a clean contact comparison?",
            "Glass Aedes aegypti chambers showed no treatment-control increase without "
            "contact, while acrylic chambers showed greater treatment escape than control "
            "with contact. Can the result be attributed to contact?",
            "The no-contact Aedes aegypti arm used 25 square centimeters of treated paper "
            "and matched control, while the contact arm used 100 square centimeters and "
            "exceeded control for escape. What does this establish?",
            "Aedes aegypti no-contact escape matched control, but treated contact chambers "
            "had more landings than controls. Does that establish increased contact escape?",
            "Antibiotic-treated Aedes aegypti matched control for escape without contact, "
            "while untreated females escaped more from treatment than control with contact. "
            "Is that evidence for a contact effect?",
            "The treated paper was mounted on the ceiling in the Aedes aegypti no-contact "
            "arm, where escape did not increase over control, and on the floor in the contact "
            "arm, where treatment escape exceeded control. Can this be called contact-associated?",
            "Aedes aegypti encountered treated filter paper in the no-contact comparison and "
            "treated cotton fabric in the contact comparison; escape matched control without "
            "contact and exceeded control with contact. Does this isolate contact?",
            "Water-rinsed Aedes aegypti cages showed no treatment-control increase without "
            "contact, while detergent-cleaned cages showed higher treatment escape than "
            "control with contact. Can contact account for the result?",
            "Uninfected Aedes aegypti matched control for no-contact escape, whereas "
            "dengue-infected females showed increased treatment escape over control with "
            "contact. Is the difference attributable to contact?",
            "Aedes aegypti chilled for sorting showed no treatment-control increase in the "
            "no-contact arm, while females tested without chilling showed increased treatment "
            "escape in the contact arm. Can we infer a contact effect?",
            "In an ER run with Uranotaenia sapphirina, no-contact treatment escape matched "
            "control and contact treatment escape was higher than control. What can be concluded?",
            "Aedes aegypti treatment did not increase escape over control without contact, "
            "and contact treatment also matched control for escape. Is a contact increase present?",
            "Aedes aegypti treatment matched control for no-contact escape but produced less "
            "escape than control when contact was allowed. Does this support increased contact escape?",
            "Are tarsal gustatory neurons responsible when Aedes aegypti no-contact escape "
            "shows no treatment-control increase and contact treatment escape exceeds control?",
            "Assay-experienced Aedes aegypti matched control for escape in the no-contact arm, "
            "whereas females tested for the first time escaped more from treatment than control "
            "in the contact arm. Does this isolate contact?",
            "Mated Aedes aegypti had no treatment-control increase in no-contact escape, but "
            "virgin females had higher treatment escape than control in the contact condition. "
            "Can the difference be attributed to contact?",
            "Black-lined Aedes aegypti chambers produced no treatment-control increase in "
            "no-contact escape, while white-lined chambers produced higher treatment escape "
            "than control with contact. Is contact isolated?",
            "The Aedes aegypti no-contact receiving cage was brightly illuminated and treatment "
            "matched control, whereas the contact receiver was dark and treatment escape "
            "exceeded control. Can this be called a contact response?",
            "Aedes aegypti no-contact chambers sat on a vibrating bench and showed no "
            "treatment-control escape increase; contact chambers were vibration-isolated and "
            "showed higher treatment escape than control. What does this establish?",
            "Paper conditioned at 30% relative humidity gave no treatment-control increase in "
            "Aedes aegypti no-contact escape, while paper conditioned at 90% gave greater "
            "treatment escape than control with contact. Can contact explain the result?",
            "A mouth aspirator was used for the Aedes aegypti no-contact groups that matched "
            "control, while a battery aspirator loaded contact groups that showed increased "
            "treatment escape. Does the comparison isolate contact?",
            "Clean gloves handled the Aedes aegypti no-contact papers that matched control, "
            "while scented gloves handled the contact papers that produced increased treatment "
            "escape over control. Is contact responsible?",
            "Aedes aegypti treatment escape did not increase over control without contact, and "
            "it remained equal to control with contact. Is increased contact escape supported?",
            "Does sodium-channel activation cause the Aedes aegypti pattern of unchanged "
            "no-contact escape and increased treatment escape with contact?",
            "Paper lot A gave no treatment-control increase in Aedes aegypti no-contact escape, "
            "while paper lot B gave higher treatment escape than control with contact. Is this "
            "a clean contact comparison?",
            "Transported Aedes aegypti showed no treatment-control increase in no-contact "
            "escape, whereas females reared beside the assay room showed increased treatment "
            "escape with contact. Is this evidence for contact?",
            "Treatment escape stayed at control without contact and rose above control with "
            "contact in Eretmapodites chrysogaster. How should that species result be classified?",
            "The posterior Aedes aegypti contact estimate was positive, but its 95% credible "
            "interval included zero; no-contact escape matched control. Can contact escape "
            "be claimed?",
            "Treatment escape exceeded control for Aedes aegypti with contact absent and with "
            "contact present. Is this contact-only?",
            "Without contact, Aedes aegypti treatment leaving matched control; with contact, "
            "no treatment-related increase in leaving was observed. What does this result "
            "support?",
            "Aedes aegypti escape matched control in the no-contact arm tested with 0.01% "
            "transfluthrin, but exceeded control in the contact arm tested with 0.05% "
            "transfluthrin. Can this be called a contact-only effect?",
            "Aedes aegypti showed equal no-contact escape and greater treated escape with "
            "contact. Was this caused by sodium-channel activation?",
            "Aedes aegypti escape was unchanged without contact, and there was no greater "
            "treatment escape than control after contact. What can be inferred?",
            "Aedes aegypti escape was unchanged behind the barrier, and contact escape "
            "never rose above control under treatment. Does that show contact excitation?",
            "Aedes aegypti showed no no-contact escape increase and greater escape with "
            "contact. Did an odorant-binding protein cause the response?",
            "Aedes aegypti no-contact escape matched control at 0.03% transfluthrin, but "
            "contact escape exceeded control at 0.09%. Does this identify a contact effect?",
            "Aedes aegypti showed no no-contact escape increase and greater escape with "
            "contact. Did a chemosensory protein mediate the response?",
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
                ]
            )
            negative_answers = [
                build_reviewed_science_answer(index, question)
                for question in negative_questions
            ]

        for question, answer in zip(
            negative_questions, negative_answers, strict=True
        ):
            with self.subTest(negative_question=question):
                if answer is not None:
                    self.assertNotIn(
                        "Interpretation of the stated result pattern:",
                        answer["answer"],
                    )

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
        from askinsects.cli import compact_agent_answer

        expected_record_ids = (
            "openalex:W3048721146",
            "openalex:W3179105761",
            "openalex:W4313493759",
            "openalex:W4399119561",
            "openalex:W4403603462",
            "human_repellent_guidance:epa:810.3700",
            "human_repellent_guidance:who:2009.4",
        )
        expected_source_ids = (
            "doi:10.1371/journal.pone.0237353",
            "doi:10.1371/journal.pntd.0009546",
            "doi:10.3390/life13010141",
            "doi:10.1371/journal.pone.0299722",
            "doi:10.1038/s41598-024-74518-x",
            "epa:oppts-810.3700",
            "who:WHO-HTM-NTD-WHOPES-2009.4",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="aedes_literature_openalex",
                        locator=f"records#{record_id}",
                    )
                    for record_id in expected_record_ids
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
                "When evaluating a volatile around Aedes aegypti, why should airflow "
                "and humidity be logged rather than described only as room conditions?",
                "Which plume and temperature conditions should I record and report "
                "when evaluating an airborne Aedes treatment?",
                "Which airflow, plume, temperature, and humidity controls are needed "
                "in an Aedes spatial-repellency assay?",
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertTrue(answer["ok"])
                    self.assertEqual(
                        [item["record_id"] for item in answer["evidence"]],
                        list(expected_record_ids),
                    )
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
                        "cited reviewed Aedes delivery and human-use evidence set",
                        "no complete product-specific",
                        "carrier",
                        "release-rate",
                        "application-method",
                        "delivery evidence package",
                        "applied loading alone as airborne dose",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())
                    final_answer = compact_agent_answer(answer)["final_answer"]
                    for source_id in expected_source_ids:
                        self.assertIn(f"Source ID: `{source_id}`", final_answer)

            unrelated = build_reviewed_science_answer(
                index,
                "How does regional humidity affect Aedes aegypti field abundance?",
            )
            if unrelated is not None:
                self.assertTrue(
                    set(expected_record_ids).isdisjoint(
                        {item["record_id"] for item in unrelated["evidence"]}
                    )
                )

    def test_aedes_co2_spectral_gating_paraphrases_preserve_endpoint_limits(self):
        record_id = "aedes_primary_behavior:pmc:PMC8816903"
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="aedes_primary_behavior_evidence",
                        locator="https://pmc.ncbi.nlm.nih.gov/articles/PMC8816903/#Sec3",
                    )
                ]
            )
            questions = (
                "In the wind-tunnel paper, female Aedes aegypti clustered near "
                "600- and 660-nm objects during carbon-dioxide release but not "
                "during filtered air. Does that establish an unconditional "
                "preference for 'red,' and which measured endpoint and controls "
                "limit the claim?",
                "Did Aedes aegypti prefer red objects regardless of odor, or was "
                "the 600 to 660 nm response gated by CO2 in the wind tunnel?",
                "How do the white control, 496 nm response, and filtered-air phase "
                "limit claims about Aedes color attraction?",
                "Were cyan and long-wavelength visual objects attractive to Aedes "
                "aegypti only after the plume arrived?",
                "Did host odor gate Aedes aegypti attraction to orange and cyan "
                "visual targets?",
                "Did CO2 make Aedes aegypti respond to red objects?",
                "How did carbon dioxide affect Aedes aegypti behavior around "
                "different wavelengths?",
                "Did Aedes aegypti spend longer around 660-nm objects while carbon "
                "dioxide was on?",
                "Did Aedes aegypti approach orange targets only with a CO2 plume?",
                "Were Aedes aegypti attracted to red circles after carbon dioxide "
                "exposure?",
                "Did carbon dioxide change Aedes aegypti color preferences?",
                "Did carbon dioxide increase Aedes aegypti visits to red objects?",
                "Were Aedes aegypti drawn to orange circles only after the CO2 plume?",
                "Did CO2 increase Aedes aegypti occupancy around 660-nm targets?",
                "Did Aedes aegypti remain near cyan objects only during carbon "
                "dioxide release?",
                "Did the CO2 plume boost Aedes aegypti visits to long-wavelength "
                "objects?",
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question in questions
            ]
            unrelated_questions = (
                "Does the color of an Aedes aegypti rearing cage change adult emergence?",
                "Should a red visual object be the control in an Aedes aegypti "
                "oviposition assay?",
                "Should a red visual object be the control when measuring Aedes "
                "aegypti adult emergence?",
                "Should Aedes aegypti odor-attraction controls use visual target "
                "markers?",
                "Does red dye affect odor responses in Aedes aegypti larvae?",
                "Does food coloring affect odor response during Aedes aegypti "
                "larval rearing?",
                "Does orange cage paint affect odor-driven oviposition behavior in "
                "Aedes aegypti?",
                "Does red ambient lighting affect adult Aedes aegypti odor responses "
                "in flight?",
                "Does wind-tunnel wall paint change Aedes aegypti odor-tracking "
                "behavior?",
                "Does red camera illumination alter Aedes aegypti odor responses in "
                "a wind tunnel?",
                "Does red clothing change odor-mediated Aedes aegypti biting?",
                "Does odor change color-gene expression in Aedes aegypti?",
                "Does flight-muscle pigmentation affect Aedes aegypti odor behavior?",
                "Can red tracking-hardware lights alter Aedes aegypti odor responses?",
            )
            unrelated_answers = [
                build_reviewed_science_answer(index, question)
                for question in unrelated_questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    [item["record_id"] for item in answer["evidence"]],
                    [record_id],
                )
                evidence = answer["evidence"][0]
                self.assertEqual(
                    evidence["title"],
                    "The olfactory gating of visual preferences to human skin and "
                    "visible spectra in mosquitoes",
                )
                self.assertEqual(
                    evidence["url"],
                    "https://doi.org/10.1038/s41467-022-28195-x",
                )
                self.assertEqual(
                    evidence["provenance"]["source_id"],
                    "doi:10.1038/s41467-022-28195-x",
                )
                self.assertIn(
                    "paragraphs 7-9, Figure 1e-i, and Supplementary Figure S1",
                    evidence["provenance"]["locator"],
                )
                for fragment in (
                    "time a tracked trajectory spent around the test object",
                    "evenly reflecting white control",
                    "1-4%",
                    "ceased after the plume stopped",
                    "600 and 660 nm",
                    "496 nm",
                    "437, 452, 510, and 520 nm",
                    "not an unconditional preference for human-labeled red",
                    "heat, water vapor, or skin volatiles",
                    "landing or biting",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

        from askinsects.cli import compact_agent_answer

        first_answer = answers[0]
        assert first_answer is not None
        final_answer = compact_agent_answer(first_answer)["final_answer"]
        self.assertIn(
            "[The olfactory gating of visual preferences to human skin and visible "
            "spectra in mosquitoes]"
            "(https://doi.org/10.1038/s41467-022-28195-x)",
            final_answer,
        )
        self.assertIn(
            "Source ID: `doi:10.1038/s41467-022-28195-x`",
            final_answer,
        )
        self.assertIn(
            "Locator: `Results, 'Olfactory gating of spectral preferences of Ae. "
            "aegypti mosquitoes,' paragraphs 7-9, Figure 1e-i, and Supplementary "
            "Figure S1; Discussion paragraph beginning 'It is important to note that "
            "our current experiments did not incorporate close-range cues'`",
            final_answer,
        )

        for question, unrelated in zip(
            unrelated_questions, unrelated_answers, strict=True
        ):
            with self.subTest(question=question):
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
                "Which controls are essential in a two-choice SWD oviposition assay?",
                "How should we randomize and replicate an SWD egg-laying choice test, "
                "and which control shows whether total egg output was suppressed?",
                "What vehicle, side-balance, fly-state, and no-choice controls belong "
                "in an SWD treated-fruit preference experiment?",
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
                    self.assertIn(
                        "no single cited paper establishes the following control "
                        "package as a universal standard",
                        answer["answer"].lower(),
                    )
                    self.assertIn("R&D synthesis", answer["answer"])
                    self.assertIn("R&D interpretation", answer["answer"])
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
                "Before field-testing a volatile SWD deterrent in raspberries, what evidence would you require to protect bees, predators, parasitoids, workers, the crop, soil, and nearby water?",
                "How should I test whether an airborne SWD treatment is safe for beneficial insects across their life stages?",
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
                        "Pectis brevipedunculata",
                        "feeding toxicity and diet-consumption",
                        "still killed more bees than the control",
                        "laboratory hazard, expected field exposure, and field risk",
                        "does not establish pollinator safety",
                        "remain evidence needs",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())

    def test_swd_crop_safety_measurement_question_starts_with_measurements(self):
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
            answer = build_reviewed_science_answer(
                index,
                "Which non-target and crop-safety measurements should accompany an SWD repellent field trial?",
            )

            self.assertIsNotNone(answer)
            assert answer is not None
            self.assertTrue(answer["ok"])
            self.assertFalse(answer["answer"].startswith("No."))
            for fragment in (
                "Measure the safety package",
                "non-target species, and life stage",
                "egg hatch, larval development and feeding",
                "pupation and adult emergence",
                "adult orientation and foraging",
                "reproduction, and offspring production",
                "crop injury and fruit quality",
                "residues and worker exposure",
                "field pollinator survival and behavior",
                "survival and behavior of beneficial arthropods",
                "predators and parasitoids",
                "soil exposure",
                "aquatic exposure",
                "does not establish pollinator safety or crop safety",
                "Crop and worker safety plus pollinator",
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
        from askinsects.cli import compact_agent_answer

        record_ids = (
            "openalex:W3048721146",
            "openalex:W3179105761",
            "openalex:W4313493759",
            "openalex:W4399119561",
            "openalex:W4403603462",
            "human_repellent_guidance:epa:810.3700",
            "human_repellent_guidance:who:2009.4",
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
        final_answer = compact_agent_answer(answer)["final_answer"]
        for source_id in (
            "doi:10.1371/journal.pone.0237353",
            "doi:10.1371/journal.pntd.0009546",
            "doi:10.3390/life13010141",
            "doi:10.1371/journal.pone.0299722",
            "doi:10.1038/s41598-024-74518-x",
            "epa:oppts-810.3700",
            "who:WHO-HTM-NTD-WHOPES-2009.4",
        ):
            self.assertIn(f"Source ID: `{source_id}`", final_answer)

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
                    "carrier",
                    "concentration",
                    "spatial delivery",
                    "release rate",
                    "application method",
                    "user-experience evidence",
                    "reviewed-public-evidence coverage gap",
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
                "Our skin repellent passes a standard unchallenged arm test. Can we claim it lasts through sweating, swimming, rubbing, and sun?",
                (
                    "WHO and EPA",
                    "baseline test does not establish",
                    "sweat or water",
                    "rubbing or abrasion",
                    "sunlight or ultraviolet",
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
                    "standardize and record prior odor or repellent exposure",
                    "do not test whether either changes a later repellent response",
                ),
            ),
            (
                "How much can mosquito population, genotype, age, or insecticide-resistance background change a repellent result?",
                "aedes-population-and-state-variation",
                (
                    "5.0%",
                    "54.9%",
                    "0.00852%",
                    "raw contact escape did not differ significantly",
                    "laboratory USDA strain showed contact excitation",
                    "field NON population did not show a contact response",
                    "feeding state, and mating status",
                    "no pairwise feeding-rate comparison was significant",
                    "all selected lines except the 60-ug permethrin line",
                    "internal reporting inconsistency",
                    "Supplementary Table S4C",
                    "adjusted p = 0.8996",
                    "adjusted p = 0.0001",
                    "S4E and S4F",
                    "adjusted p = 0.0004",
                    "adjusted p < 0.0001",
                    "significance of the between-dose contrasts",
                    "source conflict",
                    "does not quantify",
                    "do not assume",
                ),
            ),
            (
                "Could one Aedes aegypti colony mislead a repellent screen? Summarize "
                "the population and resistance-selection evidence, including any "
                "conflicting development statistics.",
                "aedes-population-and-state-variation",
                (
                    "5.0%",
                    "54.9%",
                    "0.00852%",
                    "Supplementary Table S4C",
                    "adjusted p = 0.8996",
                    "adjusted p = 0.0001",
                    "S4E and S4F",
                    "adjusted p = 0.0004",
                    "adjusted p < 0.0001",
                    "source conflict",
                    "do not assume",
                ),
            ),
            (
                "Could one Aedes aegypti colony mislead our repellent screen?",
                "aedes-population-and-state-variation",
                ("5.0%", "54.9%", "do not assume"),
            ),
            (
                "Could relying on a single Aedes aegypti colony mislead a repellent screen?",
                "aedes-population-and-state-variation",
                ("5.0%", "54.9%", "do not assume"),
            ),
            (
                "Should an Aedes aegypti repellent screen include more than one colony?",
                "aedes-population-and-state-variation",
                ("5.0%", "54.9%", "do not assume"),
            ),
            (
                "Do laboratory and field Aedes aegypti populations respond differently "
                "to the same spatial repellent dose?",
                "aedes-population-and-state-variation",
                ("5.0%", "54.9%", "do not assume"),
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
                    "not significantly lower than on the B. oleracea monoculture",
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
                if topic_id == "swd-physiological-state-confounds":
                    self.assertNotIn(
                        "batch",
                        answer["answer"].casefold(),
                    )
                    self.assertIn(
                        "did not test a repellent",
                        answer["answer"].casefold(),
                    )

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
            "When SWD crowding changes in a cage, can total egg count alone "
            "compare repellent treatments across raspberry quality?",
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
            "biological replicate numbers for every laboratory treatment",
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
                "What evidence would distinguish learned habituation from inherited resistance to an SWD repellent?",
                "swd:openalex_literature:openalex:W3199560580",
                (
                    "within-individual or within-generation",
                    "offspring raised without exposure",
                    "selection response",
                    "genetic association",
                    "two-choice gated trap capture",
                    "female survival",
                    "oviposition frequency",
                    "longitudinal behavioral tolerance",
                    "reciprocal crosses",
                    "did not test genetic association",
                    "unexposed-generation",
                ),
            ),
            (
                "How would you test whether declining SWD response to 2-pentylfuran across seasons is behavioral tolerance, cross-resistance, or a heritable field-population shift?",
                "swd:openalex_literature:openalex:W3199560580",
                (
                    "2-pentylfuran",
                    "longitudinal behavioral tolerance",
                    "cross-resistance",
                    "field phenotype frequencies",
                    "common-garden",
                    "reciprocal crosses",
                    "replicated selection lines",
                    "repeatedly sample the same field populations",
                    "matched unexposed reference populations",
                    "other repellents and relevant toxicants",
                    "matched delivered exposures",
                ),
            ),
            (
                "If an SWD line keeps ignoring a deterrent after its offspring are raised without exposure, is that still learning or evidence for inheritance?",
                "swd:openalex_literature:openalex:W3199560580",
                (
                    "offspring raised without exposure",
                    "selection response",
                    "genetic association",
                    "parental effects",
                    "inheritance",
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
                "If two cherry cultivars get similar SWD egg numbers, what larval or pupal readout could still change our product conclusion?",
                "swd_pubmed_literature:pubmed:39769586",
                (
                    "cultivar differences in pupation",
                    "survival rates of 0.51-0.62",
                    "Every prevented egg would not necessarily have become a damaging larva",
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
                "If 1-octen-3-ol works as an SWD oviposition antagonist, what placement and release questions matter before using puffers in raspberries?",
                "swd:openalex_literature:openalex:W3046652911",
                (
                    "source spacing and placement",
                    "release-rate effects",
                    "dawn and dusk",
                    "larger-scale perimeter and placement trials",
                    "time-resolved canopy concentration",
                    "marketable yield",
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
                "If a mosquito product blocks thermal infrared cues, can we claim people are protected without testing CO2, odor, humidity, vision, and biting outcomes?",
                "openalex:W4401794442",
                (
                    "humidity",
                    "vision",
                    "biting",
                    "not enough to claim people are protected",
                    "not a validated stand-alone repellent target",
                ),
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

    def test_anopheles_orco_cell_screen_does_not_rank_behavioral_repellency(self):
        record_ids = (
            "reviewed_repellent_evidence:carvacrol_anopheles_orco_cell_2015",
            "reviewed_repellent_evidence:deet_anopheles_odor_masking_2019",
        )
        questions = (
            (
                "Our cell assay says carvacrol blocks Anopheles gambiae Orco, but DEET "
                "barely does. Can I rank the compounds as repellents from that result, "
                "and how should the DEET masking paper change the follow-up?"
            ),
            (
                "If carvacrol suppresses an Anopheles odorant receptor more strongly "
                "than DEET in cultured cells, does that prove it will prevent more "
                "mosquito bites, or what experiments are still needed?"
            ),
            (
                "Carvacrol looks stronger than DEET against a mosquito odorant "
                "receptor in vitro. Is it therefore the better human repellent, and "
                "what would you test next to avoid confusing receptor inhibition "
                "with odor masking?"
            ),
            (
                "A recombinant Anopheles receptor screen makes carvacrol look stronger "
                "than DEET. In the intact-mosquito masking study, which instrument "
                "actually measured odor delivery, what happened to the attempted GC-MS "
                "method, and can either result rank protection from bites?"
            ),
            (
                "Why do strong carvacrol inhibition in recombinant Anopheles gambiae "
                "receptors and weak direct DEET inhibition not contradict the intact "
                "Anopheles coluzzii odor-masking result? Include what IR3535 and "
                "picaridin did and what behavioral evidence is still missing."
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="reviewed_repellent_evidence",
                        locator=f"records#{record_id}",
                    )
                    for record_id in record_ids
                ]
            )
            for question in questions:
                with self.subTest(question=question):
                    answer = build_reviewed_science_answer(index, question)

                    self.assertIsNotNone(answer)
                    assert answer is not None
                    self.assertEqual(
                        {item["record_id"] for item in answer["evidence"]},
                        set(record_ids),
                    )
                    for fragment in (
                        "Do not rank carvacrol above DEET",
                        "insect-cell expression system",
                        "ethyl cinnamate, carvacrol, and isopropyl cinnamate",
                        "no noticeable inhibitory action",
                        "DEET and IR3535",
                        "picaridin weakly activated",
                        "DEET carried over into subsequent samples",
                        "photoionization detector",
                        "physicochemical masking",
                        "not necessarily contradictory",
                        "mixed-versus-separated host-odor conditions",
                        "orientation, landing, and biting or protection",
                    ):
                        self.assertIn(fragment.casefold(), answer["answer"].casefold())
                    self.assertNotIn("GC-MS volatility measurements", answer["answer"])
                    self.assertNotIn(
                        "eugenol produced a weak response",
                        answer["answer"].casefold(),
                    )
                    masking_source = next(
                        item
                        for item in answer["evidence"]
                        if item["record_id"]
                        == "reviewed_repellent_evidence:deet_anopheles_odor_masking_2019"
                    )
                    self.assertIn(
                        "Methods, Photoionization detector",
                        masking_source["provenance"]["locator"],
                    )
                    self.assertNotIn(
                        "GC-MS volatility measurements",
                        masking_source["provenance"]["locator"],
                    )

    def test_anopheles_deet_time_of_test_routes_to_circadian_retest(self):
        record_id = "reviewed_repellent_evidence:deet_anopheles_time_of_test_2021"
        questions = (
            (
                "A 5% DEET excito-repellency screen run at 14:00 gives a different "
                "ranking from a night run. Is that just assay drift, or can time of "
                "day really change Anopheles contact and noncontact escape? How "
                "should I schedule the retest?"
            ),
            (
                "Could the test period explain why Anopheles minimus contact and "
                "non-contact escape to DEET changed between daytime and nighttime, "
                "and how should I block a repeat?"
            ),
            (
                "Our Anopheles dirus DEET ranking changed at night. What time-matched "
                "controls and mosquito-state variables are needed before calling it "
                "a circadian response?"
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="reviewed_repellent_evidence",
                        locator=f"records#{record_id}",
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
                    "eight 3-hour periods",
                    "Anopheles minimus",
                    "Anopheles dirus",
                    "5% DEET",
                    "time-matched control",
                    "block or randomize",
                    "contact escape, noncontact escape, knockdown, and 24-hour mortality",
                    "does not identify a receptor-level circadian mechanism",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                evidence = answer["evidence"][0]
                self.assertEqual(
                    evidence["provenance"]["source_id"],
                    "doi:10.3390/insects12100867",
                )
                self.assertIn(
                    "Methods Sections 2.2-2.4",
                    evidence["provenance"]["locator"],
                )
                self.assertNotIn(
                    "A non-significant Anopheles DEET comparison",
                    answer["answer"],
                )

    def test_anopheles_eugenol_decisions_preserve_species_and_small_next_step(self):
        record_id = "openalex:W3013059076"
        questions = (
            (
                "Eugenol was a hit in our Aedes screen. For an Anopheles program, "
                "should I carry it straight into a human-landing study, or is there "
                "enough evidence to stop? What is the smallest useful next experiment?"
            ),
            (
                "Aedes responded to eugenol, but should the Anopheles team go "
                "straight to human landing or first run a smaller no-contact study?"
            ),
            (
                "Does eugenol's P = 0.08 Anopheles result mean we should drop it, "
                "or how should dose and release be tested before people are exposed?"
            ),
            (
                "What is the minimum Anopheles go/no-go experiment for eugenol "
                "before a landing assay?"
            ),
            (
                "Before a person enters the experiment, what exact five-arm "
                "Anopheles eugenol decision gate would you preregister, including "
                "H, n, power, model, and disqualifying outcomes?"
            ),
            (
                "What five-arm eugenol decision gate should Anopheles use before "
                "human exposure?"
            ),
            (
                "Build the minimum Anopheles eugenol screen that ends in a hard "
                "advance-or-stop decision before people are involved. Specify "
                "control acceptance, headspace levels, sample count, statistics, "
                "and toxicity vetoes."
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
                        locator="records#W3013059076",
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
                self.assertIn(
                    "Do not carry an Aedes eugenol hit straight into an Anopheles",
                    answer["answer"],
                )
                self.assertIn("undiluted eugenol", answer["answer"])
                self.assertIn("non-blood-fed female", answer["answer"])
                self.assertIn("about 0.5 cm", answer["answer"])
                self.assertIn("30-second", answer["answer"])
                self.assertIn("P = 0.08", answer["answer"])
                self.assertIn("20 uL", answer["answer"])
                self.assertIn("1 x 2 cm", answer["answer"])
                self.assertIn("Anopheles coluzzii Ngousso", answer["answer"])
                self.assertIn("Aedes aegypti LVPib12", answer["answer"])
                self.assertIn("Culex quinquefasciatus Johannesburg", answer["answer"])
                self.assertIn("n = 30", answer["answer"])
                self.assertIn("at least 2 minutes", answer["answer"])
                self.assertIn("Kaplan-Meier estimates", answer["answer"])
                self.assertIn("Cox model included previous odorant exposures", answer["answer"])
                self.assertIn(
                    "1 m dual-port olfactometer",
                    answer["answer"],
                )
                self.assertIn("standardized human-odor blend plus CO2", answer["answer"])
                self.assertIn("0.25, 0.50, and 1.00 times H", answer["answer"])
                self.assertIn("entry into the host-port zone within 5 minutes", answer["answer"])
                self.assertIn("60 females per arm, 300 total", answer["answer"])
                self.assertIn("three biological blocks of 20 per arm", answer["answer"])
                self.assertIn("targets 90% power", answer["answer"])
                self.assertIn("70% vehicle entry from 35% entry", answer["answer"])
                self.assertIn("binomial mixed-effects model", answer["answer"])
                self.assertIn("Dunnett-adjusted simultaneous 95%", answer["answer"])
                self.assertIn("both 0.50H and 1.00H", answer["answer"])
                self.assertIn("negative with P < 0.05", answer["answer"])
                self.assertIn("no more than 5 percentage points above vehicle", answer["answer"])
                self.assertIn("top-dose-only effect", answer["answer"])
                self.assertIn("R&D recommendation", answer["answer"])
                self.assertNotIn("test the intended Aedes population", answer["answer"])
                self.assertEqual(len(answer["evidence"]), 1)
                evidence = answer["evidence"][0]
                self.assertEqual(evidence["record_id"], record_id)
                self.assertEqual(
                    evidence["provenance"]["source_id"],
                    "doi:10.1186/s12936-020-03206-8",
                )
                self.assertEqual(
                    evidence["provenance"]["locator"],
                    "Methods, Mosquitoes: Anopheles coluzzii Ngousso, Aedes aegypti "
                    "LVPib12, and Culex quinquefasciatus Johannesburg 3-10-day-old, "
                    "non-blood-fed, freely mated females; Methods, Odorants: eugenol "
                    "and DEET at 100%; Methods, Close proximity response assay and "
                    "Analysis: 20 uL on 1 x 2 cm filter paper, 0.5 cm from one resting "
                    "mosquito for 30 seconds, n = 30 per experiment, randomized "
                    "odorant order, at least 2 minutes between odorants, paraffin-oil "
                    "control, Kaplan-Meier time-to-flight estimates, and prior "
                    "exposures included in the Cox model; Results, "
                    "Species-specific differences in mosquito behavioural response "
                    "to repellents, Figure 2a-c: Anopheles DEET curve and "
                    "non-significant comparison, Anopheles eugenol P = 0.08, and "
                    "significant Aedes and Culex responses",
                )

    def test_species_transfer_preserves_close_proximity_assay_and_figure_locator(self):
        record_id = "openalex:W3013059076"
        questions = (
            "Does the non-significant Anopheles DEET response mean every mosquito "
            "stayed still, and can that result be assigned to Aedes?",
            "Did every Anopheles coluzzii female remain still near DEET in the "
            "30-second odor assay, or was the result only statistically "
            "non-significant?",
            "Can an Anopheles DEET result be transferred to Aedes?",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="public_literature",
                        locator="records#W3013059076",
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
                for fragment in (
                    "does not mean every mosquito stayed still",
                    "Anopheles coluzzii Ngousso",
                    "Aedes aegypti LVPib12",
                    "Culex quinquefasciatus Johannesburg",
                    "DEET and eugenol were tested at 100%",
                    "20 uL",
                    "1 x 2 cm",
                    "n = 30",
                    "at least 2 minutes",
                    "Cox model included previous exposures",
                    "Figure 2a",
                    "some mosquitoes flew away",
                    "population- and assay-specific",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                self.assertEqual(len(answer["evidence"]), 1)
                evidence = answer["evidence"][0]
                self.assertEqual(evidence["record_id"], record_id)
                self.assertEqual(
                    evidence["provenance"]["source_id"],
                    "doi:10.1186/s12936-020-03206-8",
                )
                locator = evidence["provenance"]["locator"]
                for fragment in (
                    "Methods, Mosquitoes",
                    "Methods, Odorants",
                    "20 uL on 1 x 2 cm filter paper",
                    "n = 30 per experiment",
                    "Kaplan-Meier time-to-flight estimates",
                    "prior exposures included in the Cox model",
                    "Figure 2a-c",
                ):
                    self.assertIn(fragment, locator)

    def test_anopheles_eugenol_assay_preservation_stays_in_requested_scope(self):
        record_id = "openalex:W3013059076"
        questions = (
            "For the 2020 mosquito odor paper, what dose, strains, mosquito state, "
            "reuse, and statistics do I need to preserve before interpreting the "
            "Anopheles eugenol result?",
            "Which Anopheles eugenol assay details and statistical structure must "
            "be preserved before I interpret P = 0.08?",
            "When I cite the Anopheles coluzzii eugenol P value, which exact 2020 "
            "assay conditions and time-to-event analyses must stay attached to it? "
            "Do not design a new study.",
            "Attach the complete experimental context to the 2020 Anopheles eugenol "
            "P = 0.08 result: strains, state, exposure, reuse, Kaplan-Meier, Cox "
            "model, and endpoint. Nothing beyond the paper.",
            "For a methods appendix, attach only the original Anopheles eugenol "
            "assay population, state, exposure, reuse, Kaplan-Meier and Cox details "
            "to P = 0.08.",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        record_id,
                        source_id="public_literature",
                        locator="records#W3013059076",
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
                for fragment in (
                    "Anopheles coluzzii Ngousso",
                    "3-10-day-old, freely mated, non-blood-fed females",
                    "100% undiluted eugenol",
                    "20 uL on 1 x 2 cm",
                    "0.5 cm",
                    "n = 30",
                    "at least 2 minutes",
                    "Kaplan-Meier estimates",
                    "Cox proportional hazards model",
                    "previous odorant exposures",
                    "P = 0.08",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                self.assertNotIn("five-arm", answer["answer"].casefold())
                self.assertNotIn("power", answer["answer"].casefold())
                self.assertNotIn("advance", answer["answer"].casefold())
                self.assertNotIn("Aedes", answer["answer"])
                self.assertNotIn("Culex", answer["answer"])
                self.assertNotIn("host-seeking", answer["answer"].casefold())
                locator = answer["evidence"][0]["provenance"]["locator"]
                self.assertNotIn("Aedes", locator)
                self.assertNotIn("Culex", locator)
                self.assertIn("Figure 2a", locator)

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

    def test_explicit_anopheles_diversion_questions_do_not_route_to_aedes_evidence(self):
        diversion_record_id = (
            "reviewed_repellent_evidence:transfluthrin_anopheles_diversion_2016"
        )
        unrelated_aedes_record_id = "openalex:W3013059076"
        questions = (
            (
                "How should I distinguish true protection from mosquito diversion if a "
                "spatial repellent reduces Anopheles landings in treated huts but may "
                "shift biting toward untreated neighboring huts?"
            ),
            (
                "Could lower Anopheles biting at treated houses merely redirect "
                "blood-seeking mosquitoes to nearby homes without the emanator?"
            ),
            (
                "What study design would tell us whether an Anopheles spatial repellent "
                "protects the community or only protects users at non-users' expense?"
            ),
            (
                "If fewer Anopheles are caught at transfluthrin-treated homes, what "
                "evidence would show whether neighbors without devices receive more "
                "bites rather than there being a net community benefit?"
            ),
            (
                "How can we measure Anopheles spillover or redistribution to untreated "
                "neighbours when only some households use an emanator?"
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        diversion_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[0]",
                    ),
                    evidence_record(
                        unrelated_aedes_record_id,
                        source_id="aedes_literature_openalex",
                        locator=f"records#{unrelated_aedes_record_id}",
                    ),
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
                evidence_ids = {
                    item["record_id"] for item in answer["evidence"]
                }
                self.assertIn(diversion_record_id, evidence_ids)
                self.assertNotIn(unrelated_aedes_record_id, evidence_ids)
                self.assertIn("90 households", answer["answer"])
                self.assertIn("24 weeks", answer["answer"])
                self.assertIn("incomplete coverage", answer["answer"])
                self.assertIn("do not prove community protection", answer["answer"])
                self.assertIn(
                    "six of the 30 households in each village-period were randomly selected",
                    answer["answer"],
                )
                self.assertIn(
                    "It was not an increase in mosquito density",
                    answer["answer"],
                )
                self.assertIn(
                    "This was not an edge-of-treated-area experiment",
                    answer["answer"],
                )
                self.assertIn(
                    "Its density did not remain unchanged",
                    answer["answer"],
                )
                self.assertIn("IRRs 1.44, 1.63, and 1.56", answer["answer"])
                self.assertIn("IRRs 1.35 and 1.39", answer["answer"])
                self.assertNotIn(
                    "coils did not change anopheles funestus density",
                    answer["answer"].lower(),
                )
                diversion_evidence = next(
                    item
                    for item in answer["evidence"]
                    if item["record_id"] == diversion_record_id
                )
                self.assertIn(
                    "Tables 2 and 4-6",
                    diversion_evidence["provenance"]["locator"],
                )

    def test_anopheles_hut_endpoints_do_not_become_malaria_case_predictions(self):
        guardian_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_guardian_anopheles_hut_2025"
        )
        kenya_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_kenya_malaria_cluster_trial_2025"
        )
        recommendation_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_who_spatial_emanator_recommendation_2025"
        )
        guardian_pq_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_who_guardian_prequalification_2025"
        )
        guardian_assessment_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_who_guardian_efficacy_assessment_2025"
        )
        equivalence_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_who_spatial_emanator_equivalence_guidance_2025"
        )
        module5_record_id = (
            "reviewed_repellent_evidence:"
            "transfluthrin_who_spatial_emanator_module5_2025"
        )
        broad_questions = (
            (
                "Our one-year hut trial shows 82.7% less blood feeding, 65.1% "
                "less landing, and 20.1% mortality in wild pyrethroid-resistant "
                "Anopheles arabiensis. Can I project an 82.7% reduction in "
                "malaria cases, or what evidence should gate the program decision?"
            ),
            (
                "A transfluthrin emanator cut Anopheles blood feeding by 70% in "
                "experimental huts. Is it defensible to claim 70% fewer malaria "
                "infections, or what trial must come next?"
            ),
            (
                "How should we bridge Anopheles landing, blood-feeding, and "
                "mortality endpoints from a hut trial to a malaria public-health "
                "claim for a spatial repellent?"
            ),
            (
                "Can I add lower Anopheles landing, lower blood feeding, and "
                "higher mortality to predict the malaria impact of a new "
                "transfluthrin product?"
            ),
        )
        who_questions = (
            (
                "If a new Anopheles spatial repellent outperforms a product class "
                "with clinical evidence on hut blood-feeding, is that enough to "
                "skip a community infection trial?"
            ),
            (
                "Can a same-active-ingredient equivalence argument get our "
                "transfluthrin emanator through WHO prequalification without "
                "candidate-specific mosquito studies?"
            ),
            (
                "What evidence did WHO actually use to prequalify Guardian, and "
                "did the Guardian-versus-Mosquito-Shield hut comparison carry "
                "the decision?"
            ),
            (
                "WHO prequalified Guardian even though its direct comparison with "
                "Mosquito Shield was not used in the decision. What candidate-specific "
                "tests made that bridge defensible, and what malaria claim would "
                "still be unsupported?"
            ),
            (
                "We have a new transfluthrin emanator that reduced blood feeding "
                "more than Guardian in Anopheles huts. Can we use Guardian and "
                "Mosquito Shield to avoid an infection trial, and what exact "
                "evidence would WHO still expect?"
            ),
            (
                "Which exact efficacy studies did WHO rely on for Guardian, and "
                "can a stronger head-to-head comparison replace the new product's "
                "own dossier?"
            ),
        )
        kenya_questions = (
            (
                "Which product and final malaria estimates belong to the Kenya "
                "spatial-repellent trial, and how far can I bridge them to a new "
                "Anopheles product?"
            ),
            (
                "The Kenya spatial-repellent trial quotes 33.4% in its summary but "
                "32.7% in the final results. Which estimate should anchor our "
                "decision, what was the tested product and deployment, and can we "
                "apply the number to Guardian?"
            ),
            (
                "Should I use the interim or final Mosquito Shield malaria result, "
                "and does that percentage transfer to Guardian?"
            ),
            (
                "Which version of the Kenya Mosquito Shield efficacy estimate "
                "belongs in a development memo, and why can\u2019t I assign it to "
                "another transfluthrin product?"
            ),
            (
                "Can I attribute Mosquito Shield's Kenya malaria efficacy to a "
                "different transfluthrin emanator in our portfolio?"
            ),
            (
                "How should I report the western Kenya interim and final infection "
                "estimates, and may I extrapolate them to a new formulation?"
            ),
            (
                "A candidate uses transfluthrin too. Can its malaria efficacy be "
                "inherited from the Kenya Mosquito Shield trial?"
            ),
        )
        unrelated_kenya_question = (
            "Which version of our product memo should I assign to the Kenya team?"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    evidence_record(
                        guardian_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[0]",
                    ),
                    evidence_record(
                        kenya_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[1]",
                    ),
                    evidence_record(
                        recommendation_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[2]",
                    ),
                    evidence_record(
                        guardian_pq_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[3]",
                    ),
                    evidence_record(
                        guardian_assessment_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[4]",
                    ),
                    evidence_record(
                        equivalence_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[5]",
                    ),
                    evidence_record(
                        module5_record_id,
                        source_id="reviewed_repellent_evidence",
                        locator="jsonpath=$.evidence[6]",
                    ),
                ]
            )

            broad_answers = [
                build_reviewed_science_answer(index, question)
                for question in broad_questions
            ]
            who_answers = [
                build_reviewed_science_answer(index, question)
                for question in who_questions
            ]
            kenya_answers = [
                build_reviewed_science_answer(index, question)
                for question in kenya_questions
            ]
            unrelated_kenya_answer = build_reviewed_science_answer(
                index,
                unrelated_kenya_question,
            )

        for question, answer in zip(broad_questions, broad_answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertIn(
                    "is not a percentage reduction in malaria cases",
                    answer["answer"],
                )
                self.assertIn("82.7%", answer["answer"])
                self.assertIn("65.1%", answer["answer"])
                self.assertIn("20.1% mortality", answer["answer"])
                self.assertIn("They cannot be added", answer["answer"])
                self.assertIn("Funding section says no financial support", answer["answer"])
                self.assertIn("Mosquito Shield, not Guardian", answer["answer"])
                self.assertIn("32.7% lower first-time", answer["answer"])
                self.assertIn("29.5% lower overall", answer["answer"])
                self.assertIn("33.4% and 32.1% values were interim", answer["answer"])
                self.assertIn("P-12643", answer["answer"])
                self.assertIn("not used to inform the decision", answer["answer"])
                self.assertIn("at least three semi-field studies", answer["answer"])
                self.assertIn("target-setting randomized community trial", answer["answer"])
                evidence_by_id = {
                    item["record_id"]: item for item in answer["evidence"]
                }
                self.assertEqual(
                    set(evidence_by_id),
                    {
                        guardian_record_id,
                        kenya_record_id,
                        recommendation_record_id,
                        guardian_pq_record_id,
                        guardian_assessment_record_id,
                        equivalence_record_id,
                        module5_record_id,
                    },
                )
                self.assertEqual(
                    evidence_by_id[guardian_record_id]["provenance"]["source_id"],
                    "doi:10.3389/fmala.2025.1570480",
                )
                self.assertIn(
                    "Funding and Conflict of interest",
                    evidence_by_id[guardian_record_id]["provenance"]["locator"],
                )
                self.assertEqual(
                    evidence_by_id[kenya_record_id]["provenance"]["source_id"],
                    "doi:10.1016/S0140-6736(24)02253-0",
                )
                self.assertIn(
                    "final 32.7% first-time and 29.5% overall",
                    evidence_by_id[kenya_record_id]["provenance"]["locator"],
                )
                self.assertEqual(
                    evidence_by_id[guardian_pq_record_id]["provenance"]["source_id"],
                    "who:P-12643",
                )
                self.assertIn(
                    "Table 7 on page 17",
                    evidence_by_id[guardian_assessment_record_id]["provenance"][
                        "locator"
                    ],
                )
                self.assertIn(
                    "Section 9, page 20",
                    evidence_by_id[equivalence_record_id]["provenance"]["locator"],
                )
                self.assertIn(
                    "Data requirements 5.1 and 5.2",
                    evidence_by_id[module5_record_id]["provenance"]["locator"],
                )

        for question, answer in zip(who_questions, who_answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertIn(
                    "not, by itself, an accepted bridge",
                    answer["answer"],
                )
                self.assertIn("P-12643", answer["answer"])
                self.assertIn("BIT084 NI", answer["answer"])
                self.assertIn("not used to inform the decision", answer["answer"])
                self.assertIn("equivalence-only dossier", answer["answer"])
                self.assertIn("at least three semi-field studies", answer["answer"])
                self.assertIn("32.7% lower first-time infection", answer["answer"])
                self.assertIn("29.5% lower overall new infection", answer["answer"])
                evidence_by_id = {
                    item["record_id"]: item for item in answer["evidence"]
                }
                self.assertEqual(
                    set(evidence_by_id),
                    {
                        kenya_record_id,
                        recommendation_record_id,
                        guardian_pq_record_id,
                        guardian_assessment_record_id,
                        equivalence_record_id,
                        module5_record_id,
                    },
                )
                self.assertNotIn(guardian_record_id, evidence_by_id)

        for question, answer in zip(kenya_questions, kenya_answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertIn("Use the final analysis", answer["answer"])
                self.assertIn(
                    "32.7% (95% two-sided CI 12.6%-48.2%",
                    answer["answer"],
                )
                self.assertIn("29.5% (95% CI 12.0%-43.5%", answer["answer"])
                self.assertIn(
                    "33.4% first-time and 32.1% overall values were",
                    answer["answer"],
                )
                self.assertIn("29 clusters per arm", answer["answer"])
                self.assertIn("two units per 9 square metres", answer["answer"])
                self.assertIn("Do not apply 32.7% or 29.5% to Guardian", answer["answer"])
                evidence_by_id = {
                    item["record_id"]: item for item in answer["evidence"]
                }
                self.assertEqual(
                    set(evidence_by_id),
                    {
                        kenya_record_id,
                        guardian_pq_record_id,
                        guardian_assessment_record_id,
                    },
                )
        if unrelated_kenya_answer is not None:
            self.assertNotIn(
                kenya_record_id,
                {
                    item["record_id"]
                    for item in unrelated_kenya_answer.get("evidence", [])
                },
            )

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
                self.assertEqual(
                    evidence["provenance"]["locator"],
                    "Abstract: five cultivars over seven weeks; interior and border rows; "
                    "top/bottom by north/south canopy; low-, later-, and high-density "
                    "distribution and aggregation results",
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
                "A DBM odorant receptor responds to an aromatic volatile in oocytes and females avoid the odor in a choice assay. Is that enough to call the receptor a field repellent target?",
                "dbm:openalex:W4285394072",
                (
                    "PxylOR11",
                    "Xenopus",
                    "dual-choice",
                    "did not use a receptor knockout",
                    "field dose",
                    "crop protection",
                ),
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
        from askinsects.cli import compact_agent_answer

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
            "swd:openalex_literature:openalex:W3046652911": (
                "doi:10.1002/ps.6028",
                "https://doi.org/10.1002/ps.6028",
                "2016 and 2017 raspberry field trials",
            ),
            "swd_primary_field:doi:10.3390/insects11080536": (
                "doi:10.3390/insects11080536",
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC7469169/",
                "blueberry and raspberry field-trial",
            ),
            "swd_primary_field:doi:10.3390/insects8040117": (
                "doi:10.3390/insects8040117",
                "https://doi.org/10.3390/insects8040117",
                "laminate polymer flake raspberry choice assay",
            ),
            "swd_primary_field:doi:10.1093/jee/tow116": (
                "doi:10.1093/jee/tow116",
                "https://doi.org/10.1093/jee/tow116",
                "nontarget-effects sections",
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
                "Figure 1F and Supplementary Figures S1E-S1G",
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
                {
                    "swd:openalex_literature:openalex:W4411730655",
                    "swd:openalex_literature:openalex:W3046652911",
                    "swd_primary_field:doi:10.3390/insects11080536",
                    "swd_primary_field:doi:10.3390/insects8040117",
                },
                (
                    "fewer pupae",
                    "2-component deterrent push (2c)",
                    "combined push-pull (2c + 4c)",
                    "lure-only pull arm (4c) did not differ from control",
                    "cited reviewed SWD field evidence set",
                    "no replicated field evidence",
                    "crop damage",
                    "marketable yield",
                    "persistence",
                    "operational fit",
                    "commercial crop-protection",
                ),
            ),
            (
                "What follow-up measurements connect SWD oviposition deterrence "
                "to actual crop protection?",
                {
                    "swd:openalex_literature:openalex:W4411730655",
                    "swd:openalex_literature:openalex:W3046652911",
                    "swd_primary_field:doi:10.3390/insects11080536",
                    "swd_primary_field:doi:10.3390/insects8040117",
                },
                (
                    "larval or pupal emergence",
                    "2-component deterrent push (2c)",
                    "combined push-pull (2c + 4c)",
                    "lure-only pull arm (4c) did not differ from control",
                    "cited reviewed SWD field evidence set",
                    "no replicated field evidence",
                    "crop damage",
                    "marketable yield",
                    "persistence",
                    "operational fit",
                ),
            ),
            (
                "If a fall raspberry SWD oviposition deterrent reduced eggs, "
                "can we ignore non-target captures and deployment context?",
                {"swd_primary_field:doi:10.1093/jee/tow116"},
                (
                    "No.",
                    "fall-bearing red raspberry",
                    "potential nontarget effects",
                    "deployment method",
                ),
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
                ("locomotor", "host-odor", "blood-feeding", "entrainment history"),
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
                final_answer = compact_agent_answer(answer)["final_answer"]
                for record_id in expected_record_ids:
                    source_id = records[record_id][0]
                    self.assertIn(f"Source ID: `{source_id}`", final_answer)

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

    def test_ecotrol_field_result_keeps_crop_and_comparator_claims_separate(self):
        from askinsects.cli import compact_agent_answer
        from askinsects.sources.swd_primary_field_evidence import (
            ECOTROL_FIELD_RECORD_ID,
            build_swd_primary_field_evidence_records,
        )

        questions = (
            "We got a raspberry signal with Ecotrol PLUS at 3.5 L/ha. Is that "
            "enough to advance the same spray program for half-high blueberry, "
            "and was its raspberry performance actually equivalent to spinosad?",
            "Can the Ecotrol raspberry field result be transferred to blueberries "
            "or treated as equivalence with spinosad?",
            "Was Ecotrol PLUS effective across berry crops because its raspberry "
            "mean matched the spinosad mean?",
        )
        negative_questions = (
            "Which Ecotrol ingredient has the lowest boiling point?",
            "Did spinosad cause mortality in a laboratory vial bioassay?",
            "How should blueberry firmness be measured?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                build_swd_primary_field_evidence_records(
                    retrieved_at="2026-07-20T00:00:00Z"
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

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {ECOTROL_FIELD_RECORD_ID},
                )
                for fragment in (
                    "do not advance",
                    "sentinel raspberries",
                    "equivalence or noninferiority",
                    "p = 0.909",
                    "not blueberry efficacy",
                ):
                    self.assertIn(fragment, answer["answer"].casefold())
                final_answer = compact_agent_answer(answer)["final_answer"]
                self.assertIn(
                    "(https://pmc.ncbi.nlm.nih.gov/articles/PMC7469169/)",
                    final_answer,
                )
                self.assertIn(
                    "Source ID: `doi:10.3390/insects11080536`",
                    final_answer,
                )
                self.assertIn("Locator: `Table 1", final_answer)

        for question, answer in zip(negative_questions, negatives, strict=True):
            with self.subTest(question=question):
                if answer is not None:
                    self.assertNotIn(
                        ECOTROL_FIELD_RECORD_ID,
                        {item["record_id"] for item in answer["evidence"]},
                    )

    def test_laminate_flake_questions_route_to_primary_delivery_evidence(self):
        from askinsects.cli import compact_agent_answer
        from askinsects.sources.swd_primary_field_evidence import (
            LAMINATE_FLAKE_FIELD_RECORD_ID,
            build_swd_primary_field_evidence_records,
        )

        questions = (
            "A flake formulation with SWD deterrent compounds lowered berry "
            "infestation. What evidence says the flake is doing repellent work "
            "rather than just being another insecticide, and what would still be "
            "missing for a grower recommendation?",
            "Do laminate polymer flakes with thymol or peppermint prove a "
            "non-toxic SWD repellent, or do we still need a crop recommendation "
            "gate?",
            "If treated flakes reduced strawberry infestation at four days, can "
            "we recommend them to growers or do we need persistence and field "
            "validation first?",
        )
        negative_questions = (
            "Which polymer has the best thermal stability for food packaging?",
            "How should I identify spotted wing drosophila in a monitoring trap?",
            "Which lavender essential oil supplier sells the cheapest flake?",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                build_swd_primary_field_evidence_records(
                    retrieved_at="2026-07-21T00:00:00Z"
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

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {LAMINATE_FLAKE_FIELD_RECORD_ID},
                )
                for fragment in (
                    "not as proof",
                    "increased fly mortality",
                    "reduced larval infestation by 25% at four days",
                    "not at seven days",
                    "release rate and persistence",
                    "do not recommend",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                final_answer = compact_agent_answer(answer)["final_answer"]
                self.assertIn(
                    "[Reduced Drosophila suzukii Infestation in Berries Using "
                    "Deterrent Compounds and Laminate Polymer Flakes]"
                    "(https://doi.org/10.3390/insects8040117)",
                    final_answer,
                )
                self.assertIn(
                    "Source ID: `doi:10.3390/insects8040117`",
                    final_answer,
                )
                self.assertIn("Locator: `Abstract and Results", final_answer)

        for question, answer in zip(negative_questions, negatives, strict=True):
            with self.subTest(question=question):
                if answer is not None:
                    self.assertNotIn(
                        LAMINATE_FLAKE_FIELD_RECORD_ID,
                        {item["record_id"] for item in answer["evidence"]},
                    )

    def test_hanseniaspora_lure_downselection_preserves_specificity_tradeoff(self):
        from askinsects.cli import compact_agent_answer

        record_id = "swd:openalex_literature:openalex:W4213332511"
        questions = (
            "For the pull stations in an SWD push-pull field trial, should we "
            "advance the seven-component Hanseniaspora uvarum synthetic lure "
            "instead of H. uvarum headspace because it catches more SWD, or does "
            "the specificity tradeoff require a different next gate?",
            "Should we select the seven component H. uvarum synthetic blend over "
            "headspace because it catches more spotted wing drosophila despite "
            "lower specificity?",
            "How should we downselect an SWD pull lure after H. uvarum headspace "
            "had less bycatch but the synthetic lure caught more target flies?",
            "Which H. uvarum volatile formulation should we take forward for SWD "
            "trapping if higher capture comes with greater non-target catch?",
            "Should we move ahead with the seven-compound H. uvarum odor blend if "
            "it attracts more SWD but also more nontarget insects?",
            "For SWD, should we advance H. uvarum headspace because it reduces "
            "Drosophila melanogaster bycatch and has higher selectivity?",
            "For an SWD pull lure, would you pick H. uvarum synthetic volatiles "
            "over collected headspace when target catch rises but nontarget catch "
            "rises too? What should the next experiment require?",
            "For an SWD pull-lure field trial with control traps, should we pick "
            "H. uvarum synthetic volatiles over collected headspace when target "
            "catch rises but nontarget catch rises too?",
            "For SWD, should we advance H. uvarum headspace because it has higher "
            "specificity, and what control treatment should the next experiment include?",
            "Should we compare H. uvarum headspace with the reference lure before "
            "choosing for SWD, given the bycatch difference?",
            "Should we choose H. uvarum headspace versus the reference lure for "
            "SWD based on specificity and bycatch?",
            "For SWD, should we advance H. uvarum headspace or the reference lure, "
            "considering the bycatch difference?",
            "Given its higher specificity, should we advance H. uvarum headspace "
            "for SWD?",
            "Because H. uvarum headspace has higher specificity, should we advance "
            "it for SWD?",
            "Between H. uvarum headspace and the reference lure, which should we "
            "choose for SWD based on specificity and bycatch?",
            "Which should we choose based on specificity and bycatch: H. uvarum "
            "headspace or the reference lure for SWD?",
            "Should we advance H. uvarum headspace for SWD based on target catch "
            "and bycatch?",
            "Would you recommend H. uvarum headspace over the reference lure given "
            "lower bycatch?",
            "Should we favor H. uvarum headspace over the reference lure because "
            "of lower bycatch?",
            "Is H. uvarum headspace the better choice than the reference lure given "
            "higher specificity?",
            "Should we advance the synthetic H. uvarum blend over headspace because "
            "catch is higher despite lower specificity, while keeping Riga bait as "
            "a control?",
            "Would you prefer H. uvarum headspace or the reference lure for SWD, "
            "given lower bycatch?",
            "Would you go with H. uvarum headspace over the reference lure given "
            "lower bycatch?",
            "Should we move forward with H. uvarum headspace rather than the "
            "reference lure because bycatch is lower?",
            "Should H. uvarum headspace be recommended over the reference lure for "
            "SWD given lower bycatch?",
            "Should H. uvarum headspace be favored over the reference lure for SWD "
            "because specificity is higher?",
            "Should H. uvarum headspace be advanced over the reference lure for SWD "
            "given lower bycatch?",
            "Should H. uvarum headspace be taken forward instead of the reference "
            "lure for SWD given lower bycatch?",
            "Would you recommend moving forward with H. uvarum headspace over the "
            "reference lure for SWD given lower bycatch?",
            "Should H. uvarum headspace now be recommended over the reference lure "
            "for SWD given lower bycatch?",
            "Which of H. uvarum headspace and the reference lure should we choose for "
            "SWD given the bycatch difference?",
            "Should we take H. uvarum headspace forward instead of the reference lure "
            "for SWD given lower bycatch?",
            "Should we move H. uvarum headspace forward instead of the reference lure "
            "for SWD given lower bycatch?",
            "Based on target catch and bycatch, is H. uvarum headspace the formulation "
            "we should advance for SWD?",
        )
        negative_questions = (
            "How can Hanseniaspora uvarum be genetically modified for wine fermentation?",
            "Which medium gives the fastest H. uvarum culture growth?",
            "Should we select H. uvarum as a lure for a D. suzukii attract-and-kill assay?",
            "Should we choose an H. uvarum lure to study SWD olfaction?",
            "Should we choose H. uvarum headspace for Drosophila melanogaster "
            "because it has higher selectivity?",
            "Should we choose H. uvarum headspace for Drosophila biarmipes "
            "because it has higher selectivity?",
            "For SWD, should we advance H. uvarum headspace as the negative control "
            "for measuring nontarget catch?",
            "For an SWD olfaction assay, which H. uvarum headspace dilution should "
            "we pick as the specificity control?",
            "For SWD, should H. uvarum headspace be the calibration control in a "
            "specificity model when target catch rises?",
            "For SWD, can H. uvarum headspace serve as the untreated control for "
            "bycatch counts in the next experiment?",
            "Should we pick a synthetic H. uvarum headspace formulation as a "
            "control for SWD specificity measurements?",
            "Should synthetic H. uvarum headspace be the control used for "
            "calibration in an SWD specificity model when target catch rises?",
            "Should we pick synthetic H. uvarum headspace as the vehicle control "
            "when measuring SWD bycatch?",
            "Should we pick H. uvarum headspace with six replicates for an SWD "
            "specificity assay?",
            "Should we pick H. uvarum headspace for an SWD specificity assay "
            "between 9 and 10 AM?",
            "Should we pick H. uvarum headspace as a vehicle control for SWD "
            "specificity because more technicians are available?",
            "For an SWD H. uvarum headspace specificity assay, should we pick six "
            "replicates because higher catch variance requires more observations?",
            "For an SWD specificity assay, should we pick six replicates and plot "
            "H. uvarum headspace against the reference lure?",
            "For an SWD trial where bycatch and specificity differ, should we select "
            "H. uvarum headspace samples for GC-MS analysis?",
            "Should we choose H. uvarum headspace vials for chemical analysis because "
            "bycatch and specificity differ?",
            "For an SWD report on specificity and bycatch, should we select H. uvarum "
            "headspace rows for the summary table?",
            "In Drosophila melanogaster, would you recommend H. uvarum headspace "
            "over the reference lure given lower bycatch?",
            "When trapping D. biarmipes, should we favor H. uvarum headspace over "
            "the reference lure because bycatch is lower?",
            "For Drosophila simulans, should we recommend H. uvarum headspace over "
            "the reference lure given lower bycatch?",
            "Should we select H. uvarum headspace chromatograms for an SWD "
            "specificity/bycatch figure?",
            "Should we choose H. uvarum headspace footage for a slide about SWD "
            "specificity and bycatch?",
            "Should we pick H. uvarum headspace to serve as the negative control "
            "because nontarget catch is higher?",
            "Should we choose H. uvarum headspace as our specificity control because "
            "bycatch is lower?",
            "For an SWD report where specificity and bycatch differ, should we select "
            "the spectra from H. uvarum headspace for the summary figure?",
            "For an SWD specificity and bycatch analysis, should we choose the GC-MS "
            "peaks from H. uvarum headspace for the results section?",
            "For SWD specificity and bycatch measurements, should we select the "
            "negative control containing H. uvarum headspace because target catch "
            "is higher?",
            "For the SWD specificity and bycatch report, should we select the odor "
            "profile from H. uvarum headspace over the reference profile?",
            "Which H. uvarum headspace should we select for GC-MS when SWD "
            "specificity and bycatch differ?",
            "H. uvarum headspace had lower bycatch in SWD traps; should we select it "
            "for chemical profiling?",
            "Between H. uvarum headspace and the reference lure, which chromatogram "
            "should we select for the SWD specificity and bycatch figure?",
            "Is H. uvarum headspace the better choice of negative control for an SWD "
            "specificity assay because bycatch is higher?",
            "For an SWD specificity and bycatch analysis, should we select the "
            "component from H. uvarum headspace with the strongest GC-MS peak?",
            "Should we select H. uvarum headspace for the SWD negative control "
            "because bycatch is higher?",
            "Should a mosquito repellent be tested in a wind tunnel?",
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
                ]
            )
            answers = [
                build_reviewed_science_answer(index, question)
                for question in questions
            ]
            negatives = [
                build_reviewed_science_answer(index, question)
                for question in negative_questions
            ]

        for question, answer in zip(questions, answers, strict=True):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["answer_shape"], "reviewed_science")
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    {record_id},
                )
                for fragment in (
                    "do not advance",
                    "85 SWD",
                    "148",
                    "significantly less specific",
                    "drowning solution",
                    "approximately 20-ng/uL",
                    "approximately 100-ug/uL",
                    "fruit infestation, damage, and marketable yield",
                    "not crop protection",
                ):
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())
                final_answer = compact_agent_answer(answer)["final_answer"]
                self.assertIn(
                    "[Hanseniaspora uvarum Attracts Drosophila suzukii "
                    "(Diptera: Drosophilidae) With High Specificity]"
                    "(https://pmc.ncbi.nlm.nih.gov/articles/PMC9365507/)",
                    final_answer,
                )
                self.assertIn(
                    "Source ID: `doi:10.1093/jee/toac029`",
                    final_answer,
                )
                self.assertIn(
                    "Locator: `Methods: Field Comparison of Riga bait and H. uvarum Culture",
                    final_answer,
                )

        for question, answer in zip(negative_questions, negatives, strict=True):
            with self.subTest(question=question):
                if answer is not None:
                    self.assertNotIn(
                        record_id,
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
            "Methods: Field Comparison of Riga bait and H. uvarum Culture, Wind "
            "Tunnel Tests, and Field Comparison of H. uvarum Headspace "
            "Extract, H. uvarum-Based Synthetic Blend and a Reference Blend; "
            "Table 1; Results and Figures 1-3; Discussion paragraphs on "
            "drowning-solution contribution and blend optimization",
        )

        fruit_injury = provenance[
            "swd:openalex_literature:openalex:W3163892682"
        ]
        self.assertEqual(
            fruit_injury["title"],
            "Mind the Wound!—Fruit Injury Ranks Higher than, and Interacts with, "
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
        self.assertIn("Figure 1F", vision["locator"])
        self.assertIn("Supplementary Figures S1E-S1G", vision["locator"])
        self.assertIn("Supplementary Figures S1I and S2J", vision["locator"])
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

    def test_swd_state_questions_do_not_inherit_unmentioned_batch_context(self):
        record_id = "swd:openalex_literature:openalex:W3161910963"

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
                ]
            )
            broad = build_reviewed_science_answer(
                index,
                "How could age, mating status, hunger, or prior egg laying change an SWD repellent result?",
            )
            explicit = build_reviewed_science_answer(
                index,
                "Can an SWD assay with fed virgins be compared directly with one using starved mated gravid females?",
            )

        self.assertIsNotNone(broad)
        self.assertIsNotNone(explicit)
        assert broad is not None and explicit is not None
        self.assertNotEqual(broad["answer"], explicit["answer"])
        self.assertNotIn("batch", broad["answer"].casefold())
        self.assertIn("did not test a repellent", broad["answer"].casefold())
        self.assertIn(
            "do not treat a contrast between batches",
            explicit["answer"].casefold(),
        )
        self.assertIn("did not directly compare", explicit["answer"].casefold())

    def test_reality_eval_repairs_generalize_to_neighboring_paraphrases(self):
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        topics = {topic["id"]: topic for topic in catalog["topics"]}
        cases = (
            (
                "In the 2025 raspberry push-pull field trial, which SWD treatment "
                "arms actually reduced pupal emergence versus untreated control, "
                "and which arm did not? Keep naturally ripening and sentinel fruit "
                "in scope.",
                "swd-push-pull-treatment-comparison",
                (
                    "2-component deterrent push (2c)",
                    "combined push-pull treatment (2c + 4c)",
                    "lure-only pull treatment (4c) did not differ",
                    "naturally ripening field raspberries",
                    "store-bought sentinel raspberries",
                    "53.9% lower",
                    "36.0% lower",
                    "79.5%",
                    "70.9%",
                ),
            ),
            (
                "Did every treated raspberry arm reduce SWD pupae, or did the "
                "4c pull-only treatment remain equal to control while 2c push and "
                "2c plus 4c push-pull worked?",
                "swd-push-pull-treatment-comparison",
                (
                    "2-component deterrent push (2c)",
                    "combined push-pull treatment (2c + 4c)",
                    "lure-only pull treatment (4c) did not differ",
                    "did not demonstrate added infestation reduction",
                ),
            ),
            (
                "The 2c SWD push reduced pupae in raspberries. What additional "
                "damage, yield, persistence, and operational evidence is needed "
                "before a crop-protection claim?",
                "swd-eggs-to-crop-protection",
                (
                    "Published evidence:",
                    "53.9%",
                    "36.0%",
                    "79.5%",
                    "70.9%",
                    "Evidence still needed:",
                    "fruit damage and decay",
                    "marketable yield",
                    "release rate",
                    "weather",
                    "R&D requirements",
                ),
            ),
            (
                "What evidence is still missing before we call lower SWD pupal "
                "emergence crop protection: harvest loss, durability, field "
                "deployment, or repeatability across sites?",
                "swd-eggs-to-crop-protection",
                (
                    "Published evidence:",
                    "Evidence still needed:",
                    "rejected fruit",
                    "economic loss",
                    "retreatment interval",
                    "crop, cultivar, season, and site",
                ),
            ),
            (
                "What else must a raspberry SWD deterrent demonstrate on fruit "
                "injury, rejected harvest, marketable yield, field persistence, "
                "and deployment before we call it crop protection?",
                "swd-eggs-to-crop-protection",
                (
                    "Published evidence:",
                    "fruit damage and decay",
                    "rejected fruit",
                    "marketable yield or loss",
                    "economic loss",
                    "retreatment interval",
                    "compatibility with the intended management program",
                ),
            ),
            (
                "Nearly all SWD eggs moved to untreated fruit while total fecundity fell. Which no-choice, survival, movement, and mating controls distinguish avoidance from impairment?",
                "swd-choice-endpoint-confounds",
                (
                    "side-balanced treated-versus-vehicle choice assay",
                    "treated-only and vehicle-only no-choice arms",
                    "survival immediately after exposure",
                    "confirmed-mated females",
                    "unchanged total eggs",
                    "support activity impairment or toxicity",
                    "within-state treatment contrast",
                ),
            ),
            (
                "My SWD treatment shifted eggs to the control berry but also lowered total eggs. What matched assays tell me whether this is avoidance or suppressed reproduction?",
                "swd-choice-endpoint-confounds",
                ("treated-only and vehicle-only no-choice arms", "support fecundity or egg-laying suppression"),
            ),
            (
                "Which measurements distinguish an SWD egg-laying preference from knockdown or unmated females?",
                "swd-choice-endpoint-confounds",
                ("immobility, knockdown, or death", "confirmed-mated females", "within-state treatment contrast"),
            ),
            (
                "If SWD lay fewer eggs on a treated berry, what result pattern would prove redistribution rather than a toxic or reproductive effect?",
                "swd-choice-endpoint-confounds",
                ("unchanged total eggs", "support activity impairment or toxicity", "support fecundity or egg-laying suppression"),
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
                "Our SWD odor lead changes trap choice only when paired with one target color. Is that enough to call the volatile repellent, and how should we separate color, odor, and their interaction before an oviposition claim?",
                "swd-visual-olfactory-confound",
                ("color-by-odor factorial", "target positions", "not oviposition"),
            ),
            (
                "An SWD trap lure only looks active with the blue target, not the red target. What color, odor, carrier, and position controls separate a visual effect from an odor effect?",
                "swd-visual-olfactory-confound",
                ("preferred visual cue changed", "carrier", "randomize target positions"),
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
                    "DEET, PMD, icaridin, and EBAAP",
                    "20% (m/m) ethanolic solutions",
                    "1 ml per 600 cm2",
                    "0.5, 3.5, or 6.5 hours",
                    "did not isolate which individual sensory channels remained active",
                ),
            ),
            (
                "Which sensory cues does Aedes aegypti combine to find a human, "
                "and which cues are still proven after repellent exposure?",
                "aedes-host-cues-after-exposure",
                (
                    "DEET, PMD, icaridin, and EBAAP",
                    "20% (m/m) ethanolic solutions",
                    "1 ml per 600 cm2",
                    "0.5, 3.5, or 6.5 hours",
                    "integrated host-directed approach and contact persisted",
                    "did not isolate which individual sensory channels remained active",
                ),
            ),
            (
                "After 20% DEET, PMD, icaridin, or EBAAP exposure, what approach "
                "and contact behaviors persisted in Aedes, and did that experiment "
                "identify which sensory channel remained active?",
                "mosquito-arm-in-cage-contact-behaviors",
                (
                    "Published evidence:",
                    "Aedes aegypti and Anopheles stephensi",
                    "DEET, PMD, icaridin, and EBAAP",
                    "20% (m/m) ethanolic solutions",
                    "touch-and-go, bouncing, and landing",
                    "Sensory-channel conclusion: No.",
                    "did not independently isolate an olfactory, visual, thermal, humidity, mechanosensory, or gustatory channel",
                ),
            ),
            (
                "When Aedes still approaches treated skin after DEET, PMD, "
                "icaridin, or EBAAP, which brief contact behaviors were recorded, "
                "and can that result identify the surviving sensory pathway?",
                "mosquito-arm-in-cage-contact-behaviors",
                (
                    "1 ml per 600 cm2",
                    "0.5, 3.5, or 6.5 hours",
                    "touch-and-go, bouncing, and landing",
                    "Sensory-channel conclusion: No.",
                ),
            ),
            (
                "When females still reached and touched skin treated with 20% "
                "PMD, DEET, icaridin, or EBAAP, which contact patterns were "
                "observed, and can we name the sensory route that survived?",
                "mosquito-arm-in-cage-contact-behaviors",
                (
                    "Aedes aegypti and Anopheles stephensi",
                    "touch-and-go, bouncing, and landing",
                    "Sensory-channel conclusion: No.",
                ),
            ),
            (
                "In the 20% DEET, PMD, icaridin, and EBAAP forearm assay, what "
                "did females do before and after touching skin, and does that "
                "identify a receptor or sensory pathway?",
                "mosquito-arm-in-cage-contact-behaviors",
                (
                    "Aedes aegypti and Anopheles stephensi",
                    "host-directed approaches",
                    "touch-and-go, bouncing, and landing",
                    "Sensory-channel conclusion: No.",
                ),
            ),
            (
                "In Anopheles stephensi exposed to 20% DEET and PMD on skin, "
                "which brief contact behaviors remained, and did the arm-in-cage "
                "experiment identify the active sensory channel?",
                "mosquito-arm-in-cage-contact-behaviors",
                (
                    "Aedes aegypti and Anopheles stephensi",
                    "one female was observed for 3 minutes",
                    "touch-and-go, bouncing, and landing",
                    "did not independently isolate an olfactory, visual, thermal, humidity, mechanosensory, or gustatory channel",
                ),
            ),
            (
                "In the 20% DEET, PMD, icaridin, and EBAAP forearm study, "
                "which brief landing and disengagement patterns did females show, "
                "and can those observations identify one receptor pathway?",
                "mosquito-arm-in-cage-contact-behaviors",
                (
                    "touch-and-go, bouncing, and landing",
                    "Sensory-channel conclusion: No.",
                    "Channel-specific perturbations",
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
                "swd-physiological-state-batch-confound",
                (
                    "Do not treat a contrast between batches",
                    "conventional mated gravid females at 7 hours",
                    "not significantly at 12 or 24 hours",
                    "did not directly compare a fed-virgin batch",
                ),
            ),
            (
                "What did the SWD foraging study show about fed conventional gravid females versus starved axenic virgins, and why can those batches not be compared?",
                "swd-physiological-state-batch-confound",
                (
                    "Do not treat a contrast between batches",
                    "did not directly compare",
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
                    "cited reviewed Aedes delivery and human-use evidence set",
                    "no complete product-specific",
                    "carrier",
                    "release-rate",
                    "application-method",
                    "delivery evidence package",
                ),
            ),
            (
                "Before broad diamondback moth repellent screening, which experiment closes the candidate-specific evidence gap?",
                "dbm-first-baseline-experiment",
                ("source release rate", "choice and no-choice oviposition", "same measured candidate headspace"),
            ),
            (
                "A vapor lead works against SWD and Aedes. What can we borrow when building a diamondback moth assay, and which DBM orientation, contact, egg, larval, crop-damage, plume, and persistence results still need direct evidence?",
                "dbm-cross-species-transfer-boundary",
                ("method analogies", "cannot transfer efficacy", "field plume behavior"),
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
                "Broccoli headspace yielded eight antennally active DBM compounds and a subset lure captured adults in field traps. Does that winnow oviposition candidates, or what reproductive and crop-damage outcomes remain unmeasured?",
                "dbm-antennal-field-blend-endpoints",
                ("other five antennally active compounds", "beneficial insects", "not crop protection"),
            ),
            (
                "The ROTH colony's period and timeless transcripts cycle, yet locomotor activity follows light and temperature. Which observation should control when our volatile emitter turns on?",
                "dbm-diel-release-timing",
                ("period", "timeless", "temperature-driven", "light-suppressed"),
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
                (
                    "emitted mass",
                    "time-resolved canopy concentration",
                    "marketable yield",
                    "Keep two raspberry-field results separate",
                ),
            ),
            (
                "Aerosol puffers reduced SWD emergence in raspberries more than passive vials. What exposure, weather, egg, larval, crop-quality, and yield data do we still need before choosing the delivery system?",
                "swd-field-plume-delivery",
                (
                    "If a question says puffers reduced emergence more than passive vials",
                    "premise that needs correction",
                    "pupae emerging from fruit",
                    "eggs",
                    "larval establishment or pupal emergence",
                    "crop quality or marketable yield",
                    "non-target exposure",
                ),
            ),
            (
                "If an SWD oviposition deterrent lowered eggs in fall raspberry plots, can I treat that as a clean crop-repellent win without checking non-target captures and deployment context?",
                "swd-field-deterrent-nontarget-boundary",
                (
                    "No.",
                    "fall-bearing red raspberry plots",
                    "potential nontarget effects",
                    "not optional context",
                    "does not prove general protection",
                ),
            ),
            (
                "Our fall raspberry SWD deterrent cut egg laying, but we have not reviewed nontarget captures or the dispenser setup. Is that enough for a crop-protection claim?",
                "swd-field-deterrent-nontarget-boundary",
                (
                    "No.",
                    "field layout",
                    "deployment method",
                    "marketable yield",
                    "does not by itself prove reduced crop damage",
                ),
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
                if topic_id == "aedes-host-cues-after-exposure":
                    self.assertNotIn(
                        "compound-specific exposure must be tested",
                        answer["answer"].casefold(),
                    )
                if topic_id == "swd-eggs-to-crop-protection":
                    self.assertNotIn(
                        "fewer pupae emerging from treated raspberries",
                        answer["answer"].casefold(),
                    )
                if topic_id == "swd-push-pull-treatment-comparison":
                    self.assertNotIn(
                        "match fruit species", answer["answer"].casefold()
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
        self.assertIn(
            "Materials and methods > Excito-repellency (ER) assay system",
            transfluthrin_locator,
        )
        self.assertIn(
            "sentences beginning 'For measuring spatial repellency', "
            "'For the contact design', and 'Primary outcome measures are'",
            transfluthrin_locator,
        )
        self.assertIn(
            "sentences beginning 'The number of mosquitoes that escaped' and "
            "'All live and moribund mosquitoes'",
            transfluthrin_locator,
        )
        self.assertIn(
            "Materials and methods > Data analysis, paragraph beginning "
            "'The percent ER escape responses'",
            transfluthrin_locator,
        )
        self.assertIn(
            "paragraphs beginning 'The key feature of the excito-repellency', "
            "'The ER contact test design potentially', and "
            "'Beside ER responses, mosquitoes encountering TFT'",
            transfluthrin_locator,
        )
        self.assertIn(
            "Excito-repellency of field-collected mosquitoes to sublethal concentration, Figure 4 and Table 6",
            transfluthrin_locator,
        )
        self.assertNotIn("Experimental design", transfluthrin_locator)

        learning_locator = provenance["openalex:W4315621418"]["locator"]
        self.assertIn("Materials and methods 4(b)(ii)", learning_locator)
        self.assertIn("60-second odor presentation", learning_locator)
        self.assertIn("2-minute inter-trial interval", learning_locator)

        arm_in_cage_locator = provenance["openalex:W4403603462"]["locator"]
        self.assertIn(
            "Methods > Experimental set-up: 40 x 40 x 40 cm",
            arm_in_cage_locator,
        )
        self.assertIn(
            "Methods > Experimental procedure, paragraphs beginning "
            "'The experimental procedure was', "
            "'The study included no study participants', "
            "'In the experiment', and 'For each exposure'",
            arm_in_cage_locator,
        )
        self.assertIn("1 ml per 600 cm2", arm_in_cage_locator)
        self.assertIn(
            "Results > Frequency of individual contact behaviours with exposed forearm, paragraph 1 and Figure 6",
            arm_in_cage_locator,
        )
        self.assertIn(
            "Results > Identification and quantification of behavioural categories, paragraph beginning 'Based on the FHF parameters and analysis of the video playbacks'",
            arm_in_cage_locator,
        )
        self.assertIn(
            "paragraph beginning 'Contact disengagement has also been described'",
            arm_in_cage_locator,
        )
        self.assertIn(
            "Methods > Data analysis, paragraphs beginning 'The readouts of the 3D video tracking system were' and 'Based on the FHF parameters, visual inspection'",
            arm_in_cage_locator,
        )
        self.assertIn(
            "with no receptor or sensory-channel perturbation reported",
            arm_in_cage_locator,
        )
        self.assertNotIn(
            "Experimental set-up: 40 x 40 x 40 cm arm-in-cage assay, 1 ml",
            arm_in_cage_locator,
        )

        life_history_locator = provenance["openalex:W4413344516"]["locator"]
        self.assertIn("Supplementary Table S4", life_history_locator)
        self.assertIn("S4C", life_history_locator)
        self.assertIn("S4E", life_history_locator)
        self.assertIn("S4F", life_history_locator)

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

    def test_sealed_failure_repairs_generalize_to_neighboring_questions(self):
        cases = (
            (
                "Every SWD trap in our comparison uses the same vinegar-and-ethanol "
                "drowning fluid. Before ranking an H. uvarum headspace dispenser "
                "against the reference lure, must we isolate the retention liquid's "
                "contribution?",
                {"swd:openalex_literature:openalex:W4213332511"},
                (
                    "91 ml water",
                    "0.003 ml Tween",
                    "1.6 ml acetic acid",
                    "7.2 ml ethanol",
                    "85 SWD",
                    "factorial",
                    "crop protection",
                ),
                "paragraph 4",
            ),
            (
                "Early sweet-cherry infestation was northern, then later became "
                "central, low-canopy, and southern. Does that trace SWD entering from "
                "the north, or what evidence is needed before fitting movement "
                "transitions?",
                {"swd:openalex_literature:openalex:W3036207020"},
                (
                    "1,328 arthropods",
                    "10,426 arthropods",
                    "did not track individual flies",
                    "marked flies",
                    "detection",
                    "recovery",
                ),
                "sentences 3-9",
            ),
            (
                "May we use microbe-treated soft agar as a universal positive SWD "
                "deterrence control across hard inserts, fruit coatings, and every "
                "formulation screen?",
                {"swd:openalex_literature:openalex:W3124252639"},
                (
                    "soft 1% agar",
                    "hard 3% agar",
                    "100 microliters",
                    "20 females and 10 males",
                    "16 hours",
                    "0.22 micrometers",
                    "not a universal",
                ),
                "Methods 2.2",
            ),
            (
                "For SWD, do methyl-jasmonate low-dose attraction and high-dose "
                "oviposition deterrence justify placing pull traps and a high-dose "
                "push treatment together in a berry field?",
                {"swd:openalex_literature:openalex:W4413971464"},
                (
                    "55.24",
                    "55.03",
                    "55.14",
                    "trap capture",
                    "bycatch",
                    "spacing",
                    "did not test a field push-pull system",
                ),
                "55.24, 55.03, and 55.14",
            ),
            (
                "In a repeat-measures Aedes aegypti screen, can the same cage be "
                "challenged with 20% DEET three hours later as an independent "
                "replicate, or which carryover controls are needed?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                (
                    "0.5 ml",
                    "2 minutes",
                    "10 mosquitoes",
                    "removed",
                    "concurrently prepared unexposed controls",
                    "Do not treat a three-hour second challenge",
                ),
                "Materials and Methods, Experiment 1",
            ),
            (
                "After prior DEET exposure, can a second Aedes aegypti measurement "
                "three hours later count as an independent efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                (
                    "control-arm-to-DEET",
                    "concurrently prepared unexposed controls",
                    "selected cohort",
                ),
                "Materials and Methods, Experiment 1",
            ),
            (
                "After prior exposure to DEET, can a second Aedes aegypti "
                "measurement count as an independent efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Does previous exposure to DEET create carryover in a repeated "
                "Aedes aegypti efficacy screen?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("control-arm-to-DEET", "selected cohort"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "How should pre-exposure to DEET be controlled in a repeat Aedes "
                "aegypti repellent measurement?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("naive-to-DEET", "solvent-to-DEET", "DEET-to-DEET"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can a second DEET challenge three hours later count as an "
                "independent Aedes aegypti efficacy measurement?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can Aedes aegypti previously exposed to DEET be counted as an "
                "independent replicate in a later efficacy screen?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "not an unselected population"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "If Aedes aegypti were exposed to DEET before, which carryover "
                "controls are needed for the next efficacy measurement?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("naive-to-DEET", "solvent-to-DEET", "DEET-to-DEET"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can repeated DEET exposure in Aedes aegypti be treated as an "
                "independent efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "not an unselected population"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "When retesting with DEET, which carryover controls should an Aedes "
                "aegypti efficacy screen include?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("naive-to-DEET", "solvent-to-DEET", "DEET-to-DEET"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can a second exposure to DEET in Aedes aegypti count as an "
                "independent efficacy measurement?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can prior host contact change how Aedes aegypti responds to a "
                "repellent?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("prior host contact", "is not established"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "Does prior odor exposure alter a later Aedes aegypti repellent "
                "response?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("associative learning", "does not show learning to every repellent"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "Can prior repellent exposure change a later Aedes aegypti response?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("previous DEET exposure", "three hours later"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "Can repeat repellent exposure change a later Aedes aegypti "
                "response?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("previous DEET exposure", "three hours later"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "Does repeated odor exposure alter a later Aedes aegypti repellent "
                "response?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("associative learning", "does not show learning to every repellent"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "When Aedes aegypti are retested three hours after repellent "
                "exposure, can their response change?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("previous DEET exposure", "three hours later"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "When Aedes aegypti are retested three hours after exposure to "
                "DEET, can their response change?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("previous DEET exposure", "three hours later"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "When Aedes aegypti are retested after exposure to repellent, can "
                "their response change?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("previous DEET exposure", "three hours later"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "When Aedes aegypti are retested following exposure to host odor, "
                "can their response change?",
                {
                    "aedes_primary_behavior:pmc:PMC3577799",
                    "openalex:W4315621418",
                },
                ("prior host contact", "is not established"),
                "Materials and methods 4(b)(ii)",
            ),
            (
                "Can we challenge the same cage with DEET again and treat the result "
                "as an independent Aedes aegypti efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can the same cage be rechallenged with DEET and counted as an "
                "independent Aedes aegypti efficacy measurement?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "not an unselected population"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can pre-exposure to DEET bias an independent Aedes aegypti "
                "efficacy measurement?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can re-exposure to DEET count as an independent Aedes aegypti "
                "efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "not an unselected population"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Does DEET re-exposure create carryover in an Aedes aegypti screen?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("control-arm-to-DEET", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can we use DEET to rechallenge the same cage and count the result "
                "as an independent Aedes aegypti efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "not an unselected population"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can a DEET efficacy screen that reuses the same cage count the "
                "second Aedes aegypti measurement as independent?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Can I reuse the same Aedes cage three hours after a DEET challenge "
                "and count it as an independent efficacy replicate?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("three-hour second challenge", "selected cohort"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "If Aedes is less repelled by DEET a few hours after earlier DEET "
                "exposure, what should I change in a repeat-exposure assay?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("control-arm-to-DEET", "concurrently prepared unexposed controls"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "If Aedes aegypti shows reduced repellency after prior DEET "
                "exposure, how should I design the next assay?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("naive-to-DEET", "solvent-to-DEET", "DEET-to-DEET"),
                "Materials and Methods, Experiment 1",
            ),
            (
                "Aedes mosquitoes responded less to DEET following earlier DEET "
                "exposure; how should the protocol compare cohorts?",
                {"aedes_primary_behavior:pmc:PMC3577799"},
                ("selected cohort", "not an unselected population"),
                "Materials and Methods, Experiment 1",
            ),
        )
        negative_cases = (
            (
                "Does the study show that SWD movement changed later after "
                "repellent exposure?",
                "swd:openalex_literature:openalex:W3036207020",
            ),
            (
                "What evidence shows early movement changes in Drosophila suzukii "
                "after microbial exposure?",
                "swd:openalex_literature:openalex:W3036207020",
            ),
            (
                "Does DEET efficacy against Aedes aegypti decline later in the day?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "What is the efficacy of DEET against Aedes aegypti three hours "
                "after application?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Does prior exposure to sunlight reduce DEET efficacy against "
                "Aedes aegypti?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Does previous exposure to heat affect DEET efficacy against "
                "Aedes aegypti?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Does repeat sunscreen application reduce DEET efficacy against "
                "Aedes aegypti?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Does using the same cage size affect DEET efficacy against Aedes "
                "aegypti?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Does one DEET exposure alter Aedes aegypti efficacy?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Which previous study measured Aedes aegypti response during "
                "repellent exposure?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Does using the same cage size create a challenge for measuring "
                "DEET efficacy against Aedes aegypti?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
            (
                "Can we challenge the same cage with heat before an Aedes aegypti "
                "DEET efficacy measurement?",
                "aedes_primary_behavior:pmc:PMC3577799",
            ),
        )
        catalog = load_reviewed_science_catalog(default_reviewed_science_catalog())
        record_ids = sorted(
            {
                record_id
                for topic in catalog["topics"]
                for record_id in topic["source_record_ids"]
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
                for question, _, _, _ in cases
            ]
            negative_answers = [
                build_reviewed_science_answer(index, question)
                for question, _ in negative_cases
            ]

        for (question, expected_ids, fragments, locator_fragment), answer in zip(
            cases, answers, strict=True
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(answer)
                assert answer is not None
                self.assertTrue(answer["ok"])
                self.assertEqual(
                    {item["record_id"] for item in answer["evidence"]},
                    expected_ids,
                )
                self.assertEqual(len(answer["evidence"]), len(expected_ids))
                self.assertTrue(
                    all(
                        str(evidence["url"]).startswith("https://")
                        for evidence in answer["evidence"]
                    )
                )
                self.assertTrue(
                    any(
                        locator_fragment.casefold()
                        in str(evidence["provenance"]["locator"]).casefold()
                        for evidence in answer["evidence"]
                    ),
                    answer["evidence"],
                )
                for fragment in fragments:
                    self.assertIn(fragment.casefold(), answer["answer"].casefold())

        for (question, forbidden_record_id), answer in zip(
            negative_cases, negative_answers, strict=True
        ):
            with self.subTest(question=question):
                if answer is not None:
                    self.assertNotIn(
                        forbidden_record_id,
                        {item["record_id"] for item in answer["evidence"]},
                    )


if __name__ == "__main__":
    unittest.main()
