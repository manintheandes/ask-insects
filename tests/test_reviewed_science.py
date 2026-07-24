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
                "For an SWD oviposition repellent lead, how should I think about adult or larval pre-exposure before assuming the deterrent will keep working after repeated crop exposure?",
                "Before I trust an SWD oviposition deterrent across repeated crop exposure, how should adult and larval pre-exposure be tested?",
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
                "crop injury and fruit quality",
                "residues and worker exposure",
                "field pollinator survival and behavior",
                "predators and parasitoids",
                "soil exposure",
                "aquatic exposure",
                "does not establish pollinator safety or crop safety",
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
                    "did not test genetic association",
                    "unexposed-generation",
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
        questions = (
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
                "Which product and final malaria estimates belong to the Kenya "
                "spatial-repellent trial, and how far can I bridge them to a new "
                "Anopheles product?"
            ),
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
                    "is not a percentage reduction in malaria cases",
                    answer["answer"],
                )
                self.assertIn("82.7% (95% CI 78.5%-86.1%)", answer["answer"])
                self.assertIn("65.1% (95% CI 59.4%-70.0%)", answer["answer"])
                self.assertIn("20.1% mortality at 24 hours", answer["answer"])
                self.assertIn("They cannot be added", answer["answer"])
                self.assertIn("Funding section says no financial support", answer["answer"])
                self.assertIn("Mosquito Shield, not Guardian", answer["answer"])
                self.assertIn("29 clusters per arm", answer["answer"])
                self.assertIn("two units per 9 square metres", answer["answer"])
                self.assertIn("32.7% (95% two-sided CI 12.6%-48.2%", answer["answer"])
                self.assertIn("29.5% (95% CI 12.0%-43.5%", answer["answer"])
                self.assertIn("33.4% and 32.1% values were interim", answer["answer"])
                self.assertIn("P-12643", answer["answer"])
                self.assertIn("BIT084 NI", answer["answer"])
                self.assertIn("not used to inform the decision", answer["answer"])
                self.assertIn("equivalence-only dossiers", answer["answer"])
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
