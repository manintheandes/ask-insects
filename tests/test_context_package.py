import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from askinsects.context_package import (
    DEFAULT_CONTEXT_CONFIG,
    build_context_package,
    load_context_config,
    validate_context_package,
)
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit


def record(
    record_id: str,
    *,
    source: str,
    species: str | None,
    text: str,
    title: str | None = None,
    payload: dict | None = None,
    locator: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="insect_intelligence" if source == "insect_intelligence_programs" else "literature",
        source=source,
        title=title or record_id,
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
                        "common_name": "spotted wing drosophila",
                        "aliases": [
                            "Drosophila suzukii",
                            "spotted wing drosophila",
                            "spotted-wing drosophila",
                            "SWD",
                        ],
                        "product_ids": ["swd_crop_repellent"],
                    },
                ),
                record(
                    "program:species:aedes",
                    source="insect_intelligence_programs",
                    species="Aedes aegypti",
                    text="Yellow fever mosquito profile.",
                    payload={
                        "atom_type": "species_profile",
                        "species_id": "aedes_aegypti",
                        "scientific_name": "Aedes aegypti",
                        "common_name": "yellow fever mosquito",
                        "aliases": [
                            "Aedes aegypti",
                            "yellow fever mosquito",
                            "Aedes",
                            "Ae. aegypti",
                            "mosquito",
                        ],
                        "product_ids": ["human_mosquito_repellent"],
                    },
                ),
                record(
                    "program:species:dbm",
                    source="insect_intelligence_programs",
                    species="Plutella xylostella",
                    text="Diamondback moth profile.",
                    payload={
                        "atom_type": "species_profile",
                        "species_id": "plutella_xylostella",
                        "scientific_name": "Plutella xylostella",
                        "common_name": "diamondback moth",
                        "aliases": [
                            "Plutella xylostella",
                            "diamondback moth",
                            "diamond back moth",
                            "DBM",
                        ],
                        "product_ids": [],
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
                    payload={
                        "title": "Drosophila suzukii contact avoidance assay",
                        "abstract": "Direct contact avoidance and repellent behavior was measured.",
                    },
                ),
                record(
                    "public:swd:2",
                    source="public_swd_behavior",
                    species="Drosophila suzukii",
                    text="A second direct avoidance and repellent behavior record.",
                    payload={
                        "title": "Spotted wing drosophila avoidance behavior",
                        "abstract": "A second direct contact avoidance record.",
                    },
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
            json.dumps({"generated_at": "2026-07-13T00:00:00Z", "record_count": 7}),
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
                                    "context_required_term_groups": [
                                        ["contact", "surface", "inside zone", "inside-zone"]
                                    ],
                                    "taxon_field_paths": ["payload.title"],
                                    "context_field_paths": ["payload.abstract"],
                                    "context_field_prerequisites": {},
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
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        with patch("askinsects.context_package.load_context_config", return_value=config):
            return build_context_package(
                artifact_dir=self.artifact_dir,
                config_path=self.config_path,
                generated_at=generated_at,
            )

    def build_with_contexts(self, contexts: list[dict], generated_at: str = "2026-07-14T01:00:00Z"):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["contexts"] = contexts
        with patch("askinsects.context_package.load_context_config", return_value=config):
            return build_context_package(
                artifact_dir=self.artifact_dir,
                config_path=self.config_path,
                generated_at=generated_at,
            )

    @staticmethod
    def context(context_id: str, species_ids: list[str], selectors: list[dict]) -> dict:
        return {
            "id": context_id,
            "endpoint_family": context_id,
            "exposure_routes": ["contact"],
            "species_ids": species_ids,
            "required_domains": ["behavior"],
            "measures": [f"direct {context_id} behavior"],
            "does_not_establish": ["a product claim"],
            "plausible_explanations": ["sensory behavior"],
            "discriminating_evidence": ["matched controls"],
            "selectors": selectors,
        }

    @staticmethod
    def selector(
        selector_id: str,
        species_id: str,
        source: str,
        *,
        query_any: list[str],
        context_required_term_groups: list[list[str]],
        limit: int = 5,
        taxon_field_paths: list[str] | None = None,
        context_field_paths: list[str] | None = None,
        context_field_prerequisites: dict[str, list[str]] | None = None,
        parent_record: dict | None = None,
        fulltext_context: dict | None = None,
        record_requirements: dict[str, str] | None = None,
    ) -> dict:
        selector = {
            "id": selector_id,
            "species_id": species_id,
            "source": source,
            "query_any": query_any,
            "context_required_term_groups": context_required_term_groups,
            "taxon_field_paths": taxon_field_paths or [],
            "context_field_paths": context_field_paths or [],
            "context_field_prerequisites": context_field_prerequisites or {},
            "limit": limit,
            "required": False,
        }
        if parent_record is not None:
            selector["parent_record"] = parent_record
        if fulltext_context is not None:
            selector["fulltext_context"] = fulltext_context
        if record_requirements is not None:
            selector["record_requirements"] = record_requirements
        return selector

    @staticmethod
    def fulltext_context() -> dict[str, str]:
        return {
            "unit_id_path": "payload.fulltext_unit_id",
            "parent_record_id_path": "payload.source_record_id",
            "text_field_path": "literature_fulltext_units.text",
        }

    def build_multi_context_package(self):
        self.index.upsert_records(
            [
                record(
                    "shared:direct:1",
                    source="shared_direct_evidence",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance and oviposition choice candidate.",
                    payload={
                        "title": "Drosophila suzukii behavior study",
                        "abstract": "Contact avoidance and oviposition choice were measured directly.",
                    },
                )
            ]
        )
        contexts = [
            self.context(
                "contact_context",
                ["drosophila_suzukii"],
                [
                    self.selector(
                        "shared_contact",
                        "drosophila_suzukii",
                        "shared_direct_evidence",
                        query_any=["contact", "avoidance"],
                        context_required_term_groups=[["contact", "surface"]],
                        taxon_field_paths=["payload.title"],
                        context_field_paths=["payload.abstract"],
                    )
                ],
            ),
            self.context(
                "oviposition_context",
                ["drosophila_suzukii"],
                [
                    self.selector(
                        "shared_oviposition",
                        "drosophila_suzukii",
                        "shared_direct_evidence",
                        query_any=["oviposition", "choice"],
                        context_required_term_groups=[["oviposition", "egg laying"]],
                        taxon_field_paths=["payload.title"],
                        context_field_paths=["payload.abstract"],
                    )
                ],
            ),
        ]
        return self.build_with_contexts(contexts)

    def build_linked_fulltext_package(self):
        self.index.upsert_records(
            [
                record(
                    "parent:validator:swd",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Drosophila suzukii behavior",
                            "abstract_inverted_index": {},
                        }
                    },
                ),
                record(
                    "derived:validator:swd",
                    source="derived_validator_evidence",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:validator:swd",
                        "fulltext_unit_id": "unit:validator:swd",
                        "evidence_text": "Generated repellent summary.",
                    },
                ),
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:validator:swd",
                    record_id="parent:validator:swd",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Contact avoidance was measured on a treated surface.",
                    url=None,
                    license=None,
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:validator:swd",
                        retrieved_at="2026-07-13T00:00:00Z",
                    ),
                )
            ]
        )
        selector = self.selector(
            "derived_validator",
            "drosophila_suzukii",
            "derived_validator_evidence",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["contact", "surface"]],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            },
            fulltext_context=self.fulltext_context(),
        )
        return self.build_with_contexts(
            [self.context("derived_validator_context", ["drosophila_suzukii"], [selector])]
        )

    def test_loader_accepts_generic_context_fields(self):
        config = load_context_config(self.config_path)

        context = config["contexts"][0]
        self.assertEqual(context["endpoint_family"], "treated_area_occupancy")
        self.assertEqual(context["exposure_routes"], ["contact"])

    def test_default_config_declares_trusted_fields_for_every_selector(self):
        config = load_context_config()

        selectors = [
            selector
            for context in config["contexts"]
            for selector in context["selectors"]
        ]
        self.assertTrue(selectors)
        for selector in selectors:
            with self.subTest(selector=selector["id"]):
                self.assertIn("taxon_field_paths", selector)
                self.assertIn("context_field_paths", selector)
                self.assertIn("context_field_prerequisites", selector)
                self.assertIn("context_required_term_groups", selector)
                self.assertNotIn("context_terms", selector)

        derived = [
            selector
            for selector in selectors
            if selector["source"] in {
                "drosophila_suzukii_extracted_facts",
                "aedes_extracted_facts",
            }
        ]
        self.assertTrue(derived)
        self.assertTrue(all("parent_record" in selector for selector in derived))
        for selector in derived:
            self.assertEqual(
                selector["parent_record"]["taxon_field_paths"],
                [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            )
            self.assertEqual(selector["fulltext_context"], self.fulltext_context())
            self.assertNotIn("payload.evidence_text", selector["context_field_paths"])

        flight = next(selector for selector in selectors if selector["id"] == "choice_swd_flight")
        self.assertEqual(
            flight["record_requirements"],
            {"payload.atom_type": "umn_flight_assay_dataset"},
        )

    def test_default_config_requires_context_defining_terms_not_generic_repellent(self):
        expected_groups = {
            "treated_area_contact_avoidance": [
                ["contact", "surface", "inside zone", "inside-zone"]
            ],
            "treated_area_noncontact_avoidance": [
                ["non-contact", "noncontact", "spatial", "airborne", "vapor", "plume"]
            ],
            "bounded_choice_orientation": [
                ["choice", "orientation", "Y-tube", "Y tube", "olfactometer"]
            ],
            "oviposition_choice": [["oviposition", "egg laying", "egg-laying"]],
            "human_landing_response": [
                [
                    "landing",
                    "probing",
                    "blood feeding",
                    "blood-feeding",
                    "human host",
                    "human-host",
                ]
            ],
            "spatial_behavior": [
                ["spatial", "airborne", "plume", "non-contact", "noncontact"]
            ],
            "post_exposure_behavior": [
                [
                    "post exposure",
                    "post-exposure",
                    "recovery",
                    "knockdown",
                    "after exposure",
                    "after-exposure",
                ]
            ],
        }

        for context in load_context_config()["contexts"]:
            for selector in context["selectors"]:
                with self.subTest(context=context["id"], selector=selector["id"]):
                    self.assertEqual(
                        selector["context_required_term_groups"],
                        expected_groups[context["id"]],
                    )
                    self.assertNotIn("repellent", selector["context_required_term_groups"][0])

    def test_loader_rejects_untrusted_candidate_field_paths(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))

        for field_path in (
            "species",
            "source",
            "title",
            "text",
            "payload.generated_title",
            "payload.generated_text",
            "payload.source",
            "payload.source_id",
            "payload.query",
            "payload.query_any",
            "payload.search",
            "payload.search_term",
            "payload.openalex_search_term",
            "payload.scope",
            "payload.inclusion_paths",
            "payload.source_record_id",
            "payload.matched_record_ids",
            "payload.candidate_source",
            "payload.matched_sources",
            "payload.arbitrary_retained_claim",
            "payload.primary_taxon",
        ):
            with self.subTest(field_path=field_path):
                invalid = json.loads(json.dumps(config))
                invalid["contexts"][0]["selectors"][0]["taxon_field_paths"] = [field_path]
                path = self.root / f"invalid-{field_path.replace('.', '-')}.json"
                path.write_text(json.dumps(invalid), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "trusted field path"):
                    load_context_config(path)

    def test_loader_rejects_payload_evidence_text_as_retained_fulltext(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        selector = config["contexts"][0]["selectors"][0]
        selector["context_field_paths"] = ["payload.evidence_text"]
        selector["context_field_prerequisites"] = {
            "payload.evidence_text": ["payload.fulltext_unit_id"]
        }
        path = self.root / "missing-evidence-prerequisite.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "trusted field path"):
            load_context_config(path)

    def test_loader_requires_exact_parent_fulltext_and_requirement_paths(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        selector = config["contexts"][0]["selectors"][0]
        selector["parent_record"] = {
            "record_id_path": "payload.source_record_id",
            "taxon_field_paths": [
                "payload.raw_openalex_work.display_name",
                "payload.raw_openalex_work.abstract_inverted_index",
            ],
        }
        selector["fulltext_context"] = {
            "unit_id_path": "payload.fulltext_unit_id",
            "parent_record_id_path": "payload.source_record_id",
            "text_field_path": "literature_fulltext_units.text",
        }

        invalid_values = (
            ("parent_record", "taxon_field_paths", ["title"]),
            ("parent_record", "record_id_path", "payload.candidate_parent_id"),
            ("fulltext_context", "unit_id_path", "payload.fabricated_unit_id"),
            ("fulltext_context", "text_field_path", "payload.evidence_text"),
        )
        for section, field, value in invalid_values:
            with self.subTest(section=section, field=field):
                invalid = json.loads(json.dumps(config))
                invalid["contexts"][0]["selectors"][0][section][field] = value
                path = self.root / f"invalid-{section}-{field}.json"
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "path"):
                    load_context_config(path)

        invalid = json.loads(json.dumps(config))
        invalid["contexts"][0]["selectors"][0]["record_requirements"] = {
            "payload.source": "umn_flight_assay_dataset"
        }
        path = self.root / "invalid-record-requirement.json"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "record requirement"):
            load_context_config(path)

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
                    payload={
                        "title": "Drosophila suzukii contact avoidance assay",
                        "abstract": "Repellent contact avoidance was measured directly.",
                    },
                )
            ]
        )

        package = self.build("2026-07-14T01:00:00Z")

        self.assertEqual(
            package["evidence_records"][0]["record_id"],
            "public:swd:three-matches",
        )

    def test_contaminated_database_species_rows_are_rejected_and_selection_continues(self):
        contaminated = [
            (
                "contaminated:tick",
                "Haemaphysalis longicornis tick repellency",
                "Tick contact avoidance and repellent activity were measured.",
            ),
            (
                "contaminated:beetle",
                "Tribolium castaneum Y-tube repellency",
                "Tribolium castaneum contact avoidance was measured in a Y-tube.",
            ),
            (
                "contaminated:melanogaster",
                "Drosophila melanogaster TRPA1 avoidance",
                "Drosophila melanogaster contact repellent avoidance was measured.",
            ),
            (
                "contaminated:generic",
                "Generic insect oviposition",
                "Generic insect oviposition without a focal-species observation.",
            ),
        ]
        self.index.upsert_records(
            [
                record(
                    record_id,
                    source="public_swd_behavior",
                    species="Drosophila suzukii",
                    text="Generated Drosophila suzukii repellent contact avoidance candidate.",
                    payload={
                        "title": source_title,
                        "abstract": source_text,
                        "primary_taxon": "Drosophila suzukii",
                        "query": "Drosophila suzukii repellent",
                        "scope": "Drosophila suzukii behavior",
                        "matched_record_ids": ["public:swd:1"],
                    },
                )
                for record_id, source_title, source_text in contaminated
            ]
        )

        package = self.build("2026-07-14T01:00:00Z")

        selected_ids = {item["record_id"] for item in package["evidence_records"]}
        self.assertTrue(selected_ids.intersection({"public:swd:1", "public:swd:2"}))
        self.assertFalse(selected_ids.intersection({item[0] for item in contaminated}))
        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 6)
        self.assertEqual(receipt["rejection_counts"], {"taxon_not_directly_confirmed": 4})

    def test_generic_repellent_evidence_cannot_cross_contexts(self):
        context_cases = [
            (
                "treated_area_contact_avoidance",
                ["contact", "surface", "inside zone", "inside-zone"],
                "Contact with a treated surface was measured.",
            ),
            (
                "treated_area_noncontact_avoidance",
                ["non-contact", "noncontact", "spatial", "airborne", "vapor", "plume"],
                "Airborne vapor plume avoidance was measured.",
            ),
            (
                "bounded_choice_orientation",
                ["choice", "orientation", "Y-tube", "Y tube", "olfactometer"],
                "Orientation choice in a Y-tube olfactometer was measured.",
            ),
            (
                "oviposition_choice",
                ["oviposition", "egg laying", "egg-laying"],
                "Oviposition and egg-laying choice were measured.",
            ),
            (
                "human_landing_response",
                [
                    "landing",
                    "probing",
                    "blood feeding",
                    "blood-feeding",
                    "human host",
                    "human-host",
                ],
                "Landing and probing on a human host were measured.",
            ),
            (
                "spatial_behavior",
                ["spatial", "airborne", "plume", "non-contact", "noncontact"],
                "Spatial airborne plume behavior was measured.",
            ),
            (
                "post_exposure_behavior",
                [
                    "post exposure",
                    "post-exposure",
                    "recovery",
                    "knockdown",
                    "after exposure",
                    "after-exposure",
                ],
                "Recovery and knockdown were measured after-exposure.",
            ),
        ]
        records = []
        contexts = []
        for context_id, defining_terms, direct_text in context_cases:
            source = f"context_specific_{context_id}"
            records.extend(
                [
                    record(
                        f"generic:{context_id}",
                        source=source,
                        species="Drosophila suzukii",
                        text="Generated repellent candidate.",
                        payload={
                            "title": "Drosophila suzukii repellent study",
                            "abstract": "Repellent activity was measured.",
                        },
                    ),
                    record(
                        f"direct:{context_id}",
                        source=source,
                        species="Drosophila suzukii",
                        text="Generated repellent candidate.",
                        payload={
                            "title": "Drosophila suzukii repellent study",
                            "abstract": direct_text,
                        },
                    ),
                ]
            )
            contexts.append(
                self.context(
                    context_id,
                    ["drosophila_suzukii"],
                    [
                        self.selector(
                            f"selector_{context_id}",
                            "drosophila_suzukii",
                            source,
                            query_any=["repellent"],
                            context_required_term_groups=[defining_terms],
                            taxon_field_paths=["payload.title"],
                            context_field_paths=["payload.abstract"],
                        )
                    ],
                )
            )
        self.index.upsert_records(records)

        package = self.build_with_contexts(contexts)

        self.assertEqual(
            {item["record_id"] for item in package["evidence_records"]},
            {f"direct:{context_id}" for context_id, _, _ in context_cases},
        )
        for receipt in package["selector_results"]:
            self.assertEqual(receipt["candidate_count"], 2)
            self.assertEqual(receipt["selected_count"], 1)
            self.assertEqual(
                receipt["rejection_counts"],
                {"context_not_directly_confirmed": 1},
            )

    def test_direct_swd_aedes_and_dbm_records_include_eligibility_basis(self):
        direct_records = [
            ("direct:swd", "drosophila_suzukii", "Drosophila suzukii"),
            ("direct:aedes", "aedes_aegypti", "Aedes aegypti"),
            ("direct:dbm", "plutella_xylostella", "Plutella xylostella"),
        ]
        self.index.upsert_records(
            [
                record(
                    record_id,
                    source="mapped_direct_evidence",
                    species=scientific_name,
                    text="Generated oviposition choice candidate.",
                    payload={
                        "title": f"{scientific_name} oviposition study",
                        "abstract": "Oviposition choice was measured with matched controls.",
                    },
                )
                for record_id, _, scientific_name in direct_records
            ]
            + [
                record(
                    "direct:aedes:ambiguous-alias",
                    source="mapped_direct_evidence",
                    species="Aedes aegypti",
                    text="Generated oviposition choice candidate for Aedes aegypti.",
                    payload={
                        "title": "Aedes mosquito oviposition study",
                        "abstract": "Oviposition choice was measured with matched controls.",
                    },
                )
            ]
        )
        contexts = [
            self.context(
                f"direct_{species_id}",
                [species_id],
                [
                    self.selector(
                        f"selector_{species_id}",
                        species_id,
                        "mapped_direct_evidence",
                        query_any=["oviposition", "choice"],
                        context_required_term_groups=[["oviposition", "egg laying"]],
                        taxon_field_paths=["payload.title"],
                        context_field_paths=["payload.abstract"],
                    )
                ],
            )
            for _, species_id, _ in direct_records
        ]

        package = self.build_with_contexts(contexts)

        self.assertEqual(
            {item["record_id"] for item in package["evidence_records"]},
            {item[0] for item in direct_records},
        )
        for item in package["evidence_records"]:
            eligibility = item["eligibility"]
            self.assertEqual(eligibility["ruleset_version"], "direct-semantic-evidence.v1")
            self.assertEqual(eligibility["taxon"]["status"], "direct_focal_taxon")
            self.assertEqual(eligibility["context"]["status"], "direct_context")
            for basis in [*eligibility["taxon"]["basis"], *eligibility["context"]["basis"]]:
                self.assertTrue({"field_path", "matched_term", "excerpt"}.issubset(basis))
            if item["species_id"] == "aedes_aegypti":
                self.assertNotIn(
                    eligibility["taxon"]["basis"][0]["matched_term"],
                    {"Aedes", "mosquito"},
                )

    def test_derived_fact_uses_parent_taxon_and_current_context(self):
        self.index.upsert_records(
            [
                record(
                    "parent:swd:paper",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    title="Generated database title without the focal taxon",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Retained paper title",
                            "abstract_inverted_index": {
                                "Drosophila": [0],
                                "suzukii": [1],
                                "behavior": [2],
                            },
                        }
                    },
                ),
                record(
                    "derived:swd:fact",
                    source="derived_direct_evidence",
                    species="Drosophila suzukii",
                    text="Generated Drosophila suzukii contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:swd:paper",
                        "fulltext_unit_id": "unit:1",
                        "evidence_text": "Repellent activity was generated by the extractor.",
                    },
                ),
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:1",
                    record_id="parent:swd:paper",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Contact avoidance was measured in the retained fulltext passage.",
                    url="https://example.test/swd-paper#unit-1",
                    license="CC BY 4.0",
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:1",
                        retrieved_at="2026-07-13T00:00:00Z",
                    ),
                )
            ]
        )
        selector = self.selector(
            "derived_swd",
            "drosophila_suzukii",
            "derived_direct_evidence",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["contact", "surface"]],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            },
            fulltext_context=self.fulltext_context(),
        )

        package = self.build_with_contexts(
            [self.context("derived_contact", ["drosophila_suzukii"], [selector])]
        )

        item = package["evidence_records"][0]
        self.assertEqual(item["record_id"], "derived:swd:fact")
        self.assertEqual(
            item["eligibility"]["taxon"]["basis"][0]["field_path"],
            "parent.payload.raw_openalex_work.abstract_inverted_index",
        )
        taxon_basis = item["eligibility"]["taxon"]["basis"][0]
        self.assertEqual(taxon_basis["parent_record_id"], "parent:swd:paper")
        self.assertEqual(taxon_basis["retained_source"], "public_parent_literature")
        self.assertEqual(
            taxon_basis["retained_path"],
            "payload.raw_openalex_work.abstract_inverted_index",
        )
        context_basis = item["eligibility"]["context"]["basis"][0]
        self.assertEqual(context_basis["fulltext_unit_id"], "unit:1")
        self.assertEqual(context_basis["parent_record_id"], "parent:swd:paper")
        self.assertEqual(context_basis["retained_source"], "public_parent_literature")
        self.assertEqual(context_basis["retained_path"], "literature_fulltext_units.text")
        for basis in (taxon_basis, context_basis):
            self.assertTrue(basis["evidence_snapshot"])
            self.assertRegex(basis["evidence_sha256"], r"^[0-9a-f]{64}$")

    def test_derived_fact_rejects_missing_parent(self):
        self.index.upsert_records(
            [
                record(
                    "derived:missing-parent",
                    source="derived_missing_parent",
                    species="Drosophila suzukii",
                    text="Generated Drosophila suzukii contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:does-not-exist",
                        "fulltext_unit_id": "unit:missing-parent",
                        "evidence_text": "Contact avoidance was measured.",
                    },
                )
            ]
        )
        selector = self.selector(
            "missing_parent",
            "drosophila_suzukii",
            "derived_missing_parent",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["contact", "surface"]],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            },
            fulltext_context=self.fulltext_context(),
        )

        package = self.build_with_contexts(
            [self.context("missing_parent_context", ["drosophila_suzukii"], [selector])]
        )

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {"upstream_record_missing": 1},
        )

    def test_parent_top_level_title_cannot_prove_derived_taxon(self):
        self.index.upsert_records(
            [
                record(
                    "parent:top-level-only",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    title="Drosophila suzukii retained paper title",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Generic insect behavior paper",
                            "abstract_inverted_index": {
                                "Generic": [0],
                                "repellent": [1],
                                "study": [2],
                            },
                        }
                    },
                ),
                record(
                    "derived:top-level-parent-title",
                    source="derived_top_level_parent_title",
                    species="Drosophila suzukii",
                    text="Generated Drosophila suzukii contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:top-level-only",
                        "fulltext_unit_id": "unit:top-level-only",
                        "evidence_text": "Contact avoidance was measured.",
                    },
                ),
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:top-level-only",
                    record_id="parent:top-level-only",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Contact avoidance was measured.",
                    url=None,
                    license=None,
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:top-level-only",
                        retrieved_at="2026-07-13T00:00:00Z",
                    ),
                )
            ]
        )
        selector = self.selector(
            "top_level_parent_title",
            "drosophila_suzukii",
            "derived_top_level_parent_title",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["contact", "surface"]],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            },
            fulltext_context=self.fulltext_context(),
        )

        package = self.build_with_contexts(
            [self.context("top_level_parent_context", ["drosophila_suzukii"], [selector])]
        )

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {"taxon_not_directly_confirmed": 1},
        )

    def test_fulltext_context_requires_existing_unit_linked_to_parent(self):
        self.index.upsert_records(
            [
                record(
                    "parent:linked:swd",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Drosophila suzukii behavior",
                            "abstract_inverted_index": {},
                        }
                    },
                ),
                record(
                    "derived:missing-unit",
                    source="derived_invalid_fulltext_link",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:linked:swd",
                        "fulltext_unit_id": "unit:does-not-exist",
                        "evidence_text": "Contact avoidance was fabricated here.",
                    },
                ),
                record(
                    "derived:mismatched-unit",
                    source="derived_invalid_fulltext_link",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:linked:swd",
                        "fulltext_unit_id": "unit:belongs-elsewhere",
                        "evidence_text": "Contact avoidance was fabricated here.",
                    },
                ),
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:belongs-elsewhere",
                    record_id="parent:another-paper",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Contact avoidance was measured.",
                    url=None,
                    license=None,
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:belongs-elsewhere",
                        retrieved_at="2026-07-13T00:00:00Z",
                    ),
                )
            ]
        )
        selector = self.selector(
            "invalid_fulltext_link",
            "drosophila_suzukii",
            "derived_invalid_fulltext_link",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["contact", "surface"]],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            },
            fulltext_context=self.fulltext_context(),
        )

        package = self.build_with_contexts(
            [self.context("invalid_fulltext_context", ["drosophila_suzukii"], [selector])]
        )

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {"fulltext_unit_link_invalid": 2},
        )

    def test_missing_retained_parent_fields_reject_explicitly(self):
        self.index.upsert_records(
            [
                record(
                    "parent:no-raw-fields",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    title="Drosophila suzukii generated title",
                    text="Indexed parent paper.",
                    payload={},
                ),
                record(
                    "derived:no-parent-fields",
                    source="derived_missing_trusted_field",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "source_record_id": "parent:no-raw-fields",
                        "fulltext_unit_id": None,
                    },
                ),
            ]
        )
        selector = self.selector(
            "missing_trusted_field",
            "drosophila_suzukii",
            "derived_missing_trusted_field",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["contact", "surface"]],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            },
            fulltext_context=self.fulltext_context(),
        )

        package = self.build_with_contexts(
            [self.context("missing_trusted_context", ["drosophila_suzukii"], [selector])]
        )

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {"trusted_field_missing": 1},
        )

    def test_flight_selector_accepts_only_dataset_atom(self):
        flight_records = []
        for atom_type in (
            "umn_flight_assay_dataset",
            "umn_flight_assay_file",
            "umn_flight_assay_row",
        ):
            flight_records.append(
                record(
                    f"flight:{atom_type}",
                    source="flight_atom_evidence",
                    species="Drosophila suzukii",
                    text="Generated flight orientation candidate.",
                    payload={
                        "atom_type": atom_type,
                        "title": "Drosophila suzukii flight orientation dataset",
                        "abstract": "Choice and orientation were measured in a Y-tube.",
                    },
                )
            )
        self.index.upsert_records(flight_records)
        selector = self.selector(
            "flight_dataset_only",
            "drosophila_suzukii",
            "flight_atom_evidence",
            query_any=["flight", "orientation"],
            context_required_term_groups=[
                ["choice", "orientation", "Y-tube", "Y tube", "olfactometer"]
            ],
            taxon_field_paths=["payload.title", "payload.abstract"],
            context_field_paths=["payload.title", "payload.abstract"],
            record_requirements={"payload.atom_type": "umn_flight_assay_dataset"},
        )

        package = self.build_with_contexts(
            [self.context("flight_dataset_context", ["drosophila_suzukii"], [selector])]
        )

        self.assertEqual(
            [item["record_id"] for item in package["evidence_records"]],
            ["flight:umn_flight_assay_dataset"],
        )
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {"record_requirement_not_met": 2},
        )

    def test_unretained_flight_neurobiology_and_unmapped_dbm_rows_reject_explicitly(self):
        self.index.upsert_records(
            [
                record(
                    "flight:row-without-parent",
                    source="flight_rows_without_parent",
                    species="Drosophila suzukii",
                    text="Generated Drosophila suzukii flight distance candidate.",
                    payload={
                        "atom_type": "umn_flight_assay_row",
                        "assay": "tethered flight mill",
                        "table_row": {"distancecm": "42"},
                    },
                ),
                record(
                    "neuro:hard-coded-atom",
                    source="hard_coded_neurobiology",
                    species="Aedes aegypti",
                    text="Generated Aedes aegypti olfactory sensory neuron candidate.",
                    payload={
                        "title": "Aedes aegypti olfactory sensory neurons",
                        "text": "Hard-coded neurobiology atom.",
                        "keywords": ["olfactory", "sensory neuron"],
                    },
                ),
                record(
                    "dbm:unmapped-candidate",
                    source="unmapped_dbm_literature",
                    species="Plutella xylostella",
                    text="Generated Plutella xylostella oviposition candidate.",
                    payload={
                        "title": "Plutella xylostella oviposition",
                        "abstract": "Diamondback moth egg laying was measured.",
                    },
                ),
            ]
        )
        contexts = [
            self.context(
                "flight_context",
                ["drosophila_suzukii"],
                [
                    self.selector(
                        "flight_without_parent",
                        "drosophila_suzukii",
                        "flight_rows_without_parent",
                        query_any=["flight", "distance"],
                        context_required_term_groups=[["choice", "orientation", "Y-tube"]],
                        taxon_field_paths=["payload.title", "payload.abstract"],
                        context_field_paths=["payload.title", "payload.abstract"],
                        record_requirements={
                            "payload.atom_type": "umn_flight_assay_dataset"
                        },
                    )
                ],
            ),
            self.context(
                "neurobiology_context",
                ["aedes_aegypti"],
                [
                    self.selector(
                        "hard_coded_neurobiology",
                        "aedes_aegypti",
                        "hard_coded_neurobiology",
                        query_any=["olfactory", "sensory neuron"],
                        context_required_term_groups=[["spatial", "airborne", "plume"]],
                    )
                ],
            ),
            self.context(
                "unmapped_dbm_context",
                ["plutella_xylostella"],
                [
                    self.selector(
                        "unmapped_dbm",
                        "plutella_xylostella",
                        "unmapped_dbm_literature",
                        query_any=["oviposition"],
                        context_required_term_groups=[["oviposition", "egg laying"]],
                    )
                ],
            ),
        ]

        package = self.build_with_contexts(contexts)

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(
            {
                result["selector_id"]: result["rejection_counts"]
                for result in package["selector_results"]
            },
            {
                "flight_without_parent": {"record_requirement_not_met": 1},
                "hard_coded_neurobiology": {"trusted_field_missing": 1},
                "unmapped_dbm": {"trusted_field_missing": 1},
            },
        )

    def test_one_record_preserves_direct_basis_for_every_context(self):
        package = self.build_multi_context_package()

        self.assertEqual(len(package["evidence_records"]), 1)
        item = package["evidence_records"][0]
        self.assertEqual(
            item["context_ids"],
            ["contact_context", "oviposition_context"],
        )
        self.assertEqual(
            {basis["context_id"] for basis in item["eligibility"]["context"]["basis"]},
            {"contact_context", "oviposition_context"},
        )

    def test_selector_receipt_counts_all_rejections(self):
        candidates = [
            ("receipt:eligible", "Drosophila suzukii assay", "Avoidance was measured."),
            ("receipt:tick", "Haemaphysalis longicornis assay", "Avoidance was measured."),
            ("receipt:melanogaster", "Drosophila melanogaster assay", "Avoidance was measured."),
            ("receipt:no-context", "Drosophila suzukii assay", "Adult locomotion was measured."),
        ]
        self.index.upsert_records(
            [
                record(
                    record_id,
                    source="receipt_evidence",
                    species="Drosophila suzukii",
                    text="Generated avoidance candidate.",
                    payload={"title": source_title, "abstract": source_text},
                )
                for record_id, source_title, source_text in candidates
            ]
        )
        selector = self.selector(
            "receipt_selector",
            "drosophila_suzukii",
            "receipt_evidence",
            query_any=["avoidance"],
            context_required_term_groups=[["avoidance"]],
            limit=1,
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        package = self.build_with_contexts(
            [self.context("receipt_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 4)
        self.assertEqual(receipt["selected_count"], 1)
        self.assertEqual(receipt["selected_record_ids"], ["receipt:eligible"])
        self.assertEqual(
            receipt["rejection_counts"],
            {
                "context_not_directly_confirmed": 1,
                "taxon_not_directly_confirmed": 2,
            },
        )

    def test_empty_selector_emits_direct_evidence_gap_with_same_receipt(self):
        self.index.upsert_records(
            [
                record(
                    "gap:tick",
                    source="gap_evidence",
                    species="Drosophila suzukii",
                    text="Generated avoidance candidate.",
                    payload={
                        "title": "Haemaphysalis longicornis avoidance",
                        "abstract": "Avoidance was measured.",
                    },
                )
            ]
        )
        selector = self.selector(
            "gap_selector",
            "drosophila_suzukii",
            "gap_evidence",
            query_any=["avoidance"],
            context_required_term_groups=[["avoidance"]],
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        package = self.build_with_contexts(
            [self.context("gap_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["selected_count"], 0)
        self.assertEqual(len(package["gaps"]), 1)
        gap = package["gaps"][0]
        self.assertEqual(gap["gap_type"], "selector_no_direct_evidence")
        for field in (
            "context_id",
            "selector_id",
            "species_id",
            "candidate_count",
            "selected_count",
            "selected_record_ids",
            "rejection_counts",
        ):
            self.assertEqual(gap[field], receipt[field])

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

    def test_validator_rejects_taxon_assertion_that_disagrees_with_receipt(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["eligibility"]["taxon"]["species_id"] = "aedes_aegypti"

        with self.assertRaisesRegex(ValueError, "taxon assertion"):
            validate_context_package(package, verify_hash=False)

    def test_validator_rejects_incomplete_assertion_basis(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["eligibility"]["taxon"]["basis"][0].pop("field_path")

        with self.assertRaisesRegex(ValueError, "basis.*field_path"):
            validate_context_package(package, verify_hash=False)

    def test_validator_requires_basis_for_every_selected_context(self):
        package = self.build_multi_context_package()
        basis = package["evidence_records"][0]["eligibility"]["context"]["basis"]
        package["evidence_records"][0]["eligibility"]["context"]["basis"] = [
            item for item in basis if item["context_id"] != "oviposition_context"
        ]

        with self.assertRaisesRegex(ValueError, "context assertion.*oviposition_context"):
            validate_context_package(package, verify_hash=False)

    def test_validator_requires_exact_reverse_selector_receipts(self):
        self.index.upsert_records(
            [
                record(
                    "reverse:shared:1",
                    source="reverse_receipt_evidence",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "title": "Drosophila suzukii contact behavior",
                        "abstract": "Contact avoidance was measured on a treated surface.",
                    },
                )
            ]
        )
        selectors = [
            self.selector(
                selector_id,
                "drosophila_suzukii",
                "reverse_receipt_evidence",
                query_any=["contact", "avoidance"],
                context_required_term_groups=[["contact", "surface"]],
                taxon_field_paths=["payload.title"],
                context_field_paths=["payload.abstract"],
            )
            for selector_id in ("reverse_selector_one", "reverse_selector_two")
        ]
        package = self.build_with_contexts(
            [self.context("reverse_context", ["drosophila_suzukii"], selectors)]
        )
        package["evidence_records"][0]["selector_ids"] = ["reverse_selector_one"]

        with self.assertRaisesRegex(ValueError, "selector_ids.*receipts"):
            validate_context_package(package, verify_hash=False)

    def test_validator_rejects_invalid_parent_unit_and_snapshot_basis(self):
        package = self.build_linked_fulltext_package()

        mutations = [
            (
                "parent_record_id",
                lambda item: item["eligibility"]["taxon"]["basis"][0].pop(
                    "parent_record_id"
                ),
            ),
            (
                "fulltext_unit_id",
                lambda item: item["eligibility"]["context"]["basis"][0].pop(
                    "fulltext_unit_id"
                ),
            ),
            (
                "evidence_sha256",
                lambda item: item["eligibility"]["context"]["basis"][0].__setitem__(
                    "evidence_snapshot", "Contact was rewritten after export."
                ),
            ),
            (
                "retained_path",
                lambda item: item["eligibility"]["context"]["basis"][0].__setitem__(
                    "retained_path", "payload.evidence_text"
                ),
            ),
        ]
        for expected_error, mutate in mutations:
            with self.subTest(expected_error=expected_error):
                invalid = json.loads(json.dumps(package))
                mutate(invalid["evidence_records"][0])
                with self.assertRaisesRegex(ValueError, expected_error):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_rejects_gap_that_does_not_match_selector_receipt(self):
        self.index.upsert_records(
            [
                record(
                    "gap:validator",
                    source="validator_gap_evidence",
                    species="Drosophila suzukii",
                    text="Generated avoidance candidate.",
                    payload={
                        "title": "Tribolium castaneum avoidance",
                        "abstract": "Avoidance was measured.",
                    },
                )
            ]
        )
        selector = self.selector(
            "validator_gap_selector",
            "drosophila_suzukii",
            "validator_gap_evidence",
            query_any=["avoidance"],
            context_required_term_groups=[["avoidance"]],
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )
        package = self.build_with_contexts(
            [self.context("validator_gap_context", ["drosophila_suzukii"], [selector])]
        )
        package["gaps"][0]["candidate_count"] += 1

        with self.assertRaisesRegex(ValueError, "gap receipt"):
            validate_context_package(package, verify_hash=False)

    def test_validator_rejects_hash_mismatch(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["text"] = "changed after hashing"

        with self.assertRaisesRegex(ValueError, "content_sha256"):
            validate_context_package(package)


if __name__ == "__main__":
    unittest.main()
