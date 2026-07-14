import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from askinsects import context_package as context_package_module
from askinsects.context_package import (
    DEFAULT_CONTEXT_CONFIG,
    DEFAULT_PROGRAM_CONFIG,
    PUBLIC_CONTEXT_CONFIG_URL,
    PUBLIC_PROGRAM_CONFIG_URL,
    build_context_package,
    canonical_package_hash,
    load_context_config,
    load_published_context_package,
    validate_context_package,
)
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit


CONTEXT_REQUIRED_TERM_GROUPS = {
    "treated_area_contact_avoidance": [
        ["avoidance", "repellency", "repellent", "occupancy", "preference", "deterrence"],
        ["contact", "surface", "inside zone", "inside-zone", "treated area", "treated region"],
    ],
    "treated_area_noncontact_avoidance": [
        ["avoidance", "repellency", "repellent", "occupancy", "preference", "deterrence"],
        [
            "non-contact",
            "noncontact",
            "airborne",
            "vapor",
            "vapour",
            "plume",
            "spatial exposure",
            "without contact",
        ],
    ],
    "bounded_choice_orientation": [
        ["choice", "preference", "avoidance", "selection", "occupancy"],
        [
            "orientation",
            "Y-tube",
            "Y tube",
            "olfactometer",
            "bounded arena",
        ],
    ],
    "oviposition_choice": [
        ["oviposition", "egg laying", "egg-laying", "egg deposition", "eggs laid"],
        [
            "choice",
            "preference",
            "avoidance",
            "deterrence",
            "selection",
            "distribution",
            "treated versus control",
            "treated vs control",
        ],
    ],
    "human_landing_response": [
        [
            "landing",
            "probing",
            "blood feeding",
            "blood-feeding",
            "human host",
            "human-host",
        ],
        [
            "avoidance",
            "repellency",
            "repellent",
            "reduction",
            "inhibition",
            "protection",
            "response",
            "preference",
            "deterrence",
        ],
    ],
    "spatial_behavior": [
        [
            "avoidance",
            "repellency",
            "repellent",
            "movement",
            "trajectory",
            "occupancy",
            "displacement",
            "orientation",
            "host seeking",
            "host-seeking",
        ],
        [
            "spatial",
            "airborne",
            "plume",
            "non-contact",
            "noncontact",
            "vapor",
            "vapour",
            "without contact",
        ],
    ],
    "post_exposure_behavior": [
        [
            "post exposure",
            "post-exposure",
            "after exposure",
            "after-exposure",
            "following exposure",
        ],
        [
            "recovery",
            "knockdown",
            "locomotion",
            "locomotor",
            "survival",
            "impairment",
            "mortality",
            "movement",
        ],
    ],
}
TEST_CONTEXT_CONFIG_URL = (
    "https://raw.githubusercontent.com/example/ask-insects/"
    f"{'1' * 40}/tests/context-config.json"
)


def record(
    record_id: str,
    *,
    source: str,
    species: str | None,
    text: str,
    title: str | None = None,
    payload: dict | None = None,
    locator: str | None = None,
    source_url: str | None = None,
    license: str | None = "CC-BY-4.0",
    include_source_url: bool = True,
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
            license=license,
            source_url=(
                source_url or f"https://example.org/records/{record_id}"
                if include_source_url
                else None
            ),
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
        self.assertEqual(config["package_version"], "2026-07-14.6")
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
                        "ledger_path": (
                            "/Users/josh/Documents/ask-insects/"
                            "config/insect-intelligence-programs.json"
                        ),
                        "consumer_id": "downstream-consumer",
                        "private_locator": "https://example.org/private-config",
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
                        "raw_artifact_path": "/Users/josh/private/source.json",
                        "cached_locator": "file:///tmp/x",
                        "cloud_copy": "gs://private-bucket/x",
                        "original_provenance": {
                            "auth_token": "must-not-serialize",
                            "locator": "/home/josh/ask-insects/private/source.json",
                        },
                    },
                    locator="/home/josh/ask-insects/source.json#row/100",
                    source_url="10.1234/swd.1",
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
                    "package_version": "2026-07-14.3",
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
                                    "context_required_term_groups": CONTEXT_REQUIRED_TERM_GROUPS[
                                        "treated_area_contact_avoidance"
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

    def _sync_status_record_count(self) -> None:
        with self.index.connect() as conn:
            record_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        status_path = self.artifact_dir / "source_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("record_count") != record_count:
            status["record_count"] = record_count
            status_path.write_text(json.dumps(status), encoding="utf-8")

    def build(self, generated_at: str, *, sync_status: bool = True):
        if sync_status:
            self._sync_status_record_count()
        return build_context_package(
            artifact_dir=self.artifact_dir,
            config_path=self.config_path,
            context_config_source_url=TEST_CONTEXT_CONFIG_URL,
            context_config_sha256=hashlib.sha256(self.config_path.read_bytes()).hexdigest(),
            generated_at=generated_at,
        )

    def build_with_contexts(self, contexts: list[dict], generated_at: str = "2026-07-14T01:00:00Z"):
        self._sync_status_record_count()
        original = self.config_path.read_bytes()
        config = json.loads(original)
        config["contexts"] = contexts
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        try:
            return self.build(generated_at, sync_status=False)
        finally:
            self.config_path.write_bytes(original)

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
                        context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                            "treated_area_contact_avoidance"
                        ],
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
                        context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                            "oviposition_choice"
                        ],
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
                        source_url="https://example.org/fulltext/unit-validator-swd",
                    ),
                )
            ]
        )
        selector = self.selector(
            "derived_validator",
            "drosophila_suzukii",
            "derived_validator_evidence",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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

        direct_openalex = [
            selector
            for selector in selectors
            if selector["source"] in {
                "drosophila_suzukii_core",
                "aedes_literature_openalex",
            }
        ]
        self.assertTrue(direct_openalex)
        for selector in direct_openalex:
            self.assertEqual(
                selector["taxon_field_paths"],
                ["payload.raw_openalex_work.display_name"],
            )
            self.assertEqual(
                selector["context_field_paths"],
                [
                    "payload.raw_openalex_work.display_name",
                    "payload.raw_openalex_work.abstract_inverted_index",
                ],
            )
            self.assertNotIn("parent_record", selector)
            self.assertNotIn("fulltext_context", selector)

        flight = next(selector for selector in selectors if selector["id"] == "choice_swd_flight")
        self.assertEqual(
            flight["record_requirements"],
            {"payload.atom_type": "umn_flight_assay_dataset"},
        )

    def test_default_config_requires_context_defining_terms_not_generic_repellent(self):
        for context in load_context_config()["contexts"]:
            for selector in context["selectors"]:
                with self.subTest(context=context["id"], selector=selector["id"]):
                    self.assertEqual(
                        selector["context_required_term_groups"],
                        CONTEXT_REQUIRED_TERM_GROUPS[context["id"]],
                    )

    def test_loader_requires_two_disjoint_context_term_groups(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))

        invalid_groups = (
            ([['avoidance']], "at least two"),
            ([['avoidance', 'repellent'], [' Avoidance ', 'contact']], "disjoint"),
        )
        for index, (groups, expected_error) in enumerate(invalid_groups):
            with self.subTest(groups=groups):
                invalid = json.loads(json.dumps(config))
                invalid["contexts"][0]["selectors"][0][
                    "context_required_term_groups"
                ] = groups
                path = self.root / f"invalid-context-groups-{index}.json"
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected_error):
                    load_context_config(path)

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
        selector["context_field_paths"] = []
        selector["context_field_prerequisites"] = {}

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

        invalid = json.loads(json.dumps(config))
        invalid["contexts"][0]["selectors"][0]["context_field_paths"] = [
            "payload.fields.table_row"
        ]
        path = self.root / "invalid-fulltext-current-context.json"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fulltext_context.*context_field_paths"):
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
                ("treated_area_contact_avoidance", "contact_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_core", ("repellent", "avoidance", "deterrence"), 4, False),
                ("treated_area_contact_avoidance", "contact_swd_olfaction", "drosophila_suzukii", "drosophila_suzukii_olfaction_literature", ("olfaction", "odor", "host volatile"), 3, False),
                ("treated_area_contact_avoidance", "contact_aedes_behavior", "aedes_aegypti", "aedes_literature_openalex", ("repellent", "avoidance", "deterrence"), 4, False),
                ("treated_area_contact_avoidance", "contact_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("repellent", "olfaction", "host seeking"), 3, False),
                ("treated_area_noncontact_avoidance", "noncontact_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_core", ("spatial repellent", "non-contact", "noncontact", "airborne", "vapor", "vapour"), 4, False),
                ("treated_area_noncontact_avoidance", "noncontact_swd_olfaction", "drosophila_suzukii", "drosophila_suzukii_olfaction_literature", ("olfaction", "odor", "host volatile"), 3, False),
                ("treated_area_noncontact_avoidance", "noncontact_aedes_behavior", "aedes_aegypti", "aedes_literature_openalex", ("spatial repellent", "non-contact", "noncontact", "airborne", "vapor", "vapour"), 4, False),
                ("treated_area_noncontact_avoidance", "noncontact_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("repellent", "olfaction", "host seeking"), 3, False),
                ("bounded_choice_orientation", "choice_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_core", ("olfactometer", "Y-tube", "Y tube", "choice", "preference"), 4, False),
                ("bounded_choice_orientation", "choice_swd_flight", "drosophila_suzukii", "drosophila_suzukii_umn_flight_assay_rows", ("flight", "movement", "distance"), 3, False),
                ("bounded_choice_orientation", "choice_aedes_behavior", "aedes_aegypti", "aedes_literature_openalex", ("olfactometer", "Y-tube", "Y tube", "choice", "preference"), 4, False),
                ("bounded_choice_orientation", "choice_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("olfaction", "orientation", "host seeking"), 3, False),
                ("oviposition_choice", "oviposition_swd_behavior", "drosophila_suzukii", "drosophila_suzukii_core", ("oviposition", "egg laying", "egg-laying"), 5, False),
                ("oviposition_choice", "oviposition_swd_olfaction", "drosophila_suzukii", "drosophila_suzukii_olfaction_literature", ("oviposition", "fruit odor", "host volatile"), 3, False),
                ("oviposition_choice", "oviposition_dbm_direct", "plutella_xylostella", "plutella_xylostella_oviposition_literature", ("oviposition", "egg laying", "host choice"), 5, False),
                ("human_landing_response", "landing_aedes_host_seeking", "aedes_aegypti", "aedes_olfaction_literature", ("host seeking", "human odor", "landing", "blood feeding"), 6, False),
                ("human_landing_response", "landing_aedes_behavior", "aedes_aegypti", "aedes_literature_openalex", ("landing", "probing", "blood feeding", "human host"), 5, False),
                ("spatial_behavior", "spatial_aedes_olfaction", "aedes_aegypti", "aedes_olfaction_literature", ("spatial repellent", "olfaction", "odor plume", "host seeking"), 6, False),
                ("spatial_behavior", "spatial_aedes_literature", "aedes_aegypti", "aedes_literature_openalex", ("spatial repellent", "airborne", "odor plume", "non-contact", "noncontact"), 4, False),
                ("post_exposure_behavior", "post_aedes_behavior", "aedes_aegypti", "aedes_literature_openalex", ("post exposure", "post-exposure", "after exposure", "knockdown", "recovery"), 5, False),
            ],
        )

    def test_default_config_uses_original_public_papers_for_openalex_evidence(self):
        config = load_context_config()
        selectors = [
            selector
            for context in config["contexts"]
            for selector in context["selectors"]
        ]
        direct_sources = {
            "drosophila_suzukii_core",
            "aedes_literature_openalex",
        }
        openalex_title_path = [
            "payload.raw_openalex_work.display_name",
        ]
        openalex_context_paths = [
            *openalex_title_path,
            "payload.raw_openalex_work.abstract_inverted_index",
        ]

        self.assertFalse(
            any(selector["source"].endswith("_extracted_facts") for selector in selectors)
        )
        for selector in selectors:
            if selector["source"] in direct_sources:
                self.assertEqual(selector["taxon_field_paths"], openalex_title_path)
                self.assertEqual(selector["context_field_paths"], openalex_context_paths)
                self.assertNotIn("parent_record", selector)
                self.assertNotIn("fulltext_context", selector)

    def test_explicit_public_program_config_replaces_stale_index_records(self):
        self._sync_status_record_count()
        package = build_context_package(
            artifact_dir=self.artifact_dir,
            config_path=self.config_path,
            context_config_source_url=TEST_CONTEXT_CONFIG_URL,
            context_config_sha256=hashlib.sha256(self.config_path.read_bytes()).hexdigest(),
            program_config_path=(
                Path(__file__).resolve().parents[1]
                / "config"
                / "insect-intelligence-programs.json"
            ),
            generated_at="2026-07-14T01:00:00Z",
        )

        serialized = json.dumps(package, sort_keys=True)
        portfolio = next(
            record
            for record in package["program_records"]
            if record["record_id"] == "insect_intelligence_programs:portfolio"
        )
        self.assertEqual(
            portfolio["payload"]["objective"],
            "Deeply understand insects and accelerate effective, safe repellents that "
            "protect people and crops without killing insects.",
        )
        self.assertNotIn("monarch", serialized.casefold())
        program_source = package["configuration_sources"]["program_config"]
        self.assertEqual(
            program_source["sha256"],
            hashlib.sha256(
                (
                    Path(__file__).resolve().parents[1]
                    / "config"
                    / "insect-intelligence-programs.json"
                ).read_bytes()
            ).hexdigest(),
        )
        self.assertTrue(
            all(
                record["provenance"]["locator"].startswith(
                    f"{program_source['source_url']}#jsonpath=$"
                )
                for record in package["program_records"]
            )
        )

    def test_builder_rejects_even_one_byte_of_config_drift(self):
        self._sync_status_record_count()
        expected_sha256 = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        self.config_path.write_bytes(self.config_path.read_bytes() + b"\n")

        with self.assertRaisesRegex(ValueError, "context config SHA-256"):
            build_context_package(
                artifact_dir=self.artifact_dir,
                config_path=self.config_path,
                context_config_source_url=TEST_CONTEXT_CONFIG_URL,
                context_config_sha256=expected_sha256,
                generated_at="2026-07-14T01:00:00Z",
            )

    def test_published_package_loader_checks_raw_hash_and_contract(self):
        package = self.build("2026-07-14T01:00:00Z")
        raw = (json.dumps(package, sort_keys=True) + "\n").encode("utf-8")
        path = self.root / "published-package.json"
        path.write_bytes(raw)

        loaded = load_published_context_package(
            path,
            expected_artifact_sha256=hashlib.sha256(raw).hexdigest(),
        )

        self.assertEqual(loaded, package)

    def test_published_package_loader_rejects_duplicate_keys(self):
        raw = b'{"ok":true,"ok":true}'
        path = self.root / "duplicate-package.json"
        path.write_bytes(raw)

        with self.assertRaisesRegex(ValueError, "duplicate JSON key: ok"):
            load_published_context_package(
                path,
                expected_artifact_sha256=hashlib.sha256(raw).hexdigest(),
            )

    def test_published_package_loader_rejects_raw_hash_mismatch(self):
        package = self.build("2026-07-14T01:00:00Z")
        path = self.root / "mismatched-package.json"
        path.write_text(json.dumps(package), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact hash does not match"):
            load_published_context_package(
                path,
                expected_artifact_sha256="0" * 64,
            )

    def test_default_published_package_is_the_exact_public_release(self):
        package = load_published_context_package()
        serialized = json.dumps(package, sort_keys=True).casefold()

        self.assertEqual(package["schema_version"], "ask-insects-evidence-package.v2")
        self.assertEqual(package["package_version"], "2026-07-14.5")
        self.assertEqual(len(package["evidence_records"]), 36)
        self.assertEqual(len(package["gaps"]), 10)
        self.assertNotIn("monarch", serialized)
        self.assertNotIn("/users/", serialized)
        self.assertNotIn("/home/", serialized)

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
                    "public:swd:1",
                    source="public_swd_behavior",
                    species="Drosophila suzukii",
                    text="Generated text repeats every search term.",
                    payload={
                        "title": "Drosophila suzukii contact avoidance assay",
                        "abstract": "Direct contact avoidance was measured.",
                    },
                    locator="/home/josh/ask-insects/source.json#row/100",
                    source_url="10.1234/swd.1",
                ),
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
        self.assertEqual(receipt["candidate_count"], 5)
        self.assertEqual(receipt["rejection_counts"], {"taxon_not_directly_confirmed": 3})

    def test_single_concept_evidence_cannot_qualify_any_context(self):
        context_cases = [
            (
                "treated_area_contact_avoidance",
                "Contact avoidance on a treated surface was measured.",
                ["Repellent activity was measured.", "Surface chemistry was characterized."],
            ),
            (
                "treated_area_noncontact_avoidance",
                "Airborne vapor plume avoidance was measured.",
                ["Repellent activity was measured.", "Airborne chemistry was characterized."],
            ),
            (
                "bounded_choice_orientation",
                "Orientation choice in a Y-tube olfactometer was measured.",
                ["Choice was recorded.", "Y-tube geometry was characterized."],
            ),
            (
                "oviposition_choice",
                "Oviposition and egg-laying choice were measured.",
                ["Oviposition was measured.", "Choice was recorded."],
            ),
            (
                "human_landing_response",
                "Landing avoidance on a human host was measured.",
                ["Landing was measured.", "Avoidance was measured."],
            ),
            (
                "spatial_behavior",
                "Spatial airborne plume avoidance was measured.",
                ["Spatial conditions were characterized.", "Avoidance was measured."],
            ),
            (
                "post_exposure_behavior",
                "Recovery and knockdown were measured after-exposure.",
                ["Recovery was measured.", "After-exposure chemistry was characterized."],
            ),
        ]
        records = []
        contexts = []
        for context_id, direct_text, false_positive_texts in context_cases:
            source = f"context_specific_{context_id}"
            records.append(
                record(
                    f"direct:{context_id}",
                    source=source,
                    species="Drosophila suzukii",
                    text="Generated repellent candidate.",
                    payload={
                        "title": "Drosophila suzukii repellent study",
                        "abstract": direct_text,
                    },
                )
            )
            records.extend(
                record(
                    f"false:{context_id}:{index}",
                    source=source,
                    species="Drosophila suzukii",
                    text="Generated repellent candidate.",
                    payload={
                        "title": "Drosophila suzukii repellent study",
                        "abstract": false_positive_text,
                    },
                )
                for index, false_positive_text in enumerate(false_positive_texts)
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
                            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                                context_id
                            ],
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
            self.assertEqual(receipt["candidate_count"], 3)
            self.assertEqual(receipt["selected_count"], 1)
            self.assertEqual(
                receipt["rejection_counts"],
                {"context_not_directly_confirmed": 2},
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
                        context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                            "oviposition_choice"
                        ],
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
            self.assertEqual(eligibility["ruleset_version"], "direct-semantic-evidence.v2")
            self.assertEqual(eligibility["taxon"]["status"], "direct_focal_taxon")
            self.assertEqual(eligibility["context"]["status"], "direct_context")
            for basis in [*eligibility["taxon"]["basis"], *eligibility["context"]["basis"]]:
                self.assertTrue({"field_path", "matched_term", "excerpt"}.issubset(basis))
            if item["species_id"] == "aedes_aegypti":
                self.assertNotIn(
                    eligibility["taxon"]["basis"][0]["matched_term"],
                    {"Aedes", "mosquito"},
                )

    def test_parasitoid_choice_is_not_published_as_swd_choice(self):
        record_id = "swd:openalex_literature:openalex:W4399796030"
        self.index.upsert_records(
            [
                record(
                    record_id,
                    source="parasitoid_review_case",
                    species="Drosophila suzukii",
                    title=(
                        "Foraging behavior of Ganaspis brasiliensis in response to "
                        "temporal dynamics of volatile release by the fruit-Drosophila "
                        "suzukii complex"
                    ),
                    text=(
                        "The results showed a choice made by Ganaspis brasiliensis females "
                        "in a two-choice olfactometer using Drosophila suzukii-infested fruit."
                    ),
                    payload={
                        "title": (
                            "Foraging behavior of Ganaspis brasiliensis in response to "
                            "temporal dynamics of volatile release by the fruit-Drosophila "
                            "suzukii complex"
                        ),
                        "abstract": (
                            "The results showed a choice made by Ganaspis brasiliensis females "
                            "in a two-choice olfactometer using Drosophila suzukii-infested fruit."
                        ),
                    },
                )
            ]
        )
        context = self.context(
            "bounded_choice_orientation",
            ["drosophila_suzukii"],
            [
                self.selector(
                    "choice_swd_subject_role",
                    "drosophila_suzukii",
                    "parasitoid_review_case",
                    query_any=["choice", "olfactometer"],
                    context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                        "bounded_choice_orientation"
                    ],
                    taxon_field_paths=["payload.title"],
                    context_field_paths=["payload.abstract"],
                )
            ],
        )

        package = self.build_with_contexts([context])

        self.assertNotIn(
            record_id,
            {item["record_id"] for item in package["evidence_records"]},
        )
        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 1)
        self.assertEqual(receipt["eligible_count"], 0)
        self.assertEqual(
            receipt["rejection_counts"],
            {"taxon_role_not_directly_confirmed": 1},
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
                        source_url="https://example.org/fulltext/unit-1",
                    ),
                )
            ]
        )
        selector = self.selector(
            "derived_swd",
            "drosophila_suzukii",
            "derived_direct_evidence",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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
            taxon_basis["provenance"]["index_record_id"],
            "parent:swd:paper",
        )
        self.assertEqual(
            taxon_basis["retained_path"],
            "payload.raw_openalex_work.abstract_inverted_index",
        )
        self.assertEqual(
            {basis["field_path"] for basis in item["eligibility"]["context"]["basis"]},
            {"literature_fulltext_units.text"},
        )
        context_basis = item["eligibility"]["context"]["basis"][0]
        self.assertEqual(context_basis["fulltext_unit_id"], "unit:1")
        self.assertEqual(context_basis["parent_record_id"], "parent:swd:paper")
        self.assertEqual(context_basis["retained_source"], "public_parent_literature")
        self.assertEqual(context_basis["provenance"]["index_record_id"], "unit:1")
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
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:missing-parent",
                    record_id="parent:does-not-exist",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Contact avoidance was measured on a treated surface.",
                    url=None,
                    license=None,
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:missing-parent",
                        retrieved_at="2026-07-13T00:00:00Z",
                        source_url="https://example.org/fulltext/unit-missing-parent",
                    ),
                )
            ]
        )
        selector = self.selector(
            "missing_parent",
            "drosophila_suzukii",
            "derived_missing_parent",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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
                        source_url="https://example.org/fulltext/unit-top-level-only",
                    ),
                )
            ]
        )
        selector = self.selector(
            "top_level_parent_title",
            "drosophila_suzukii",
            "derived_top_level_parent_title",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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
                            "display_name": "Drosophila suzukii contact avoidance behavior",
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
                        source_url="https://example.org/fulltext/unit-belongs-elsewhere",
                    ),
                )
            ]
        )
        selector = self.selector(
            "invalid_fulltext_link",
            "drosophila_suzukii",
            "derived_invalid_fulltext_link",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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

    def test_fulltext_selector_requires_one_id_pair_and_uses_only_unit_text(self):
        self.index.upsert_records(
            [
                record(
                    "parent:strict-link:swd",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Drosophila suzukii contact avoidance behavior",
                            "abstract_inverted_index": {},
                        }
                    },
                ),
                *[
                    record(
                        record_id,
                        source="derived_strict_fulltext_link",
                        species="Drosophila suzukii",
                        text="Generated contact avoidance candidate.",
                        payload={
                            "source_record_id": source_record_id,
                            "fulltext_unit_id": unit_id,
                            "fields": {
                                "table_row": "Contact avoidance on a treated surface was measured."
                            },
                            "evidence_text": "Contact avoidance was generated here.",
                        },
                    )
                    for record_id, source_record_id, unit_id in (
                        (
                            "derived:missing-unit-id",
                            "parent:strict-link:swd",
                            None,
                        ),
                        (
                            "derived:missing-parent-id",
                            None,
                            "unit:strict-link:generic",
                        ),
                        (
                            "derived:multiple-unit-ids",
                            "parent:strict-link:swd",
                            ["unit:strict-link:generic", "unit:strict-link:second"],
                        ),
                        (
                            "derived:multiple-parent-ids",
                            ["parent:strict-link:swd", "parent:other"],
                            "unit:strict-link:generic",
                        ),
                        (
                            "derived:generated-row-cannot-rescue",
                            "parent:strict-link:swd",
                            "unit:strict-link:generic",
                        ),
                    )
                ],
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id=unit_id,
                    record_id="parent:strict-link:swd",
                    source="public_parent_literature",
                    unit_index=index,
                    text="Surface chemistry was characterized.",
                    url=None,
                    license=None,
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator=f"literature_fulltext_units#{unit_id}",
                        retrieved_at="2026-07-13T00:00:00Z",
                        source_url=f"https://example.org/fulltext/{unit_id}",
                    ),
                )
                for index, unit_id in enumerate(
                    ("unit:strict-link:generic", "unit:strict-link:second")
                )
            ]
        )
        selector = self.selector(
            "strict_fulltext_link",
            "drosophila_suzukii",
            "derived_strict_fulltext_link",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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
            [self.context("strict_fulltext_context", ["drosophila_suzukii"], [selector])]
        )

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(package["selector_results"][0]["candidate_count"], 4)
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {
                "context_not_directly_confirmed": 1,
                "fulltext_unit_link_invalid": 3,
            },
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
                        "fulltext_unit_id": "unit:no-parent-fields",
                    },
                ),
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:no-parent-fields",
                    record_id="parent:no-raw-fields",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Contact avoidance was measured on a treated surface.",
                    url=None,
                    license=None,
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:no-parent-fields",
                        retrieved_at="2026-07-13T00:00:00Z",
                        source_url="https://example.org/fulltext/unit-no-parent-fields",
                    ),
                )
            ]
        )
        selector = self.selector(
            "missing_trusted_field",
            "drosophila_suzukii",
            "derived_missing_trusted_field",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
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
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "bounded_choice_orientation"
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
                        context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                            "bounded_choice_orientation"
                        ],
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
                        context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                            "spatial_behavior"
                        ],
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
                        context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                            "oviposition_choice"
                        ],
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
                "hard_coded_neurobiology": {},
                "unmapped_dbm": {},
            },
        )
        self.assertEqual(
            {
                result["selector_id"]: result["candidate_count"]
                for result in package["selector_results"]
            },
            {
                "flight_without_parent": 1,
                "hard_coded_neurobiology": 0,
                "unmapped_dbm": 0,
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
            query_any=["assay"],
            context_required_term_groups=[["avoidance"], ["measured"]],
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
            context_required_term_groups=[["avoidance"], ["measured"]],
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

    def test_selector_rejects_missing_or_nonpublic_provenance_and_continues(self):
        self.index.upsert_records(
            [
                record(
                    "provenance:missing",
                    source="public_provenance_candidates",
                    species="Drosophila suzukii",
                    text="Contact avoidance candidate with missing public provenance.",
                    payload={
                        "title": "Drosophila suzukii contact behavior",
                        "abstract": "Contact avoidance was measured on a treated surface.",
                    },
                    include_source_url=False,
                ),
                record(
                    "provenance:localhost",
                    source="public_provenance_candidates",
                    species="Drosophila suzukii",
                    text="Contact avoidance candidate with nonpublic provenance.",
                    payload={
                        "title": "Drosophila suzukii contact behavior",
                        "abstract": "Contact avoidance was measured on a treated surface.",
                    },
                    source_url="https://localhost/private/source.json",
                ),
                record(
                    "provenance:public",
                    source="public_provenance_candidates",
                    species="Drosophila suzukii",
                    text="Contact avoidance candidate with public provenance.",
                    payload={
                        "title": "Drosophila suzukii contact behavior",
                        "abstract": "Contact avoidance was measured on a treated surface.",
                    },
                    source_url="https://journals.plos.org/plosone/article"
                    "?id=10.1371/journal.pone.0000001&type=printable",
                ),
            ]
        )
        selector = self.selector(
            "public_provenance_selector",
            "drosophila_suzukii",
            "public_provenance_candidates",
            query_any=["contact", "avoidance"],
            context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                "treated_area_contact_avoidance"
            ],
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        package = self.build_with_contexts(
            [self.context("public_provenance_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 3)
        self.assertEqual(receipt["eligible_count"], 1)
        self.assertEqual(receipt["selected_record_ids"], ["provenance:public"])
        self.assertEqual(receipt["rejection_counts"], {"public_provenance_missing": 2})
        self.assertEqual(
            package["evidence_records"][0]["provenance"]["locator"],
            "https://journals.plos.org/plosone/article"
            "?id=10.1371/journal.pone.0000001&type=printable",
        )

    def test_package_hash_is_stable_across_generation_times(self):
        first = self.build("2026-07-14T01:00:00Z")
        second = self.build("2026-07-14T02:00:00Z")

        self.assertNotEqual(first["generated_at"], second["generated_at"])
        self.assertEqual(first["content_sha256"], second["content_sha256"])

    def test_package_hash_covers_scientific_receipt_and_provenance_fields(self):
        package = self.build("2026-07-14T01:00:00Z")
        original_hash = canonical_package_hash(package)

        ignored = json.loads(json.dumps(package))
        ignored["generated_at"] = "2099-01-01T00:00:00Z"
        ignored["content_sha256"] = "0" * 64
        self.assertEqual(canonical_package_hash(ignored), original_hash)

        mutations = [
            lambda value: value["evidence_records"][0]["payload"].__setitem__(
                "abstract", "Changed scientific evidence."
            ),
            lambda value: value["evidence_records"][0]["provenance"].__setitem__(
                "locator", "https://example.org/changed#row/100"
            ),
            lambda value: value["selector_results"][0].__setitem__(
                "candidate_count", value["selector_results"][0]["candidate_count"] + 1
            ),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = json.loads(json.dumps(package))
                mutate(changed)
                self.assertNotEqual(canonical_package_hash(changed), original_hash)

    def test_package_declares_producer_and_downstream_validation_boundary(self):
        package = self.build("2026-07-14T01:00:00Z")

        self.assertEqual(
            package["validation_contract"],
            {
                "producer_linkage": (
                    "status_record_count_selected_rows_and_links_verified_in_read_only_source_index"
                ),
                "downstream_validation": "exported_snapshot_internal_consistency_only",
                "snapshot_authentication": "publisher_pinned_content_sha256",
            },
        )
        invalid = json.loads(json.dumps(package))
        invalid["validation_contract"]["producer_linkage"] = (
            "claimed_without_source_index"
        )
        with self.assertRaisesRegex(ValueError, "validation_contract"):
            validate_context_package(invalid, verify_hash=False)

    def test_every_exported_record_has_exact_provenance(self):
        package = self.build("2026-07-14T01:00:00Z")

        for item in [*package["program_records"], *package["evidence_records"]]:
            self.assertEqual(
                set(item["provenance"]),
                {"source_id", "locator", "index_record_id", "retrieved_at", "license"},
            )
            self.assertEqual(item["provenance"]["index_record_id"], item["record_id"])
            self.assertTrue(item["provenance"]["locator"].startswith("https://"))
        for context in package["contexts"]:
            self.assertEqual(
                set(context["provenance"]),
                {"source_id", "locator", "index_record_id", "retrieved_at", "license"},
            )
        validate_context_package(package)

    def test_builder_exports_exact_public_record_shapes_and_minimal_payloads(self):
        package = self.build("2026-07-14T01:00:00Z")

        self.assertEqual(
            set(package),
            {
                "ok",
                "schema_version",
                "package_version",
                "generated_at",
                "objective",
                "validation_contract",
                "configuration_sources",
                "knowledge_domains",
                "upstream_snapshot",
                "contexts",
                "program_records",
                "evidence_records",
                "selector_results",
                "gaps",
                "content_sha256",
            },
        )
        expected_program_fields = {
            "record_id",
            "lane",
            "source",
            "title",
            "text",
            "species",
            "payload",
            "provenance",
        }
        expected_evidence_fields = expected_program_fields | {
            "species_id",
            "context_ids",
            "selector_ids",
            "eligibility",
        }
        self.assertTrue(package["program_records"])
        self.assertTrue(package["evidence_records"])
        for item in package["program_records"]:
            self.assertEqual(set(item), expected_program_fields)
        for item in package["evidence_records"]:
            self.assertEqual(set(item), expected_evidence_fields)

        evidence = package["evidence_records"][0]
        self.assertEqual(
            evidence["payload"],
            {
                "title": "Drosophila suzukii contact avoidance assay",
                "abstract": "Direct contact avoidance and repellent behavior was measured.",
            },
        )
        self.assertEqual(
            evidence["provenance"]["locator"],
            "https://doi.org/10.1234/swd.1#row/100",
        )
        self.assertEqual(
            package["program_records"][0]["provenance"]["locator"],
            "https://example.org/records/program:domain:swd:behavior",
        )
        self.assertNotIn("ledger_path", package["program_records"][0]["payload"])

        serialized = json.dumps(package, sort_keys=True)
        for unsafe in (
            "/home/josh/",
            "/Users/josh/",
            "file:///tmp/x",
            "gs://private-bucket/x",
            "must-not-serialize",
            '"consumer_id"',
            '"private_locator"',
        ):
            with self.subTest(unsafe=unsafe):
                self.assertNotIn(unsafe, serialized)

    def test_public_provenance_normalizes_doi_and_preserves_only_safe_fragments(self):
        public_provenance = context_package_module._public_provenance
        base_record = {
            "record_id": "public:record:1",
            "provenance": {
                "source_id": "public_source",
                "source_url": "https://example.org/public/data.json",
                "locator": "/home/josh/private/data.json#row/100",
                "retrieved_at": "2026-07-13T00:00:00Z",
                "license": "CC-BY-4.0",
            },
        }

        expected_fragments = {
            "row/100",
            "page=4",
            "cell/B12",
            "sheet=assays",
            "result/3",
            "works/W123",
            "jsonpath=$.items[0]",
        }
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                candidate = json.loads(json.dumps(base_record))
                candidate["provenance"]["locator"] = f"/home/josh/private/data#{fragment}"
                normalized = public_provenance(candidate)
                self.assertEqual(
                    normalized["locator"],
                    f"https://example.org/public/data.json#{fragment}",
                )

        for fragment in (
            "token=secret",
            "row/1?token=secret",
            "artifact=/Users/josh/x",
            "file:///tmp/x",
        ):
            with self.subTest(fragment=fragment):
                candidate = json.loads(json.dumps(base_record))
                candidate["provenance"]["locator"] = f"/home/josh/private/data#{fragment}"
                normalized = public_provenance(candidate)
                self.assertEqual(normalized["locator"], "https://example.org/public/data.json")

        doi_record = json.loads(json.dumps(base_record))
        doi_record["provenance"]["source_url"] = "10.5555/example.doi"
        normalized = public_provenance(doi_record)
        self.assertEqual(normalized["locator"], "https://doi.org/10.5555/example.doi#row/100")

    def test_public_provenance_rejects_nonpublic_or_credentialed_source_urls(self):
        invalid_urls = (
            "file:///tmp/x",
            "gs://private-bucket/x",
            "s3://private-bucket/x",
            "ssh://example.org/x",
            "private://consumer/x",
            "http://example.org/x",
            "https://user:password@example.org/x",
            "https://example.org/x?access_token=secret",
            "https://example.org/x?password=secret",
            "https://example.org/x?X-Amz-Signature=secret",
            "https://localhost/x",
            "https://127.0.0.1/x",
            "https://[::1]/x",
            "https://169.254.169.254/x",
            "https://10.0.0.1/x",
            "https://172.16.0.1/x",
            "https://192.168.1.1/x",
            "https://[fe80::1]/x",
            "https://[fd00::1]/x",
            "https://source.local/x",
        )
        for source_url in invalid_urls:
            with self.subTest(source_url=source_url):
                candidate = {
                    "record_id": "public:record:1",
                    "provenance": {
                        "source_id": "public_source",
                        "source_url": source_url,
                        "locator": "records#row/1",
                        "retrieved_at": "2026-07-13T00:00:00Z",
                        "license": "CC-BY-4.0",
                    },
                }
                with self.assertRaisesRegex(ValueError, "public HTTPS source_url"):
                    context_package_module._public_provenance(candidate)

    def test_validator_rejects_unknown_package_record_and_payload_fields(self):
        package = self.build("2026-07-14T01:00:00Z")
        mutations = [
            (
                "top-level",
                lambda value: value.__setitem__("unexpected", "public-looking"),
            ),
            (
                "record",
                lambda value: value["evidence_records"][0].__setitem__(
                    "unexpected", "public-looking"
                ),
            ),
            (
                "payload",
                lambda value: value["evidence_records"][0]["payload"].__setitem__(
                    "untrusted_summary", "public-looking"
                ),
            ),
            (
                "provenance",
                lambda value: value["evidence_records"][0]["provenance"].__setitem__(
                    "source_url", "https://example.org/not-part-of-export-shape"
                ),
            ),
        ]
        for expected_error, mutate in mutations:
            with self.subTest(expected_error=expected_error):
                invalid = json.loads(json.dumps(package))
                mutate(invalid)
                with self.assertRaisesRegex(ValueError, expected_error):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_rejects_unsafe_paths_schemes_and_urls_anywhere(self):
        package = self.build("2026-07-14T01:00:00Z")
        unsafe_values = (
            "/home/josh/ask-insects/source.csv#row/100",
            "/Users/josh/Documents/private.json",
            "/etc/passwd",
            "file:///tmp/x",
            "file:/tmp/x",
            "gs://private-bucket/x",
            "s3://private-bucket/x",
            "ssh://example.org/private/x",
            "private://consumer/x",
            r"C:\Users\josh\private.txt",
            r"\\server\private\share.txt",
            "http://example.org/not-https",
            "ftp://example.org/not-https",
        )
        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                invalid = json.loads(json.dumps(package))
                invalid["program_records"][0]["text"] = unsafe
                with self.assertRaisesRegex(ValueError, "unsafe value"):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_rejects_credentials_and_consumer_specific_keys(self):
        package = self.build("2026-07-14T01:00:00Z")
        unsafe_keys = (
            "api_token",
            "password",
            "auth",
            "authorization_header",
            "consumer_id",
            "customer_config",
            "tenant_identifier",
            "private_locator",
        )
        for unsafe_key in unsafe_keys:
            with self.subTest(unsafe_key=unsafe_key):
                invalid = json.loads(json.dumps(package))
                invalid["program_records"][0]["payload"][unsafe_key] = "secret"
                with self.assertRaisesRegex(ValueError, "unsafe key"):
                    validate_context_package(invalid, verify_hash=False)

        credentialed_urls = (
            "https://user:password@example.org/data",
            "https://example.org/data?token=secret",
            "https://example.org/data?auth=secret",
        )
        for locator in credentialed_urls:
            with self.subTest(locator=locator):
                invalid = json.loads(json.dumps(package))
                invalid["evidence_records"][0]["provenance"]["locator"] = locator
                with self.assertRaisesRegex(ValueError, "credential"):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_enforces_string_list_depth_and_package_size_limits(self):
        package = self.build("2026-07-14T01:00:00Z")

        oversized_string = json.loads(json.dumps(package))
        oversized_string["objective"] = "x" * (1024 * 1024)
        with self.assertRaisesRegex(ValueError, "100000"):
            validate_context_package(oversized_string, verify_hash=False)

        oversized_list = json.loads(json.dumps(package))
        oversized_list["knowledge_domains"] = [f"domain-{index}" for index in range(10_001)]
        with self.assertRaisesRegex(ValueError, "10000"):
            validate_context_package(oversized_list, verify_hash=False)

        too_deep = json.loads(json.dumps(package))
        nested: object = "leaf"
        for _ in range(21):
            nested = {"level": nested}
        too_deep["program_records"][0]["payload"]["nested"] = nested
        with self.assertRaisesRegex(ValueError, "depth 20"):
            validate_context_package(too_deep, verify_hash=False)

        oversized_package = json.loads(json.dumps(package))
        oversized_package["program_records"][0]["payload"]["large_public_fields"] = {
            f"field_{index}": "x" * 99_000 for index in range(170)
        }
        with self.assertRaisesRegex(ValueError, "16 MiB"):
            validate_context_package(oversized_package, verify_hash=False)

    def test_validator_rejects_non_finite_floats(self):
        package = self.build("2026-07-14T01:00:00Z")

        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                invalid = json.loads(json.dumps(package))
                invalid["program_records"][0]["payload"]["measurement"] = value
                with self.assertRaisesRegex(ValueError, "non-finite"):
                    validate_context_package(invalid, verify_hash=False)

    def test_validator_allows_generic_public_text_about_external_private_systems(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["program_records"][0]["text"] = (
            "Public evidence may inform external private systems, including Monarch."
        )

        validate_context_package(package, verify_hash=False)

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

    def test_validator_rejects_private_cloud_locator_without_consumer_markers(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["provenance"]["locator"] = (
            "gs://private-bucket/results.csv#row=1"
        )

        with self.assertRaisesRegex(ValueError, "unsafe value"):
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
                context_required_term_groups=CONTEXT_REQUIRED_TERM_GROUPS[
                    "treated_area_contact_avoidance"
                ],
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
            context_required_term_groups=[["avoidance"], ["measured"]],
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )
        package = self.build_with_contexts(
            [self.context("validator_gap_context", ["drosophila_suzukii"], [selector])]
        )
        package["gaps"][0]["candidate_count"] += 1

        with self.assertRaisesRegex(ValueError, "gap receipt"):
            validate_context_package(package, verify_hash=False)

    def test_status_receipt_must_match_database_record_count(self):
        status_path = self.artifact_dir / "source_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["record_count"] = status["record_count"] + 1
        status_path.write_text(json.dumps(status), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "record_count.*database"):
            self.build("2026-07-14T01:00:00Z", sync_status=False)

    def test_status_receipt_hash_is_stable_across_json_formatting(self):
        first = self.build("2026-07-14T01:00:00Z")
        status_path = self.artifact_dir / "source_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status_path.write_text(
            json.dumps(status, indent=4, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        second = self.build("2026-07-14T01:00:00Z")

        self.assertEqual(
            first["upstream_snapshot"]["source_status_sha256"],
            second["upstream_snapshot"]["source_status_sha256"],
        )
        self.assertEqual(first["content_sha256"], second["content_sha256"])

    def test_builder_uses_bounded_read_only_database_checks_not_integrity_scans(self):
        self._sync_status_record_count()
        real_connect = context_package_module.sqlite3.connect
        connect_calls = []
        statements: list[str] = []

        def tracked_connect(*args, **kwargs):
            connect_calls.append((args, kwargs))
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with patch(
            "askinsects.context_package.sqlite3.connect",
            side_effect=tracked_connect,
        ):
            build_context_package(
                artifact_dir=self.artifact_dir,
                config_path=self.config_path,
                context_config_source_url=TEST_CONTEXT_CONFIG_URL,
                context_config_sha256=hashlib.sha256(
                    self.config_path.read_bytes()
                ).hexdigest(),
                generated_at="2026-07-14T01:00:00Z",
            )

        self.assertEqual(len(connect_calls), 1)
        args, kwargs = connect_calls[0]
        self.assertIn("mode=ro", args[0])
        self.assertIs(kwargs.get("uri"), True)
        normalized = [" ".join(statement.casefold().split()) for statement in statements]
        self.assertIn("pragma query_only = on", normalized)
        self.assertIn("pragma query_only", normalized)
        self.assertTrue(any("from sqlite_master" in statement for statement in normalized))
        self.assertTrue(any("select count(*) from records" in statement for statement in normalized))
        self.assertFalse(any("quick_check" in statement for statement in normalized))
        self.assertFalse(any("integrity_check" in statement for statement in normalized))

    def test_builder_rejects_missing_required_source_table(self):
        with self.index.connect() as conn:
            conn.execute("DROP TABLE literature_fulltext_units")

        with self.assertRaisesRegex(ValueError, "missing required tables.*literature_fulltext_units"):
            self.build("2026-07-14T01:00:00Z")

    def test_discovery_uses_only_trusted_fields_not_generated_columns_or_species_label(self):
        self.index.upsert_records(
            [
                record(
                    "trusted-discovery:selected",
                    source="trusted_discovery_source",
                    species="Generated wrong species label",
                    title="Neutral generated database title",
                    text="Neutral generated database text.",
                    payload={
                        "title": "Drosophila suzukii needle assay",
                        "abstract": "Needle contact avoidance was measured directly.",
                    },
                ),
                record(
                    "trusted-discovery:decoy",
                    source="trusted_discovery_source",
                    species="Drosophila suzukii",
                    title="Needle contact avoidance Drosophila suzukii",
                    text="Needle contact avoidance was repeated in generated text.",
                    payload={
                        "title": "Drosophila suzukii locomotion assay",
                        "abstract": "Adult locomotion was measured directly.",
                    },
                ),
            ]
        )
        selector = self.selector(
            "trusted_discovery",
            "drosophila_suzukii",
            "trusted_discovery_source",
            query_any=["needle", "contact", "avoidance"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            limit=1,
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        package = self.build_with_contexts(
            [self.context("trusted_discovery_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 1)
        self.assertEqual(receipt["selected_record_ids"], ["trusted-discovery:selected"])
        self.assertEqual(package["evidence_records"][0]["species"], "Drosophila suzukii")

    def test_link_references_alone_do_not_make_generated_text_a_candidate(self):
        self.index.upsert_records(
            [
                record(
                    "parent:no-context-match",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Drosophila suzukii locomotion study",
                        }
                    },
                ),
                record(
                    "derived:generated-only-match",
                    source="linked_discovery_source",
                    species="Drosophila suzukii",
                    text="Needle contact avoidance appeared only in generated text.",
                    payload={
                        "source_record_id": "parent:no-context-match",
                        "fulltext_unit_id": "unit:no-context-match",
                    },
                ),
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id="unit:no-context-match",
                    record_id="parent:no-context-match",
                    source="public_parent_literature",
                    unit_index=0,
                    text="Adult movement was measured after emergence.",
                    url="https://example.org/fulltext/no-context-match",
                    license="CC-BY-4.0",
                    provenance=Provenance(
                        source_id="public_parent_literature",
                        locator="literature_fulltext_units#unit:no-context-match",
                        retrieved_at="2026-07-13T00:00:00Z",
                        source_url="https://example.org/fulltext/no-context-match",
                        license="CC-BY-4.0",
                    ),
                )
            ]
        )
        selector = self.selector(
            "linked_generated_only",
            "drosophila_suzukii",
            "linked_discovery_source",
            query_any=["needle", "contact", "avoidance"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            taxon_field_paths=[],
            context_field_paths=[],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": ["payload.raw_openalex_work.display_name"],
            },
            fulltext_context=self.fulltext_context(),
        )

        package = self.build_with_contexts(
            [
                self.context(
                    "linked_generated_only_context",
                    ["drosophila_suzukii"],
                    [selector],
                )
            ]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 0)
        self.assertEqual(receipt["rejection_counts"], {})
        self.assertEqual(package["evidence_records"], [])

    def test_generated_text_cannot_change_trusted_tie_ranking(self):
        def insert_rows(first_text: str, second_text: str) -> None:
            self.index.upsert_records(
                [
                    record(
                        record_id,
                        source="trusted_ranking_source",
                        species="Drosophila suzukii",
                        title=f"Generated title {record_id}",
                        text=generated_text,
                        payload={
                            "title": "Drosophila suzukii needle assay",
                            "abstract": "Needle contact avoidance was measured.",
                        },
                    )
                    for record_id, generated_text in (
                        ("trusted-ranking:a", first_text),
                        ("trusted-ranking:b", second_text),
                    )
                ]
            )

        selector = self.selector(
            "trusted_ranking",
            "drosophila_suzukii",
            "trusted_ranking_source",
            query_any=["needle", "contact", "avoidance"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            limit=1,
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )
        contexts = [self.context("trusted_ranking_context", ["drosophila_suzukii"], [selector])]

        insert_rows("Neutral generated text.", "Needle contact avoidance " * 20)
        first = self.build_with_contexts(contexts)
        insert_rows("Needle contact avoidance " * 20, "Neutral generated text.")
        second = self.build_with_contexts(contexts)

        self.assertEqual(first["selector_results"][0]["candidate_count"], 2)
        self.assertEqual(
            first["selector_results"][0]["selected_record_ids"],
            ["trusted-ranking:a"],
        )
        self.assertEqual(
            second["selector_results"][0]["selected_record_ids"],
            ["trusted-ranking:a"],
        )

    def test_unsafe_eligible_candidates_are_receipted_and_selection_continues(self):
        self.index.upsert_records(
            [
                record(
                    "boundary:bad-path",
                    source="boundary_candidates",
                    species="Drosophila suzukii",
                    title="see(/Users/josh/private/results.csv)",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "title": "Drosophila suzukii needle assay",
                        "abstract": "Needle contact avoidance was measured.",
                    },
                ),
                record(
                    "boundary:bad-credential",
                    source="boundary_candidates",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "title": [
                            "Drosophila suzukii needle assay",
                            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
                        ],
                        "abstract": "Needle contact avoidance was measured.",
                    },
                ),
                record(
                    "boundary:bad-number",
                    source="boundary_candidates",
                    species="Drosophila suzukii",
                    text="Generated contact avoidance candidate.",
                    payload={
                        "title": "Drosophila suzukii needle assay",
                        "abstract": [
                            "Needle contact avoidance was measured.",
                            float("nan"),
                        ],
                    },
                ),
                record(
                    "boundary:safe",
                    source="boundary_candidates",
                    species="Drosophila suzukii",
                    text="Neutral generated text.",
                    payload={
                        "title": "Drosophila suzukii needle assay",
                        "abstract": "Needle contact avoidance was measured.",
                    },
                ),
            ]
        )
        selector = self.selector(
            "boundary_selector",
            "drosophila_suzukii",
            "boundary_candidates",
            query_any=["needle", "contact", "avoidance"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            limit=1,
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        package = self.build_with_contexts(
            [self.context("boundary_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 4)
        self.assertEqual(receipt["eligible_count"], 1)
        self.assertEqual(receipt["selected_record_ids"], ["boundary:safe"])
        self.assertEqual(receipt["rejection_counts"], {"unsafe_export_boundary": 3})

    def test_parent_and_fulltext_basis_each_require_public_provenance(self):
        parent_specs = (
            ("parent:private", "https://metadata.google.internal/paper"),
            ("parent:unit-private", "https://example.org/paper/unit-private"),
            ("parent:public", "https://example.org/paper/public"),
        )
        child_specs = (
            ("derived:private-parent", "parent:private", "unit:public-one"),
            ("derived:private-unit", "parent:unit-private", "unit:private"),
            ("derived:public", "parent:public", "unit:public-two"),
        )
        self.index.upsert_records(
            [
                record(
                    parent_id,
                    source="basis_parent_source",
                    species="Drosophila suzukii",
                    text="Neutral generated parent text.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Drosophila suzukii study",
                            "abstract_inverted_index": {},
                        }
                    },
                    source_url=source_url,
                )
                for parent_id, source_url in parent_specs
            ]
            + [
                record(
                    child_id,
                    source="basis_provenance_candidates",
                    species="Drosophila suzukii",
                    text="Neutral generated child text.",
                    payload={
                        "source_record_id": parent_id,
                        "fulltext_unit_id": unit_id,
                    },
                )
                for child_id, parent_id, unit_id in child_specs
            ]
        )
        self.index.upsert_fulltext_units(
            [
                FullTextUnit(
                    unit_id=unit_id,
                    record_id=parent_id,
                    source="basis_parent_source",
                    unit_index=index,
                    text="Needle contact avoidance was measured on a treated surface.",
                    url=source_url,
                    license="CC-BY-4.0",
                    provenance=Provenance(
                        source_id="basis_parent_source",
                        locator=f"fulltext#row/{index}",
                        retrieved_at="2026-07-13T00:00:00Z",
                        source_url=source_url,
                    ),
                )
                for index, (unit_id, parent_id, source_url) in enumerate(
                    (
                        ("unit:public-one", "parent:private", "https://example.org/unit/one"),
                        ("unit:private", "parent:unit-private", "https://service.internal/unit"),
                        ("unit:public-two", "parent:public", "https://example.org/unit/two"),
                    )
                )
            ]
        )
        selector = self.selector(
            "basis_provenance_selector",
            "drosophila_suzukii",
            "basis_provenance_candidates",
            query_any=["needle", "contact", "avoidance"],
            context_required_term_groups=[["avoidance"], ["contact"]],
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
            [self.context("basis_provenance_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 3)
        self.assertEqual(receipt["selected_record_ids"], ["derived:public"])
        self.assertEqual(receipt["rejection_counts"], {"public_provenance_missing": 2})
        item = package["evidence_records"][0]
        taxon_basis = item["eligibility"]["taxon"]["basis"][0]
        context_basis = item["eligibility"]["context"]["basis"][0]
        self.assertEqual(taxon_basis["provenance"]["index_record_id"], "parent:public")
        self.assertEqual(context_basis["provenance"]["index_record_id"], "unit:public-two")

    def test_malformed_linked_parent_is_receipted_instead_of_crashing_build(self):
        self.index.upsert_records(
            [
                record(
                    "parent:malformed-source",
                    source="public_parent_literature",
                    species="Drosophila suzukii",
                    text="Indexed parent paper.",
                    payload={
                        "raw_openalex_work": {
                            "display_name": "Drosophila suzukii contact behavior",
                        }
                    },
                ),
                record(
                    "derived:malformed-parent",
                    source="malformed_parent_candidates",
                    species="Drosophila suzukii",
                    text="Generated candidate text.",
                    payload={
                        "source_record_id": "parent:malformed-source",
                        "abstract": "Contact avoidance was measured on a treated surface.",
                    },
                ),
            ]
        )
        with self.index.connect() as conn:
            conn.execute(
                "UPDATE records SET source='' WHERE record_id='parent:malformed-source'"
            )
        selector = self.selector(
            "malformed_parent_selector",
            "drosophila_suzukii",
            "malformed_parent_candidates",
            query_any=["contact", "avoidance"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            taxon_field_paths=[],
            context_field_paths=["payload.abstract"],
            parent_record={
                "record_id_path": "payload.source_record_id",
                "taxon_field_paths": ["payload.raw_openalex_work.display_name"],
            },
        )

        package = self.build_with_contexts(
            [
                self.context(
                    "malformed_parent_context",
                    ["drosophila_suzukii"],
                    [selector],
                )
            ]
        )

        self.assertEqual(package["evidence_records"], [])
        self.assertEqual(
            package["selector_results"][0]["rejection_counts"],
            {"public_provenance_missing": 1},
        )

    def test_validator_rejects_inconsistent_basis_provenance(self):
        package = self.build_linked_fulltext_package()
        mutations = (
            lambda basis: basis["provenance"].pop("license"),
            lambda basis: basis["provenance"].__setitem__("source_id", "wrong-source"),
            lambda basis: basis["provenance"].__setitem__("index_record_id", "wrong-row"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                invalid = json.loads(json.dumps(package))
                mutate(invalid["evidence_records"][0]["eligibility"]["taxon"]["basis"][0])
                with self.assertRaisesRegex(ValueError, "provenance"):
                    validate_context_package(invalid, verify_hash=False)

        direct = self.build("2026-07-14T01:00:00Z")
        direct["evidence_records"][0]["eligibility"]["taxon"]["basis"][0][
            "provenance"
        ]["locator"] = "https://example.org/different-public-row"
        with self.assertRaisesRegex(ValueError, "basis provenance.*record provenance"):
            validate_context_package(direct, verify_hash=False)

    def test_validator_rejects_under_selection_and_false_gap(self):
        package = self.build("2026-07-14T01:00:00Z")
        receipt = package["selector_results"][0]
        self.assertGreater(receipt["eligible_count"], 0)
        receipt["selected_count"] = 0
        receipt["selected_record_ids"] = []

        with self.assertRaisesRegex(ValueError, "selected_count must equal"):
            validate_context_package(package, verify_hash=False)

    def test_candidate_frontier_handles_more_than_sqlite_variable_limit(self):
        self.index.upsert_records(
            [
                record(
                    f"frontier:{index:04d}",
                    source="bounded_frontier_source",
                    species="Drosophila suzukii",
                    text="Neutral generated text.",
                    payload={
                        "title": "Drosophila suzukii needle assay",
                        "abstract": "Needle contact avoidance was measured.",
                    },
                )
                for index in range(1005)
            ]
        )
        selector = self.selector(
            "bounded_frontier",
            "drosophila_suzukii",
            "bounded_frontier_source",
            query_any=["needle"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            limit=1,
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        package = self.build_with_contexts(
            [self.context("bounded_frontier_context", ["drosophila_suzukii"], [selector])]
        )

        receipt = package["selector_results"][0]
        self.assertEqual(receipt["candidate_count"], 1005)
        self.assertEqual(receipt["eligible_count"], 1005)
        self.assertEqual(receipt["selected_count"], 1)

    def test_candidate_frontier_fails_closed_when_configuration_is_too_broad(self):
        self.index.upsert_records(
            [
                record(
                    f"too-broad:{index}",
                    source="too_broad_source",
                    species="Drosophila suzukii",
                    text="Neutral generated text.",
                    payload={
                        "title": "Drosophila suzukii needle assay",
                        "abstract": "Needle contact avoidance was measured.",
                    },
                )
                for index in range(4)
            ]
        )
        selector = self.selector(
            "too_broad",
            "drosophila_suzukii",
            "too_broad_source",
            query_any=["needle"],
            context_required_term_groups=[["avoidance"], ["contact"]],
            taxon_field_paths=["payload.title"],
            context_field_paths=["payload.abstract"],
        )

        with patch.object(context_package_module, "MAX_SELECTOR_CANDIDATE_FRONTIER", 3):
            with self.assertRaisesRegex(ValueError, "candidate frontier.*narrow"):
                self.build_with_contexts(
                    [self.context("too_broad_context", ["drosophila_suzukii"], [selector])]
                )

    def test_validator_rejects_embedded_credentials_paths_and_private_hosts(self):
        package = self.build("2026-07-14T01:00:00Z")
        unsafe_values = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwcml2YXRlIn0.signaturevalue",
            "api_key=sk-abcdefghijklmnopqrstuvwxyz012345",
            "token=abcdefghijklmnopqrstuvwxyz012345",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "see(/Users/josh/private/results.csv)",
            "https://metadata.google.internal/computeMetadata/v1/",
            "https://service.internal/private",
            "https://node.localhost/private",
            "https://lab.home.arpa/private",
            "metadata.google.internal",
            "::1",
            "fe80::1",
            "fd00::1",
        )
        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                invalid = json.loads(json.dumps(package))
                invalid["program_records"][0]["text"] = unsafe
                with self.assertRaisesRegex(ValueError, "unsafe|credential"):
                    validate_context_package(invalid, verify_hash=False)

        safe_values = (
            "The concentration ratio was 10:1 in the assay.",
            "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0000001&type=printable",
            "Bearer plants were observed near the treated plots.",
            "The internal state of the insect changed after feeding.",
        )
        for safe in safe_values:
            with self.subTest(safe=safe):
                valid = json.loads(json.dumps(package))
                valid["program_records"][0]["text"] = safe
                validate_context_package(valid, verify_hash=False)

    def test_public_provenance_rejects_private_dns_suffixes(self):
        for source_url in (
            "https://metadata.google.internal/source",
            "https://service.internal/source",
            "https://service.local/source",
            "https://service.localhost/source",
            "https://service.home.arpa/source",
        ):
            with self.subTest(source_url=source_url):
                candidate = {
                    "record_id": "public:record:1",
                    "provenance": {
                        "source_id": "public_source",
                        "source_url": source_url,
                        "locator": "records#row/1",
                        "retrieved_at": "2026-07-13T00:00:00Z",
                        "license": "CC-BY-4.0",
                    },
                }
                with self.assertRaisesRegex(ValueError, "public HTTPS source_url"):
                    context_package_module._public_provenance(candidate)

    def test_config_provenance_is_pinned_to_immutable_version_commit(self):
        self._sync_status_record_count()
        package = build_context_package(
            artifact_dir=self.artifact_dir,
            program_config_path=DEFAULT_PROGRAM_CONFIG,
            generated_at="2026-07-14T01:00:00Z",
        )
        self.assertEqual(
            package["configuration_sources"]["context_config"]["source_url"],
            PUBLIC_CONTEXT_CONFIG_URL,
        )
        self.assertEqual(
            package["configuration_sources"]["program_config"]["source_url"],
            PUBLIC_PROGRAM_CONFIG_URL,
        )
        self.assertTrue(
            all(
                record["provenance"]["locator"].startswith(
                    f"{PUBLIC_PROGRAM_CONFIG_URL}#jsonpath=$"
                )
                for record in package["program_records"]
            )
        )
        self.assertTrue(
            all(
                context["provenance"]["locator"].startswith(
                    f"{PUBLIC_CONTEXT_CONFIG_URL}#jsonpath=$.contexts["
                )
                for context in package["contexts"]
            )
        )
        locators = [
            record["provenance"]["locator"]
            for record in package["program_records"]
        ]
        locators.extend(
            context["provenance"]["locator"] for context in package["contexts"]
        )
        self.assertNotIn("blob/main", json.dumps(locators))

        mutable = json.loads(json.dumps(package))
        mutable["program_records"][0]["provenance"]["locator"] = (
            "https://github.com/manintheandes/ask-insects/blob/main/"
            "config/insect-intelligence-programs.json"
        )
        with self.assertRaisesRegex(ValueError, "public source"):
            validate_context_package(mutable, verify_hash=False)

    def test_validator_requires_exact_identifier_and_species_types(self):
        package = self.build("2026-07-14T01:00:00Z")
        mutations = (
            lambda value: value["program_records"][0].__setitem__("species", {}),
            lambda value: value["program_records"][0].__setitem__("record_id", 7),
            lambda value: value["contexts"][0].__setitem__("id", 7),
            lambda value: value["selector_results"][0].__setitem__("selector_id", 7),
            lambda value: value["evidence_records"][0].__setitem__("record_id", 7),
            lambda value: value["evidence_records"][0]["eligibility"]["taxon"]["basis"][0].__setitem__("selector_id", 7),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                invalid = json.loads(json.dumps(package))
                mutate(invalid)
                with self.assertRaisesRegex(ValueError, "string"):
                    validate_context_package(invalid, verify_hash=False)

        nullable_species = json.loads(json.dumps(package))
        nullable_species["program_records"][0]["species"] = None
        validate_context_package(nullable_species, verify_hash=False)

    def test_validator_rejects_hash_mismatch(self):
        package = self.build("2026-07-14T01:00:00Z")
        package["evidence_records"][0]["text"] = "changed after hashing"

        with self.assertRaisesRegex(ValueError, "content_sha256"):
            validate_context_package(package)


if __name__ == "__main__":
    unittest.main()
