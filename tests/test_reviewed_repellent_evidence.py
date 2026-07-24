from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.sources.reviewed_repellent_evidence import (
    REVIEWED_REPELLENT_SOURCE_ID,
    ReviewedRepellentEvidenceError,
    build_reviewed_repellent_records,
    load_reviewed_repellent_catalog,
)


def catalog_payload() -> dict[str, object]:
    return {
        "schema_version": "ask-insects-reviewed-repellent-evidence.v1",
        "last_reviewed": "2026-07-23",
        "materials": [
            {
                "id": "eugenol",
                "canonical_name": "eugenol",
                "material_type": "pure_compound",
                "exact_aliases": ["eugenol"],
            },
            {
                "id": "one_four_cineole",
                "canonical_name": "1,4-cineole",
                "material_type": "pure_compound",
                "exact_aliases": ["1,4-cineole", "1,4 cineole"],
            },
            {
                "id": "one_eight_cineole",
                "canonical_name": "1,8-cineole",
                "material_type": "pure_compound",
                "exact_aliases": ["1,8-cineole", "1,8 cineole", "eucalyptol"],
            },
        ],
        "evidence": [
            {
                "id": "eugenol_aedes_close_range",
                "material_id": "eugenol",
                "species_id": "aedes_aegypti",
                "scientific_name": "Aedes aegypti",
                "evidence_relation": "exact_material",
                "evidence_class": "repellent_effect",
                "assay_family": "close_proximity_odor",
                "exposure_route": "non_contact",
                "endpoint": "movement away from treated filter paper",
                "finding": (
                    "Eugenol produced significant close-range repellency in "
                    "Aedes aegypti under this assay."
                ),
                "limitations": [
                    "The assay did not measure landing, biting, complete protection time, or field efficacy."
                ],
                "supporting_provenance": [
                    {
                        "title": "Insect repellents mediate species-specific olfactory behaviours in mosquitoes",
                        "public_url": "https://doi.org/10.1186/s12936-020-03206-8",
                        "source_id": "doi:10.1186/s12936-020-03206-8",
                        "locator": (
                            "Methods: close-proximity odor assay; Results: "
                            "Aedes aegypti species comparison"
                        ),
                    }
                ],
            }
        ],
    }


class ReviewedRepellentEvidenceTests(unittest.TestCase):
    def write_catalog(self, root: Path, payload: dict[str, object]) -> Path:
        path = root / "reviewed-repellent-evidence.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def test_builds_structured_public_records_with_exact_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records = build_reviewed_repellent_records(
                catalog_path=self.write_catalog(root, catalog_payload()),
                retrieved_at="2026-07-23T00:00:00Z",
            )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, REVIEWED_REPELLENT_SOURCE_ID)
        self.assertEqual(record.species, "Aedes aegypti")
        self.assertEqual(record.payload["atom_type"], "reviewed_repellent_evidence")
        evidence = record.payload["evidence"]
        self.assertEqual(evidence["canonical_name"], "eugenol")
        self.assertEqual(evidence["exact_aliases"], ["eugenol"])
        self.assertEqual(evidence["evidence_relation"], "exact_material")
        self.assertEqual(
            evidence["supporting_provenance"][0]["source_id"],
            "doi:10.1186/s12936-020-03206-8",
        )
        self.assertIn(
            "Aedes aegypti species comparison",
            evidence["supporting_provenance"][0]["locator"],
        )

    def test_default_catalog_contains_hut_and_epidemiological_transfluthrin_evidence(
        self,
    ):
        catalog = load_reviewed_repellent_catalog()
        evidence_by_id = {
            item["id"]: item
            for item in catalog["evidence"]
        }

        guardian = evidence_by_id[
            "transfluthrin_guardian_anopheles_hut_2025"
        ]
        self.assertEqual(
            guardian["supporting_provenance"][0]["source_id"],
            "doi:10.3389/fmala.2025.1570480",
        )
        self.assertIn("82.7%", guardian["finding"])
        self.assertIn("65.1%", guardian["finding"])
        self.assertIn("20.1%", guardian["finding"])
        self.assertIn(
            "do not estimate malaria-case reduction",
            " ".join(guardian["limitations"]),
        )
        self.assertIn(
            "contradictory declarations",
            " ".join(guardian["limitations"]),
        )
        self.assertIn(
            "Funding and Conflict of interest",
            guardian["supporting_provenance"][0]["locator"],
        )

        kenya = evidence_by_id[
            "transfluthrin_kenya_malaria_cluster_trial_2025"
        ]
        self.assertEqual(
            kenya["supporting_provenance"][0]["source_id"],
            "doi:10.1016/S0140-6736(24)02253-0",
        )
        self.assertIn("32.7%", kenya["finding"])
        self.assertIn("29.5%", kenya["finding"])
        self.assertIn("interim results", kenya["finding"])
        self.assertIn("two units per 9 square metres", kenya["finding"])
        self.assertIn("29 clusters per arm", kenya["finding"])
        self.assertIn(
            "does not make another product's hut endpoints",
            " ".join(kenya["limitations"]),
        )

        recommendation = evidence_by_id[
            "transfluthrin_who_spatial_emanator_recommendation_2025"
        ]
        self.assertEqual(
            recommendation["supporting_provenance"][0]["source_id"],
            "who:spatial-emanator-recommendation-2025-08-13",
        )
        self.assertIn("in addition to insecticide-treated nets", recommendation["finding"])

        guardian_pq = evidence_by_id[
            "transfluthrin_who_guardian_prequalification_2025"
        ]
        self.assertIn("P-12643", guardian_pq["finding"])
        self.assertIn("2.5 g per unit", guardian_pq["finding"])

        guardian_assessment = evidence_by_id[
            "transfluthrin_who_guardian_efficacy_assessment_2025"
        ]
        self.assertIn("BIT084 NI", guardian_assessment["finding"])
        self.assertIn("not used to inform decision making", guardian_assessment["finding"])

        equivalence = evidence_by_id[
            "transfluthrin_who_spatial_emanator_equivalence_guidance_2025"
        ]
        self.assertIn("not accepted", equivalence["finding"])

        module5 = evidence_by_id[
            "transfluthrin_who_spatial_emanator_module5_2025"
        ]
        self.assertIn("susceptible and insecticide-resistant", module5["finding"])
        self.assertIn("at least three semi-field studies", module5["finding"])

    def test_distinct_cineole_isomers_cannot_share_an_exact_alias(self):
        payload = catalog_payload()
        payload["materials"][2]["exact_aliases"].append("1,4 cineole")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedRepellentEvidenceError,
                "exact alias.*shared",
            ):
                load_reviewed_repellent_catalog(path)

    def test_rejects_internal_or_imprecise_claim_provenance(self):
        payload = catalog_payload()
        payload["evidence"][0]["supporting_provenance"][0] = {
            "title": "Internal catalog",
            "public_url": "https://example.org/catalog",
            "source_id": "reviewed_repellent_evidence",
            "locator": "config/reviewed-repellent-evidence.json#jsonpath=$.evidence[0]",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedRepellentEvidenceError,
                "exact public source",
            ):
                load_reviewed_repellent_catalog(path)

    def test_rejects_private_experiment_coupling(self):
        payload = catalog_payload()
        payload["evidence"][0]["private_experiment_id"] = "experiment:secret"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_catalog(Path(tmpdir), payload)
            with self.assertRaisesRegex(
                ReviewedRepellentEvidenceError,
                "private or consumer-specific",
            ):
                load_reviewed_repellent_catalog(path)


if __name__ == "__main__":
    unittest.main()
