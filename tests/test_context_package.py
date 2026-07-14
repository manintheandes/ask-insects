import json
import tempfile
import unittest
from pathlib import Path

from askinsects.context_package import (
    DEFAULT_CONTEXT_CONFIG,
    build_context_package,
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
    def test_default_config_path_is_independent_of_launch_directory(self):
        self.assertTrue(DEFAULT_CONTEXT_CONFIG.is_absolute())
        self.assertTrue(DEFAULT_CONTEXT_CONFIG.is_file())

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
                    "schema_version": "ask-insects-context-package-config.v1",
                    "package_version": "2026-07-14.1",
                    "last_reviewed": "2026-07-14",
                    "objective": "Provide public context for private interpretation.",
                    "knowledge_domains": ["behavior"],
                    "contexts": [
                        {
                            "id": "contact_no_contact",
                            "species_ids": ["drosophila_suzukii"],
                            "private_assay_families": ["contact_no_contact"],
                            "private_assay_modes": ["contact", "non_contact"],
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
                                    "query_any": ["avoidance", "repellent"],
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
