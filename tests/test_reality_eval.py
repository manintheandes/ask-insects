import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from askinsects.reality_eval import (
    CONTRACT_VERSION,
    HOLDOUT_BUNDLE_VERSION,
    HOLDOUT_QUESTION_COUNT,
    HOLDOUT_RECEIPT_VERSION,
    PUBLIC_MANIFEST_VERSION,
    PUBLIC_QUESTION_COUNT,
    QUESTION_COUNT,
    RESULTS_VERSION,
    TARGET,
    RealityEvalError,
    assemble_contract,
    build_holdout_receipt,
    load_json_object,
    sha256_bytes,
    summarize_results,
    validate_contract,
    validate_holdout_bundle,
    validate_holdout_receipt,
    validate_public_manifest,
    validate_results,
)


CREATED_AT = "2026-07-16T12:00:00Z"
INSTALLED_VALIDATOR = Path(
    "/Users/josh/.codex/skills/realityeval/scripts/validate_eval.py"
)
MISSING = object()
DEFAULT_PUBLIC_MANIFEST = (
    Path(__file__).parents[1]
    / "evals"
    / "ask_insects_reality_eval_public_v1.json"
)
EXPECTED_PUBLIC_QUESTIONS = (
    (
        "swd-texture-01",
        "How does fruit texture influence where Drosophila suzukii females lay eggs, and what sensory mechanism is implicated?",
    ),
    (
        "swd-microbes-02",
        "Do microbes on fruit attract or deter SWD oviposition, and does substrate hardness change that response?",
    ),
    (
        "swd-density-03",
        "How do adult density and host quality change spotted wing drosophila egg-laying behavior?",
    ),
    (
        "swd-fermentation-04",
        "How do fermentation volatile concentration and mating state affect drosophilid preference, and what is actually known for SWD?",
    ),
    (
        "swd-meja-dose-05",
        "What does methyl jasmonate's dose-response tell us about the risk that a low dose attracts SWD instead of repelling it?",
    ),
    (
        "swd-choice-confounds-06",
        "If treated fruit gets fewer SWD eggs, how do we separate true oviposition choice from mortality, reduced activity, mating, or fecundity?",
    ),
    (
        "swd-choice-controls-07",
        "Which controls are essential in a two-choice SWD oviposition assay?",
    ),
    (
        "swd-olfactometer-08",
        "Can a Y-tube or planar olfactometer result prove crop protection or reduced egg laying in SWD?",
    ),
    (
        "swd-fruit-condition-09",
        "How should fruit ripeness, skin hardness, injury, and moisture be controlled in an SWD repellent assay?",
    ),
    (
        "swd-crop-followup-10",
        "What follow-up measurements connect SWD oviposition deterrence to actual crop protection?",
    ),
    (
        "aedes-host-cues-11",
        "Which sensory cues does Aedes aegypti combine to find a human, and which cues are still proven after repellent exposure?",
    ),
    (
        "aedes-bloodmeal-state-12",
        "What does the public evidence say about internal-state control of Aedes aegypti host seeking after a blood meal?",
    ),
    (
        "aedes-npylr1-13",
        "Is NPYLR1 proven to be required for post-blood-meal suppression of Aedes aegypti host seeking?",
    ),
    (
        "aedes-human-metabolites-14",
        "What evidence links human metabolic differences to Aedes aegypti attraction, and is it causal?",
    ),
    (
        "aedes-contact-spatial-15",
        "How do we distinguish spatial repellency from contact irritancy in Aedes aegypti?",
    ),
    (
        "aedes-vapor-toxicity-16",
        "How can we tell whether apparent vapor repellency in Aedes aegypti is actually knockdown or toxicity?",
    ),
    (
        "aedes-environment-17",
        "Which airflow, plume, temperature, and humidity controls are needed in an Aedes spatial-repellency assay?",
    ),
    (
        "aedes-occupancy-bites-18",
        "Does reduced chamber occupancy prove fewer human landings or bites by Aedes aegypti?",
    ),
    (
        "aedes-recovery-19",
        "What should be measured after Aedes repellent exposure to separate temporary knockdown, recovery, and mortality?",
    ),
    (
        "aedes-controlled-release-20",
        "What does controlled-release citronella evidence show about duration, and what does it not prove about human protection?",
    ),
    (
        "swd-receptors-21",
        "How strong is the evidence that specific odorant or ionotropic receptors drive SWD avoidance, rather than merely responding to an odor?",
    ),
    (
        "swd-visual-confound-22",
        "Could visual contrast or fruit color confound an SWD assay intended to measure odor-mediated repellency?",
    ),
    (
        "swd-recovery-habituation-23",
        "After a volatile is removed, what recovery measurements would show whether SWD avoidance persists, habituates, or rapidly disappears?",
    ),
    (
        "swd-state-confounds-24",
        "How could age, mating status, hunger, or prior egg laying change an SWD repellent result?",
    ),
    (
        "swd-field-plume-25",
        "What changes when an SWD volatile that works in a still-air chamber is moved into a windy crop canopy?",
    ),
    (
        "swd-safety-26",
        "Which non-target and crop-safety measurements should accompany an SWD repellent field trial?",
    ),
    (
        "swd-resistance-27",
        "What evidence would distinguish learned habituation from inherited resistance to an SWD repellent?",
    ),
    (
        "swd-crop-loss-28",
        "Which endpoints connect fewer SWD eggs on fruit to fewer surviving larvae and less marketable crop loss?",
    ),
    (
        "aedes-multimodal-cues-29",
        "How redundant are carbon dioxide, human odor, heat, humidity, and visual cues during Aedes aegypti host seeking?",
    ),
    (
        "aedes-circadian-30",
        "How should time of day and mosquito circadian state be controlled in a human-repellent assay?",
    ),
    (
        "aedes-learning-31",
        "Can prior odor or host experience change how Aedes aegypti responds to a repellent?",
    ),
    (
        "aedes-population-variation-32",
        "How much can mosquito population, genotype, age, or insecticide-resistance background change a repellent result?",
    ),
    (
        "aedes-dose-release-33",
        "How should dose, evaporation rate, air concentration, and distance be reported for an Aedes spatial repellent?",
    ),
    (
        "aedes-arm-in-cage-34",
        "What can an arm-in-cage landing assay establish, and what can it not establish about actual bite prevention?",
    ),
    (
        "aedes-durability-35",
        "Which sweat, washing, abrasion, sunlight, and temperature tests are needed to estimate how long a skin repellent protects a person?",
    ),
    (
        "aedes-repellent-resistance-36",
        "How do we distinguish physiological resistance to a mosquito repellent from ordinary behavioral avoidance or reduced sensitivity?",
    ),
    (
        "dbm-host-cues-37",
        "Which plant cues guide diamondback moth host finding and egg laying, and which evidence is direct for Plutella xylostella?",
    ),
    (
        "dbm-endpoints-38",
        "For diamondback moth, which life stage and crop-damage endpoints should a repellent program measure first?",
    ),
    (
        "dbm-cross-species-39",
        "What can SWD or mosquito spatial-repellency evidence legitimately suggest for diamondback moth, and what must be tested directly?",
    ),
    (
        "dbm-gap-experiment-40",
        "Before screening diamondback moth repellents, what is the most important public-evidence gap to close and what experiment would close it?",
    ),
)


def truth_packet(case_id):
    return {
        "required_claims": [f"State the measured observation for {case_id}."],
        "forbidden_claims": ["The observation proves commercial efficacy."],
        "reasoning_boundaries": ["Separate observation from mechanism."],
        "sources": [
            {
                "source_id": f"public-source-{case_id}",
                "locator": f"records#{case_id}",
                "public_url": f"https://example.org/sources/{case_id}",
                "supports": f"The measured observation for {case_id}.",
            }
        ],
    }


def question_case(
    case_id,
    *,
    holdout,
    kind="domain",
    category="category-0",
):
    return {
        "id": case_id,
        "question": f"How should a scientist interpret evidence for {case_id}?",
        "category": category,
        "kind": kind,
        "origin": "scientist-workflow",
        "holdout": holdout,
        "why_realistic": "A scientist must interpret evidence before making a decision.",
        "expected_behavior": "State the observation and preserve the reasoning boundary.",
        "truth_source": "Independent review of the cited public source.",
        "truth_packet": truth_packet(case_id),
    }


def public_manifest():
    return {
        "manifest_version": PUBLIC_MANIFEST_VERSION,
        "target": TARGET,
        "maximum_seconds": 60,
        "questions": [
            question_case(
                f"public-{index:02d}",
                holdout=False,
                category=f"category-{index % 6}",
            )
            for index in range(PUBLIC_QUESTION_COUNT)
        ],
    }


def holdout_bundle():
    kinds = ("domain", "boundary", "adversarial")
    return {
        "bundle_version": HOLDOUT_BUNDLE_VERSION,
        "target": TARGET,
        "created_at": CREATED_AT,
        "questions": [
            question_case(
                f"holdout-{index:02d}",
                holdout=True,
                kind=kinds[index % len(kinds)],
                category=f"holdout-category-{index % 2}",
            )
            for index in range(HOLDOUT_QUESTION_COUNT)
        ],
    }


def contract_bytes(contract):
    return json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")


def passing_results(contract=None, exact_contract_bytes=None):
    contract = contract or assemble_contract(public_manifest(), holdout_bundle())
    if exact_contract_bytes is None:
        exact_contract_bytes = contract_bytes(contract)
    return {
        "results_version": RESULTS_VERSION,
        "contract_sha256": sha256_bytes(exact_contract_bytes),
        "target": TARGET,
        "mode": "evaluation",
        "environment": "Codex desktop production route",
        "revision": "revision-123",
        "recording": {
            "recording_path": "/private/tmp/reality-eval-recording.mov",
            "question_count": QUESTION_COUNT,
            "complete_answers_visible": True,
            "privacy_review": "pass",
            "shared_with_josh": True,
        },
        "results": [
            {
                "id": case["id"],
                "question": case["question"],
                "answer": f"Complete source-backed answer for {case['id']}.",
                "elapsed_seconds": index / 10,
                "attempt": 1,
                "interface_observed": "codex-app",
                "answer_systems": [TARGET],
                "fresh_task": True,
                "complete_answer_visible": True,
                "route_trace": {
                    "thread_id": f"thread-{case['id']}",
                    "submitted_at": "2026-07-16T12:00:00Z",
                    "completed_at": "2026-07-16T12:00:01Z",
                    "answer_command_count": 1,
                    "hosted_route": True,
                    "raw_trace_path": f"/private/tmp/realityeval/{case['id']}.json",
                },
                "route_verdict": "pass",
                "content_verdict": "pass",
                "source_verdict": "pass",
                "privacy_verdict": "pass",
                "usefulness_verdict": "pass",
                "judge_evidence": "The independent source supports the answer.",
                "provenance": [
                    {
                        "source_id": f"source-{case['id']}",
                        "locator": f"records#{case['id']}",
                    }
                ],
            }
            for index, case in enumerate(contract["questions"])
        ],
    }


def passing_result_fixture():
    contract = assemble_contract(public_manifest(), holdout_bundle())
    exact_contract_bytes = contract_bytes(contract)
    return (
        contract,
        exact_contract_bytes,
        passing_results(contract, exact_contract_bytes),
    )


def mutate_path(payload, path, value):
    cursor = payload
    for component in path[:-1]:
        cursor = cursor[component]
    if value is MISSING:
        del cursor[path[-1]]
    else:
        cursor[path[-1]] = value


class RealityEvalTests(unittest.TestCase):
    def test_sha256_and_json_object_helpers(self):
        payload = b'{"ok": true}'
        self.assertEqual(sha256_bytes(payload), hashlib.sha256(payload).hexdigest())

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "object.json"
            path.write_bytes(payload)
            self.assertEqual(load_json_object(path), {"ok": True})
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(RealityEvalError, "JSON object"):
                load_json_object(path)

    def test_load_json_object_rejects_duplicate_top_level_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "duplicate-top-level.json"
            path.write_text('{"ok":true,"ok":false}', encoding="utf-8")
            with self.assertRaisesRegex(
                RealityEvalError,
                "duplicate JSON object key",
            ):
                load_json_object(path)

    def test_holdout_bytes_reject_duplicate_nested_keys(self):
        bundle_bytes = json.dumps(
            holdout_bundle(),
            separators=(",", ":"),
        ).encode("utf-8")
        source = b'"source_id":"public-source-holdout-00"'
        duplicate_source = source + b"," + source
        self.assertIn(source, bundle_bytes)
        bundle_bytes = bundle_bytes.replace(source, duplicate_source, 1)
        with self.assertRaisesRegex(
            RealityEvalError,
            "duplicate JSON object key",
        ):
            build_holdout_receipt(bundle_bytes)

    def test_contract_bytes_reject_duplicate_nested_keys(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        rule = b'"exact_question_required":true'
        duplicate_rule = rule + b"," + rule
        self.assertIn(rule, exact_contract_bytes)
        duplicate_contract_bytes = exact_contract_bytes.replace(rule, duplicate_rule, 1)
        with self.assertRaisesRegex(
            RealityEvalError,
            "duplicate JSON object key",
        ):
            validate_results(
                payload,
                contract=contract,
                contract_bytes=duplicate_contract_bytes,
            )

    def test_valid_public_manifest(self):
        validated = validate_public_manifest(public_manifest())

        self.assertEqual(len(validated["questions"]), PUBLIC_QUESTION_COUNT)
        self.assertTrue(all(case["holdout"] is False for case in validated["questions"]))
        self.assertTrue(all(case["kind"] == "domain" for case in validated["questions"]))

    def test_canonical_public_manifest_is_realistic_and_complete(self):
        manifest = load_json_object(DEFAULT_PUBLIC_MANIFEST)
        validate_public_manifest(manifest)
        questions = manifest["questions"]

        self.assertEqual(len(questions), 40)
        self.assertTrue(all(case["kind"] == "domain" for case in questions))
        self.assertTrue(all(case["holdout"] is False for case in questions))
        self.assertGreaterEqual(len({case["category"] for case in questions}), 6)
        self.assertEqual(
            {(case["id"], case["question"]) for case in questions},
            set(EXPECTED_PUBLIC_QUESTIONS),
        )
        self.assertEqual(len({case["question"] for case in questions}), 40)
        product_names = ("ask insects", "ask monarch", "ask just")
        self.assertTrue(
            all(
                all(name not in case["question"].casefold() for name in product_names)
                for case in questions
            )
        )
        self.assertTrue(
            all(case["truth_packet"]["sources"] for case in questions)
        )

    def test_canonical_public_manifest_pins_verified_public_artifacts(self):
        manifest = load_json_object(DEFAULT_PUBLIC_MANIFEST)
        sources = [
            source
            for case in manifest["questions"]
            for source in case["truth_packet"]["sources"]
        ]
        expected_urls_by_record = {
            "W2344416877": {"https://doi.org/10.48496/m467-t235"},
            "W4225097850": {
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC9046260/"
            },
            "W4401794442": {
                "https://www.nature.com/articles/s41586-024-07848-5"
            },
            "W4403603462": {
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC11494009/"
            },
            "39769586": {"https://pubmed.ncbi.nlm.nih.gov/39769586/"},
        }

        for record_id, expected_urls in expected_urls_by_record.items():
            with self.subTest(record_id=record_id):
                matching_urls = {
                    source["public_url"]
                    for source in sources
                    if record_id in source["locator"]
                }
                self.assertEqual(matching_urls, expected_urls)

    def test_public_manifest_rejects_39_and_41_cases(self):
        too_few = public_manifest()
        too_few["questions"].pop()
        too_many = public_manifest()
        too_many["questions"].append(
            question_case("public-40", holdout=False, category="category-0")
        )

        for payload in (too_few, too_many):
            with self.subTest(question_count=len(payload["questions"])):
                with self.assertRaisesRegex(RealityEvalError, "exactly 40"):
                    validate_public_manifest(payload)

    def test_public_manifest_rejects_holdouts_and_non_domain_cases(self):
        mutations = (("holdout", True, "holdout"), ("kind", "boundary", "domain"))

        for field, value, message in mutations:
            with self.subTest(field=field):
                payload = public_manifest()
                payload["questions"][0][field] = value
                with self.assertRaisesRegex(RealityEvalError, message):
                    validate_public_manifest(payload)

    def test_valid_holdout_bundle(self):
        validated = validate_holdout_bundle(holdout_bundle())

        self.assertEqual(len(validated["questions"]), HOLDOUT_QUESTION_COUNT)
        self.assertTrue(all(case["holdout"] is True for case in validated["questions"]))

    def test_holdout_created_at_requires_canonical_utc_seconds(self):
        invalid_timestamps = (
            "2026-07-16T12:00:00.123Z",
            "2026-07-16T12:00:00+00:00",
            "2026-07-16T12:00:00Z\ncovert-channel",
            "2026-02-30T12:00:00Z",
        )
        for created_at in invalid_timestamps:
            with self.subTest(created_at=created_at):
                payload = holdout_bundle()
                payload["created_at"] = created_at
                with self.assertRaisesRegex(RealityEvalError, "created_at"):
                    validate_holdout_bundle(payload)

    def test_holdout_bundle_rejects_non_holdout_case(self):
        payload = holdout_bundle()
        payload["questions"][0]["holdout"] = False

        with self.assertRaisesRegex(RealityEvalError, "holdout"):
            validate_holdout_bundle(payload)

    def test_cases_reject_missing_or_empty_truth_fields(self):
        payload = holdout_bundle()
        del payload["questions"][0]["truth_packet"]
        with self.assertRaisesRegex(RealityEvalError, "truth_packet"):
            validate_holdout_bundle(payload)

        mutations = (
            ("required_claims", []),
            ("required_claims", [" "]),
            ("forbidden_claims", [""]),
            ("reasoning_boundaries", []),
            ("sources", []),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                payload = holdout_bundle()
                payload["questions"][0]["truth_packet"][field] = value
                with self.assertRaisesRegex(RealityEvalError, field):
                    validate_holdout_bundle(payload)

        for field in ("source_id", "locator", "public_url", "supports"):
            with self.subTest(source_field=field):
                payload = holdout_bundle()
                payload["questions"][0]["truth_packet"]["sources"][0][field] = ""
                with self.assertRaisesRegex(RealityEvalError, field):
                    validate_holdout_bundle(payload)

    def test_duplicate_ids_and_normalized_wording_are_rejected(self):
        duplicate_id = public_manifest()
        duplicate_id["questions"][1]["id"] = duplicate_id["questions"][0]["id"]
        with self.assertRaisesRegex(RealityEvalError, "ids must be unique"):
            validate_public_manifest(duplicate_id)

        duplicate_wording = public_manifest()
        question = duplicate_wording["questions"][0]["question"]
        duplicate_wording["questions"][1]["question"] = (
            f"  {question.upper().replace(' ', '   ')}  "
        )
        with self.assertRaisesRegex(RealityEvalError, "wording must be unique"):
            validate_public_manifest(duplicate_wording)

    def test_assembly_rejects_duplicates_across_public_and_holdout_cases(self):
        public = public_manifest()
        holdouts = holdout_bundle()
        holdouts["questions"][0]["id"] = public["questions"][0]["id"]

        with self.assertRaisesRegex(RealityEvalError, "ids must be unique"):
            assemble_contract(public, holdouts)

        holdouts = holdout_bundle()
        holdouts["questions"][0]["question"] = public["questions"][0]["question"]
        with self.assertRaisesRegex(RealityEvalError, "wording must be unique"):
            assemble_contract(public, holdouts)

    def test_domain_cases_reject_product_meta_questions(self):
        questions = (
            "What does Ask Insects cover for Aedes aegypti?",
            "What does Ask Monarch cover?",
            "What does Ask Just cover?",
            "Is Ask Monarch complete?",
            "Is Ask Just complete?",
            "What is Ask Monarch missing?",
            "What is Ask Just missing?",
            "How complete is Ask Insects?",
            "Should this question use Ask Monarch?",
            "Can Ask Just answer this question?",
            "Does ASK INSECTS have evidence for this claim?",
        )
        for question in questions:
            with self.subTest(question=question):
                payload = public_manifest()
                payload["questions"][0]["question"] = question
                with self.assertRaisesRegex(RealityEvalError, "coverage or status"):
                    validate_public_manifest(payload)

    def test_domain_cases_allow_ordinary_ask_phrases(self):
        questions = (
            "How should we ask farmers to record mosquito landing observations?",
            "When should we ask a scientist to review the assay evidence?",
        )
        for question in questions:
            with self.subTest(question=question):
                payload = public_manifest()
                payload["questions"][0]["question"] = question
                self.assertIs(validate_public_manifest(payload), payload)

    def test_categories_must_be_lowercase_slugs(self):
        invalid_categories = (
            "Category-0",
            " category-0",
            "category-0 ",
            "category_0",
            "category--0",
        )
        for category in invalid_categories:
            with self.subTest(category=category):
                payload = public_manifest()
                payload["questions"][0]["category"] = category
                with self.assertRaisesRegex(RealityEvalError, "lowercase slug"):
                    validate_public_manifest(payload)

    def test_malformed_manifest_scalars_raise_reality_eval_error(self):
        mutations = (
            (
                "kind-list",
                public_manifest,
                ("questions", 0, "kind"),
                [],
                validate_public_manifest,
                "kind",
            ),
            (
                "huge-timestamp",
                holdout_bundle,
                ("created_at",),
                "9" * 100_000,
                validate_holdout_bundle,
                "created_at",
            ),
            (
                "timestamp-int",
                holdout_bundle,
                ("created_at",),
                10**10_000,
                validate_holdout_bundle,
                "created_at",
            ),
        )
        for name, builder, path, value, validator, message in mutations:
            with self.subTest(name=name):
                payload = builder()
                mutate_path(payload, path, value)
                with self.assertRaisesRegex(RealityEvalError, message):
                    validator(payload)

    def test_maximum_seconds_rejects_nonfinite_and_overflowing_numbers(self):
        invalid_values = (
            True,
            float("nan"),
            float("inf"),
            float("-inf"),
            10**10_000,
        )
        for index, value in enumerate(invalid_values):
            with self.subTest(case=index, value_type=type(value).__name__):
                payload = public_manifest()
                payload["maximum_seconds"] = value
                with self.assertRaisesRegex(RealityEvalError, "maximum_seconds"):
                    validate_public_manifest(payload)

    def test_final_contract_requires_six_categories(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        for case in contract["questions"]:
            case["category"] = "one-category"

        with self.assertRaisesRegex(RealityEvalError, "at least 6"):
            validate_contract(contract)

    def test_final_contract_requires_exactly_50_cases_and_10_holdouts(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())
        validated = validate_contract(contract)

        self.assertEqual(len(validated["questions"]), QUESTION_COUNT)
        self.assertEqual(sum(case["holdout"] for case in validated["questions"]), 10)
        self.assertGreaterEqual(
            sum(case["kind"] == "domain" for case in validated["questions"]),
            40,
        )
        self.assertTrue(all(not case["holdout"] for case in validated["questions"][:40]))
        self.assertTrue(all(case["holdout"] for case in validated["questions"][40:]))

        missing_case = deepcopy(contract)
        missing_case["questions"].pop()
        with self.assertRaisesRegex(RealityEvalError, "exactly 50"):
            validate_contract(missing_case)

        nine_holdouts = deepcopy(contract)
        nine_holdouts["questions"][-1]["holdout"] = False
        with self.assertRaisesRegex(RealityEvalError, "exactly 10"):
            validate_contract(nine_holdouts)

    def test_assembled_contract_has_installed_validator_shape(self):
        contract = assemble_contract(public_manifest(), holdout_bundle())

        self.assertEqual(
            set(contract),
            {
                "contract_version",
                "target",
                "mode",
                "interface",
                "maximum_seconds",
                "rules",
                "questions",
            },
        )
        self.assertEqual(contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(contract["target"], TARGET)
        self.assertEqual(contract["mode"], "evaluation")
        self.assertEqual(contract["interface"], "codex-app")
        self.assertEqual(contract["maximum_seconds"], 60)
        self.assertEqual(
            contract["rules"],
            {
                "exact_question_required": True,
                "first_attempt_only": True,
                "full_answer_required": True,
                "fresh_task_per_question": True,
                "sibling_answer_routes_forbidden": True,
            },
        )

    def test_holdout_receipt_allows_only_exact_keys_and_hashes_exact_bytes(self):
        bundle = holdout_bundle()
        bundle_bytes = json.dumps(bundle, indent=2).encode("utf-8")
        receipt = build_holdout_receipt(bundle_bytes)

        self.assertEqual(
            set(receipt),
            {
                "receipt_version",
                "target",
                "bundle_version",
                "created_at",
                "question_count",
                "bundle_sha256",
            },
        )
        self.assertEqual(receipt["receipt_version"], HOLDOUT_RECEIPT_VERSION)
        self.assertEqual(receipt["bundle_version"], HOLDOUT_BUNDLE_VERSION)
        self.assertEqual(receipt["created_at"], CREATED_AT)
        self.assertEqual(receipt["question_count"], HOLDOUT_QUESTION_COUNT)
        self.assertEqual(receipt["bundle_sha256"], hashlib.sha256(bundle_bytes).hexdigest())
        self.assertEqual(validate_holdout_receipt(receipt, bundle_bytes=bundle_bytes), receipt)

        receipt_with_extra = {**receipt, "questions": []}
        with self.assertRaisesRegex(RealityEvalError, "keys"):
            validate_holdout_receipt(receipt_with_extra)

    def test_holdout_receipt_rejects_changed_supplied_bytes(self):
        bundle_bytes = json.dumps(holdout_bundle(), indent=2).encode("utf-8")
        receipt = build_holdout_receipt(bundle_bytes)

        with self.assertRaisesRegex(RealityEvalError, "exact bundle bytes"):
            validate_holdout_receipt(receipt, bundle_bytes=bundle_bytes + b"\n")

    def test_holdout_receipt_rejects_fractional_and_covert_timestamps(self):
        bundle_bytes = json.dumps(holdout_bundle(), indent=2).encode("utf-8")
        invalid_timestamps = (
            "2026-07-16T12:00:00.1Z",
            "2026-07-16T12:00:00+00:00",
            "2026-07-16T12:00:00Z hidden-data",
        )
        for created_at in invalid_timestamps:
            with self.subTest(created_at=created_at):
                receipt = build_holdout_receipt(bundle_bytes)
                receipt["created_at"] = created_at
                with self.assertRaisesRegex(RealityEvalError, "created_at"):
                    validate_holdout_receipt(receipt)

    def test_passing_baseline_results(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()

        self.assertEqual(
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            ),
            payload,
        )

    def test_elapsed_time_equal_to_60_is_rejected(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        payload["results"][0]["elapsed_seconds"] = 60.0

        with self.assertRaisesRegex(RealityEvalError, "strict time limit"):
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            )

    def test_missing_recording_is_rejected(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        del payload["recording"]

        with self.assertRaisesRegex(RealityEvalError, "recording"):
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            )

    def test_results_reject_wrong_hash_changed_question_and_alternate_system(self):
        mutations = (
            (("contract_sha256",), "0" * 64, "contract_sha256"),
            (("results", 0, "question"), "Changed question", "exact frozen question"),
            (("results", 0, "answer_systems"), ["ask-monarch"], "alternate answer"),
        )
        for path, value, message in mutations:
            with self.subTest(path=path):
                contract, exact_contract_bytes, payload = passing_result_fixture()
                mutate_path(payload, path, value)
                with self.assertRaisesRegex(RealityEvalError, message):
                    validate_results(
                        payload,
                        contract=contract,
                        contract_bytes=exact_contract_bytes,
                    )

    def test_results_bind_contract_object_to_exact_contract_bytes(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()

        with self.assertRaisesRegex(RealityEvalError, "contract_sha256"):
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes + b"\n",
            )

        mismatched_contract = deepcopy(contract)
        mismatched_contract["questions"][0]["question"] = "Changed parsed contract"
        with self.assertRaisesRegex(RealityEvalError, "contract.*exact contract bytes"):
            validate_results(
                payload,
                contract=mismatched_contract,
                contract_bytes=exact_contract_bytes,
            )

    def test_results_reject_every_non_pass_verdict(self):
        for field in (
            "route_verdict",
            "content_verdict",
            "source_verdict",
            "privacy_verdict",
            "usefulness_verdict",
        ):
            with self.subTest(field=field):
                contract, exact_contract_bytes, payload = passing_result_fixture()
                payload["results"][0][field] = "fail"
                with self.assertRaisesRegex(RealityEvalError, field):
                    validate_results(
                        payload,
                        contract=contract,
                        contract_bytes=exact_contract_bytes,
                    )

    def test_results_require_nonempty_provenance(self):
        mutations = (
            (("results", 0, "provenance"), MISSING),
            (("results", 0, "provenance"), []),
        )
        for path, value in mutations:
            with self.subTest(missing=value is MISSING):
                contract, exact_contract_bytes, payload = passing_result_fixture()
                mutate_path(payload, path, value)
                with self.assertRaisesRegex(RealityEvalError, r"\.provenance"):
                    validate_results(
                        payload,
                        contract=contract,
                        contract_bytes=exact_contract_bytes,
                    )

    def test_results_require_complete_recording_metadata(self):
        mutations = (
            (("recording", "question_count"), 49, "question_count"),
            (
                ("recording", "complete_answers_visible"),
                False,
                "complete_answers_visible",
            ),
            (("recording", "privacy_review"), "fail", "privacy_review"),
            (("recording", "shared_with_josh"), False, "shared_with_josh"),
            (("recording", "recording_path"), MISSING, "recording_path"),
            (("recording", "question_count"), 50.0, "question_count"),
        )
        for path, value, message in mutations:
            with self.subTest(path=path):
                contract, exact_contract_bytes, payload = passing_result_fixture()
                mutate_path(payload, path, value)
                with self.assertRaisesRegex(RealityEvalError, message):
                    validate_results(
                        payload,
                        contract=contract,
                        contract_bytes=exact_contract_bytes,
                    )

    def test_results_require_complete_route_trace(self):
        mutations = (
            (("results", 0, "route_trace"), MISSING, "route_trace"),
            (("results", 0, "route_trace", "thread_id"), MISSING, "thread_id"),
            (("results", 0, "route_trace", "thread_id"), "", "thread_id"),
            (
                ("results", 0, "route_trace", "submitted_at"),
                MISSING,
                "submitted_at",
            ),
            (
                ("results", 0, "route_trace", "submitted_at"),
                "2026-07-16T12:00:00.1Z",
                "submitted_at",
            ),
            (
                ("results", 0, "route_trace", "submitted_at"),
                "2026-07-16T12:00:00+00:00",
                "submitted_at",
            ),
            (
                ("results", 0, "route_trace", "completed_at"),
                MISSING,
                "completed_at",
            ),
            (
                ("results", 0, "route_trace", "completed_at"),
                "2026-07-16T12:00:01Z hidden",
                "completed_at",
            ),
            (
                ("results", 0, "route_trace", "answer_command_count"),
                MISSING,
                "answer_command_count",
            ),
            (
                ("results", 0, "route_trace", "answer_command_count"),
                0,
                "answer_command_count",
            ),
            (
                ("results", 0, "route_trace", "answer_command_count"),
                1.0,
                "answer_command_count",
            ),
            (
                ("results", 0, "route_trace", "answer_command_count"),
                True,
                "answer_command_count",
            ),
            (
                ("results", 0, "route_trace", "hosted_route"),
                MISSING,
                "hosted_route",
            ),
            (
                ("results", 0, "route_trace", "hosted_route"),
                False,
                "hosted_route",
            ),
            (
                ("results", 0, "route_trace", "raw_trace_path"),
                MISSING,
                "raw_trace_path",
            ),
            (
                ("results", 0, "route_trace", "raw_trace_path"),
                "",
                "raw_trace_path",
            ),
            (
                ("results", 0, "route_trace", "raw_trace_path"),
                "relative/trace.json",
                "raw_trace_path",
            ),
        )
        for path, value, message in mutations:
            with self.subTest(path=path, missing=value is MISSING):
                contract, exact_contract_bytes, payload = passing_result_fixture()
                mutate_path(payload, path, value)
                with self.assertRaisesRegex(RealityEvalError, message):
                    validate_results(
                        payload,
                        contract=contract,
                        contract_bytes=exact_contract_bytes,
                    )

    def test_results_require_unique_route_thread_ids(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        payload["results"][1]["route_trace"]["thread_id"] = payload["results"][0][
            "route_trace"
        ]["thread_id"]

        with self.assertRaisesRegex(RealityEvalError, r"thread_id.*unique"):
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            )

    def test_results_reject_route_completion_before_submission(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        route_trace = payload["results"][0]["route_trace"]
        route_trace["submitted_at"] = "2026-07-16T12:00:02Z"
        route_trace["completed_at"] = "2026-07-16T12:00:01Z"

        with self.assertRaisesRegex(RealityEvalError, r"completed_at.*earlier"):
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            )

    def test_results_allow_equal_route_timestamps(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        route_trace = payload["results"][0]["route_trace"]
        route_trace["completed_at"] = route_trace["submitted_at"]

        self.assertIs(
            validate_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            ),
            payload,
        )

    def test_result_numbers_fail_closed(self):
        mutations = (
            (("results", 0, "elapsed_seconds"), float("nan"), "elapsed_seconds"),
            (("results", 0, "elapsed_seconds"), float("inf"), "elapsed_seconds"),
            (("results", 0, "elapsed_seconds"), float("-inf"), "elapsed_seconds"),
            (("results", 0, "elapsed_seconds"), 10**10_000, "elapsed_seconds"),
            (("results", 0, "elapsed_seconds"), True, "elapsed_seconds"),
            (("results", 0, "attempt"), 1.0, "attempt"),
        )
        for index, (path, value, message) in enumerate(mutations):
            with self.subTest(case=index, path=path):
                contract, exact_contract_bytes, payload = passing_result_fixture()
                mutate_path(payload, path, value)
                with self.assertRaisesRegex(RealityEvalError, message):
                    validate_results(
                        payload,
                        contract=contract,
                        contract_bytes=exact_contract_bytes,
                    )

    def test_results_summary_uses_median_and_nearest_rank_p95(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        for index, result in enumerate(payload["results"]):
            result["elapsed_seconds"] = float(index)

        self.assertEqual(
            summarize_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            ),
            {
                "question_count": 50,
                "passed_count": 50,
                "failed_count": 0,
                "p50_seconds": 24.5,
                "p95_seconds": 47.0,
                "maximum_seconds": 49.0,
                "reality_eval_passed": True,
            },
        )

    def test_results_summary_revalidates_before_reporting_pass(self):
        contract, exact_contract_bytes, payload = passing_result_fixture()
        payload["results"][0]["content_verdict"] = "fail"

        with self.assertRaisesRegex(RealityEvalError, "content_verdict"):
            summarize_results(
                payload,
                contract=contract,
                contract_bytes=exact_contract_bytes,
            )

    def test_installed_validator_accepts_exact_compatibility_fixture(self):
        if not INSTALLED_VALIDATOR.exists():
            self.skipTest(f"installed validator not found: {INSTALLED_VALIDATOR}")

        contract, exact_contract_bytes, payload = passing_result_fixture()
        with tempfile.TemporaryDirectory() as temp_dir:
            contract_path = Path(temp_dir) / "contract.json"
            results_path = Path(temp_dir) / "results.json"
            contract_path.write_bytes(exact_contract_bytes)
            results_path.write_bytes(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLED_VALIDATOR),
                    "--contract",
                    str(contract_path),
                    "--results",
                    str(results_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
