import json
import tempfile
import unittest
from pathlib import Path

from askinsects.context_package import (
    DEFAULT_CONTEXT_CONFIG,
    build_context_package,
    load_context_config,
    validate_context_package,
)
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance


def record(
    record_id: str,
    *,
    source: str,
    species: str | None,
    text: str,
    payload: dict | None = None,
    locator: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="insect_intelligence" if source == "insect_intelligence_programs" else "literature",
        source=source,
        title=record_id,
        text=text,
        species=species,
        url=None,
        media_url=None,
        provenance=Provenance(
            source_id=source,
            locator=locator or f"records#{record_id}",
            retrieved_at="2026-07-13T00:00:00Z",
        ),
        payload=payload,
    )


class ContextPackageTests(unittest.TestCase):
    def test_default_config_uses_generic_v2_contract(self):
        self.assertTrue(DEFAULT_CONTEXT_CONFIG.is_absolute())
        self.assertEqual(DEFAULT_CONTEXT_CONFIG.name, "insect-evidence-package.json")
        self.assertTrue(DEFAULT_CONTEXT_CONFIG.is_file())
        config = load_context_config()

        self.assertEqual(
            config["schema_version"],
            "ask-insects-evidence-package-config.v2",
        )
        contexts = config["contexts"]
        self.assertEqual(
            [context["id"] for context in contexts],
            [
                "treated_area_contact_avoidance",
                "treated_area_noncontact_avoidance",
                "bounded_choice_orientation",
                "oviposition_choice",
                "human_landing_response",
                "spatial_behavior",
                "post_exposure_behavior",
            ],
        )
        expected_fields = {
            "id",
            "endpoint_family",
            "exposure_routes",
            "species_ids",
            "required_domains",
            "measures",
            "does_not_establish",
            "plausible_explanations",
            "discriminating_evidence",
            "selectors",
        }
        for context in contexts:
            self.assertEqual(set(context), expected_fields)

        by_id = {context["id"]: context for context in contexts}
        self.assertEqual(
            by_id["treated_area_contact_avoidance"]["exposure_routes"],
            ["contact"],
        )
        self.assertEqual(
            by_id["treated_area_noncontact_avoidance"]["exposure_routes"],
            ["non_contact"],
        )

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.artifact_dir = self.root / "mosquito-v1"
        self.index = SourceIndex(self.artifact_dir / "source_index.sqlite")
        self.index.initialize()
        self.index.upsert_records(
            [
                record(
                    "program:species:swd",
                    source="insect_intelligence_programs",
                    species="Drosophila suzukii",
                    text="Spotted wing drosophila profile.",
                    payload={
                        "atom_type": "species_profile",
                        "species_id": "drosophila_suzukii",
                        "scientific_name": "Drosophila suzukii",
                        "product_ids": ["swd_crop_repellent"],
                    },
                ),
                record(
                    "program:domain:swd:behavior",
                    source="insect_intelligence_programs",
                    species="Drosophila suzukii",
                    text="Behavior is partly covered and important gaps remain.",
                    payload={
                        "atom_type": "knowledge_domain",
                        "species_id": "drosophila_suzukii",
                        "domain": "behavior",
                        "status": "partial_source_grade",
                        "gaps": ["dose-aligned avoidance evidence"],
                    },
                ),
                record(
                    "public:swd:1",
                    source="public_swd_behavior",
                    species="Drosophila suzukii",
                    text="Direct avoidance and repellent behavior was measured in a choice assay.",
                ),
                record(
                    "public:swd:2",
                    source="public_swd_behavior",
                    species="Drosophila suzukii",
                    text="A second direct avoidance and repellent behavior record.",
                ),
                record(
                    "public:melanogaster:1",
                    source="public_swd_behavior",
                    species="Drosophila melanogaster",
                    text="Avoidance and repellent behavior in another fly.",
                ),
            ]
        )
        (self.artifact_dir / "source_status.json").write_text(
            json.dumps({"generated_at": "2026-07-13T00:00:00Z", "record_count": 5}),
            encoding="utf-8",
        )
        self.config_path = self.root / "context-config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "schema_version": "ask-insects-evidence-package-config.v2",
                    "package_version": "2026-07-14.1",
                    "last_reviewed": "2026-07-14",
                    "objective": "Provide public context for private interpretation.",
                    "knowledge_domains": ["behavior"],
                    "contexts": [
                        {
                            "id": "treated_area_contact_avoidance",
                            "endpoint_family": "treated_area_occupancy",
                            "exposure_routes": ["contact"],
                            "species_ids": ["drosophila_suzukii"],
                            "required_domains": ["behavior"],
                            "measures": ["time or occupancy relative to a treated region"],
                            "does_not_establish": ["a proven receptor mechanism"],
                            "plausible_explanations": ["sensory avoidance"],
                            "discriminating_evidence": ["matched contact and non-contact controls"],
                            "selectors": [
                                {
                                    "id": "swd_behavior",
                                    "species_id": "drosophila_suzukii",
                                    "source": "public_swd_behavior",
                                    "query_any": ["avoidance", "repellent", "contact"],
                                    "limit": 1,
                                    "required": True,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def build(self, generated_at: str):
        return build_context_package(
            artifact_dir=self.artifact_dir,
            config_path=self.config_path,
            generated_at=generated_at,
        )

    def test_loader_accepts_generic_context_fields(self):
        config = load_context_config(self.config_path)

        context = config["contexts"][0]
        self.assertEqual(context["endpoint_family"], "treated_area_occupancy")
        self.assertEqual(context["exposure_routes"], ["contact"])

    def test_loader_rejects_private_assay_fields(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))

        for field in ("private_assay_families", "private_assay_modes"):
            with self.subTest(field=field):
                legacy_config = json.loads(json.dumps(config))
                legacy_config["contexts"][0][field] = ["private_value"]
                path = self.root / f"{field}.json"
                path.write_text(json.dumps(legacy_config), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, field):
                    load_context_config(path)

    def test_default_config_preserves_selector_inventory(self):
        config = load_context_config()
        actual = [
            (
                context["id"],
                selector["id"],
                selector["species_id"],
                selector["source"],
                tuple(selector["query_any"]),
                selector["limit"],
                selector["required"],
            )
            for context in config["contexts"]
            for selector in context["selectors"]
        ]

        self.assertEqual(
            actual,
            [
                ("treated_area_contact_avoidance", "contact_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_extracted_facts", ("repellent", "avoidance", "contact"), 4, False),
                ("treated_area_contact_avoidance", "contact_swd_olfaction", "drosophila_suzukii", "drosophila_suzukii_olfaction_literature", ("olfaction", "odor", "host volatile"), 3, False),
                ("treated_area_contact_avoidance", "contact_aedes_behavior", "aedes_aegypti", "aedes_extracted_facts", ("repellent", "avoidance", "contact"), 4, False),
                ("treated_area_contact_avoidance", "contact_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("repellent", "olfaction", "host seeking"), 3, False),
                ("treated_area_noncontact_avoidance", "noncontact_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_extracted_facts", ("repellent", "avoidance", "spatial"), 4, False),
                ("treated_area_noncontact_avoidance", "noncontact_swd_olfaction", "drosophila_suzukii", "drosophila_suzukii_olfaction_literature", ("olfaction", "odor", "host volatile"), 3, False),
                ("treated_area_noncontact_avoidance", "noncontact_aedes_behavior", "aedes_aegypti", "aedes_extracted_facts", ("repellent", "avoidance", "spatial"), 4, False),
                ("treated_area_noncontact_avoidance", "noncontact_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("repellent", "olfaction", "host seeking"), 3, False),
                ("bounded_choice_orientation", "choice_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_extracted_facts", ("choice", "avoidance", "repellent"), 4, False),
                ("bounded_choice_orientation", "choice_swd_flight", "drosophila_suzukii", "drosophila_suzukii_umn_flight_assay_rows", ("flight", "movement", "distance"), 3, False),
                ("bounded_choice_orientation", "choice_aedes_behavior", "aedes_aegypti", "aedes_extracted_facts", ("choice", "avoidance", "repellent"), 4, False),
                ("bounded_choice_orientation", "choice_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("olfaction", "orientation", "host seeking"), 3, False),
                ("oviposition_choice", "oviposition_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_extracted_facts", ("oviposition", "egg laying", "host choice"), 5, False),
                ("oviposition_choice", "oviposition_swd_olfaction", "drosophila_suzukii", "drosophila_suzukii_olfaction_literature", ("oviposition", "fruit odor", "host volatile"), 3, False),
                ("oviposition_choice", "oviposition_dbm_direct", "plutella_xylostella", "plutella_xylostella_oviposition_literature", ("oviposition", "egg laying", "host choice"), 5, False),
                ("human_landing_response", "landing_aedes_host_seeking", "aedes_aegypti", "aedes_olfaction_literature", ("host seeking", "human odor", "landing", "blood feeding"), 6, False),
                ("human_landing_response", "landing_aedes_behavior", "aedes_aegypti", "aedes_extracted_facts", ("landing", "probing", "feeding", "repellent"), 5, False),
                ("spatial_behavior", "spatial_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("spatial repellent", "olfaction", "odor plume", "host seeking"), 6, False),
                ("spatial_behavior", "spatial_aedes_neurobiology", "aedes_aegypti", "aedes_neurobiology_sources", ("olfactory", "sensory neuron", "odor receptor"), 4, False),
                ("post_exposure_behavior", "post_aedes_behavior", "aedes_aegypti", "aedes_extracted_facts", ("post exposure", "recovery", "knockdown", "locomotion"), 5, False),
                ("post_exposure_behavior", "post_aedes_chemical", "aedes_aegypti", "aedes_neurobiology_sources", ("chemical exposure", "locomotor", "recovery", "toxicity"), 4, False),
            ],
        )

    def test_package_selects_only_exact_species_and_respects_limit(self):
        package = self.build("2026-07-14T01:00:00Z")

        self.assertTrue(package["ok"])
        selected = package["evidence_records"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["species"], "Drosophila suzukii")
        self.assertIn(selected[0]["record_id"], {"public:swd:1", "public:swd:2"})
        self.assertEqual(package["selector_results"][0]["selected_count"], 1)
        self.assertEqual(package["selector_results"][0]["limit"], 1)
        self.assertNotIn("public:melanogaster:1", json.dumps(package))

    def test_selector_prefers_records_matching_more_declared_terms(self):
        self.index.upsert_records(
            [
                record(
                    "public:swd:three-matches",
                    source="public_swd_behavior",
                    species="Drosophila suzukii",
                    text="Repellent contact avoidance was measured directly.",
                )
            ]
        )

        package = self.build("2026-07-14T01:00:00Z")

        self.assertEqual(
            package["evidence_records"][0]["record_id"],
            "public:swd:three-matches",
        )

    def test_package_hash_is_stable_across_generation_times(self):
        first = self.build("2026-07-14T01:00:00Z")
        second = self.build("2026-07-14T02:00:00Z")

        self.assertNotEqual(first["generated_at"], second["generated_at"])
        self.assertEqual(first["content_sha256"], second["content_sha256"])

    def test_every_exported_record_has_exact_provenance(self):
        package = self.build("2026-07-14T01:00:00Z")

        for item in [*package["program_records"], *package["evidence_records"]]:
            self.assertTrue(item["provenance"]["source_id"])
            self.assertTrue(item["provenance"]["locator"])
        validate_context_package(package)

    def test_validator_rejects_exported_contexts_missing_generic_fields(self):
        package = self.build("2026-07-14T01:00:00Z")

        for field in ("endpoint_family", "exposure_routes"):
            with self.subTest(field=field):
                invalid = json.loads(json.dumps(package))
                invalid["contexts"][0].pop(field)

                with self.assertRaisesRegex(ValueError, field):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_rejects_exported_contexts_with_private_fields(self):
        package = self.build("2026-07-14T01:00:00Z")

        for field in ("private_assay_families", "private_assay_modes"):
            with self.subTest(field=field):
                invalid = json.loads(json.dumps(package))
                invalid["contexts"][0][field] = ["private_value"]

                with self.assertRaisesRegex(ValueError, field):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_rejects_private_monarch_locator(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["provenance"]["locator"] = (
            "gs://monarch-videos-new/private/results.csv#row=1"
        )

        with self.assertRaisesRegex(ValueError, "private Monarch source"):
            validate_context_package(package, verify_hash=False)

    def test_validator_rejects_hash_mismatch(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["text"] = "changed after hashing"

        with self.assertRaisesRegex(ValueError, "content_sha256"):
            validate_context_package(package)


if __name__ == "__main__":
    unittest.main()
