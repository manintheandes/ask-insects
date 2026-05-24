from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.extracted_facts import (
    EXTRACTED_FACTS_SOURCE_ID,
    build_extracted_fact_records,
)
from askinsects.sources.literature import FullTextUnit


def write_extracted_facts_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    paper = EvidenceRecord(
        record_id="openalex:WFACT1",
        lane="literature",
        source="aedes_literature_openalex",
        title="Aedes aegypti tables across competence resistance behavior ecology and dengue control",
        text="Aedes aegypti paper with linked supplementary tables.",
        species="Aedes aegypti",
        url="https://example.org/aedes-facts",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/literature/page.json#WFACT1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="open metadata",
            source_url="https://example.org/aedes-facts",
        ),
        payload={
            "ids": {
                "doi": "10.1234/aedes.fact",
                "pmid": "12345678",
                "pmcid": "PMC1234567",
            },
            "supplementary_materials": [
                {
                    "title": "Supplementary Table 1: Aedes aegypti assay measurements",
                    "url": "https://example.org/aedes-facts/supp-table-1.csv",
                    "file_type": "csv",
                    "license": "CC-BY",
                    "size": 2048,
                    "source": "publisher",
                }
            ],
        },
    )
    fulltext = FullTextUnit(
        unit_id="openalex:WFACT1:fulltext:0",
        record_id="openalex:WFACT1",
        source="aedes_literature_openalex",
        unit_index=0,
        text=(
            "Table 1 vector competence dengue virus infection rate 80%, dissemination rate 40%, "
            "transmission rate 20% in saliva at 28 C after a 10^6 PFU blood meal, 7 dpi, Rockefeller strain. "
            "Supplementary resistance table: permethrin bioassay mortality 55%, knockdown after exposure, "
            "LC50, VGSC V1016G genotype frequency in Brazil. "
            "Behavior assay: Y-tube olfactometer with lactic acid stimulus in 5 day old female Rockefeller "
            "mosquitoes had a response rate of 62%. "
            "Ecology table: larval breeding site water storage container habitat in an urban rainy season "
            "range survey at 27 C in Kenya. "
            "Public health table: dengue cases 1234, deaths 5, serotype DENV-2, Wolbachia intervention in Brazil 2024."
        ),
        url="https://example.org/aedes-facts/fulltext",
        license="CC-BY",
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/fulltext/WFACT1.txt#chunk/0",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/aedes-facts/fulltext",
        ),
    )
    index.upsert_records_and_fulltext_units([paper], [fulltext])


class ExtractedFactsSourceTests(unittest.TestCase):
    def test_build_extracted_fact_records_emits_cross_lane_payloads_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)

            result = build_extracted_fact_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.source_id, EXTRACTED_FACTS_SOURCE_ID)
            lanes = {record.lane for record in result.records}
            self.assertIn("vector_competence", lanes)
            self.assertIn("resistance", lanes)
            self.assertIn("behavior", lanes)
            self.assertIn("ecology", lanes)
            self.assertIn("public_health", lanes)
            self.assertIn("literature", lanes)
            self.assertGreaterEqual(result.fact_counts["vector_competence"], 1)
            self.assertEqual(result.supplement_manifest_count, 1)

            vector = next(record for record in result.records if record.payload["fact_type"] == "vector_competence")
            self.assertEqual(vector.source, EXTRACTED_FACTS_SOURCE_ID)
            self.assertEqual(vector.payload["schema_version"], "2026-05-24.v1")
            self.assertEqual(vector.payload["confidence"], "candidate")
            self.assertEqual(vector.payload["source_record_id"], "openalex:WFACT1")
            self.assertEqual(vector.payload["fulltext_unit_id"], "openalex:WFACT1:fulltext:0")
            self.assertIn("dengue virus", vector.payload["fields"]["pathogen"])
            self.assertIn("28 C", vector.payload["fields"]["temperature_values"])
            self.assertIn("literature_fulltext_units#openalex:WFACT1:fulltext:0", vector.provenance.locator)
            self.assertEqual(result.max_fulltext_units, 5000)
            self.assertEqual(result.selected_record_text_count, 0)

            manifest = next(record for record in result.records if record.payload["fact_type"] == "supplement_manifest")
            self.assertEqual(manifest.lane, "literature")
            self.assertEqual(manifest.payload["confidence"], "manifest")
            self.assertEqual(manifest.payload["supplement"]["url"], "https://example.org/aedes-facts/supp-table-1.csv")
            self.assertIn("records#openalex:WFACT1", manifest.provenance.locator)

    def test_build_extracted_fact_records_uses_bounded_fulltext_probe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            paper = EvidenceRecord(
                record_id="openalex:WFACT2",
                lane="literature",
                source="aedes_literature_openalex",
                title="Aedes aegypti dengue vector competence follow-up",
                text="Aedes aegypti follow-up paper.",
                species="Aedes aegypti",
                url="https://example.org/aedes-facts-2",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/literature/page.json#WFACT2",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="open metadata",
                    source_url="https://example.org/aedes-facts-2",
                ),
                payload={},
            )
            unit = FullTextUnit(
                unit_id="openalex:WFACT2:fulltext:0",
                record_id="openalex:WFACT2",
                source="aedes_literature_openalex",
                unit_index=0,
                text="Aedes aegypti dengue vector competence infection rate 40%.",
                url="https://example.org/aedes-facts-2/fulltext",
                license="CC-BY",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WFACT2.txt#chunk/0",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="CC-BY",
                    source_url="https://example.org/aedes-facts-2/fulltext",
                ),
            )
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records_and_fulltext_units(
                [paper],
                [unit],
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                max_fulltext_units=1,
            )

            self.assertEqual(result.fulltext_unit_count, 2)
            self.assertEqual(result.selected_fulltext_unit_count, 1)
            self.assertTrue(any(gap["reason"] == "fulltext_prefilter_limit_applied" for gap in result.gaps))

    def test_build_extracted_fact_records_skips_markup_noise_fulltext(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            paper = EvidenceRecord(
                record_id="openalex:WHTML",
                lane="literature",
                source="aedes_literature_openalex",
                title="Aedes aegypti landing page",
                text="Aedes aegypti landing page.",
                species="Aedes aegypti",
                url="https://example.org/html",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/literature/page.json#WHTML",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="open metadata",
                    source_url="https://example.org/html",
                ),
                payload={},
            )
            unit = FullTextUnit(
                unit_id="openalex:WHTML:fulltext:0",
                record_id="openalex:WHTML",
                source="aedes_literature_openalex",
                unit_index=0,
                text=(
                    "<!DOCTYPE html><html><head><style>:root{--color:red;font-family:sans-serif}"
                    "*{box-sizing:border-box}</style><script></script></head><body><div>"
                    "Aedes aegypti behavior response rate 99% oviposition assay"
                    "</div></body></html>"
                ),
                url="https://example.org/html",
                license="OpenAlex OA PDF URL",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WHTML.html#chunk/0",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="OpenAlex OA PDF URL",
                    source_url="https://example.org/html",
                ),
            )
            css_unit = FullTextUnit(
                unit_id="openalex:WHTML:fulltext:1",
                record_id="openalex:WHTML",
                source="aedes_literature_openalex",
                unit_index=1,
                text=(
                    "Aedes aegypti behavior response rate 99% "
                    "--ds-header-color:#fff;--ds-footer-color:#000;--ds-sidebar-width:50px;"
                    "--ds-slider-color:#eee;--ds-button-color:#111;var(--ds-header-color);"
                    "var(--ds-footer-color);margin:0!important;padding:0!important;width:100%!important;"
                    "display:flex!important;align-items:center!important"
                ),
                url="https://example.org/html",
                license="OpenAlex OA PDF URL",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WHTML.html#chunk/1",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="OpenAlex OA PDF URL",
                    source_url="https://example.org/html",
                ),
            )
            partial_css_unit = FullTextUnit(
                unit_id="openalex:WHTML:fulltext:2",
                record_id="openalex:WHTML",
                source="aedes_literature_openalex",
                unit_index=2,
                text=(
                    "Aedes aegypti behavior response rate 88% "
                    ".btn{display:inline-block;font-weight:400;color:#212529;text-align:center;"
                    "vertical-align:middle;background-color:#0000;border:1px solid rgba(0,0,0,0);"
                    "padding:.375rem .75rem;font-size:1rem;line-height:1.5;border-radius:0;"
                    "transition:color .15s ease-in-out,background-color .15s ease-in-out,"
                    "border-color .15s ease-in-out,box-shadow .15s ease-in-out}"
                    "@media (prefers-reduced-motion: reduce){.btn{transition:none}}"
                    ".btn:hover{color:#212529;text-decoration:none}"
                ),
                url="https://example.org/html",
                license="OpenAlex OA PDF URL",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WHTML.html#chunk/2",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="OpenAlex OA PDF URL",
                    source_url="https://example.org/html",
                ),
            )
            encoded_state_unit = FullTextUnit(
                unit_id="openalex:WHTML:fulltext:3",
                record_id="openalex:WHTML",
                source="aedes_literature_openalex",
                unit_index=3,
                text=(
                    "Aedes aegypti behavior response rate 77% "
                    ",&q;rotatable-typeahead.value.filter.date-Year-Month.relative&q;:&q;Month, relative&q;,"
                    "&q;rotatable-typeahead.value.filter.dso-bitstream&q;:&q;Bitstream&q;,"
                    "&q;requestUUIDs&q;:[&q;client/1b5fdb62-61bd-49e2-bb7f-3cb98c817659&q;],"
                    "&q;metadata&q;:{&q;dc.contributor.author&q;:[{&q;value&q;:&q;Jones, Adam&q;}],"
                    "&q;server/api/statistics/statlets&q;:{&q;type&q;:{&q;value&q;:&q;statlet&q;}}"
                ),
                url="https://example.org/html",
                license="OpenAlex OA PDF URL",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WHTML.html#chunk/3",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="OpenAlex OA PDF URL",
                    source_url="https://example.org/html",
                ),
            )
            meta_tag_unit = FullTextUnit(
                unit_id="openalex:WHTML:fulltext:4",
                record_id="openalex:WHTML",
                source="aedes_literature_openalex",
                unit_index=4,
                text=(
                    "Aedes aegypti host-seeking behavior response rate 66% "
                    "or.\"> <meta itemprop=\"description\" content=\"Aedes aegypti mosquitoes are the principal "
                    "vectors for Dengue Fever. Our goal was to discover new ways to interfere with the ability "
                    "of a mosquito to locate a human host for a blood meal.\"> <meta itemprop=\"name\" "
                    "content=\"The Neuropeptide Regulation of Host-Seeking Behavior in Aedes Aegypti Mosquitoes\">"
                ),
                url="https://example.org/html",
                license="OpenAlex OA PDF URL",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WHTML.html#chunk/4",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="OpenAlex OA PDF URL",
                    source_url="https://example.org/html",
                ),
            )
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records_and_fulltext_units([paper], [unit])
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_fulltext_units([unit, css_unit, partial_css_unit, encoded_state_unit, meta_tag_unit])

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                max_fulltext_units=6,
            )

            self.assertFalse(any(record.payload.get("source_record_id") == "openalex:WHTML" for record in result.records))

    def test_build_extracted_fact_records_ignores_non_openalex_literature_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="paper:fixture",
                        lane="literature",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti behavior fixture paper",
                        text="Aedes aegypti Y-tube olfactometer and host-seeking behavior.",
                        species="Aedes aegypti",
                        url="https://example.org/fixture",
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="data/fixtures/mosquito_records.json#paper:fixture",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                    )
                ]
            )

            result = build_extracted_fact_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.records, [])
            self.assertEqual(result.source_record_count, 0)
            self.assertEqual(result.selected_record_text_count, 0)
            self.assertEqual(result.gaps[0]["reason"], "no_literature_records")

    def test_build_extracted_fact_records_rejects_non_positive_fulltext_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)

            with self.assertRaisesRegex(ValueError, "max_fulltext_units must be positive"):
                build_extracted_fact_records(
                    artifact_dir,
                    retrieved_at="2026-05-24T00:00:00Z",
                    max_fulltext_units=0,
                )

    def test_build_extracted_fact_records_records_gap_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_extracted_fact_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], EXTRACTED_FACTS_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
