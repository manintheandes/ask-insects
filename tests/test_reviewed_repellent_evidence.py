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
