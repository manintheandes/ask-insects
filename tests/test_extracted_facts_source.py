from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.extracted_facts import (
    DEFAULT_MAX_SUPPLEMENT_BYTES,
    EXTRACTED_FACTS_SOURCE_ID,
    build_extracted_fact_records,
    fetch_public_supplement_metadata,
)
from askinsects.sources.literature import FullTextUnit


def make_xlsx_bytes(rows: list[list[str]]) -> bytes:
    strings: list[str] = []
    string_index: dict[str, int] = {}
    for row in rows:
        for value in row:
            if value not in string_index:
                string_index[value] = len(strings)
                strings.append(value)

    def cell_ref(column_index: int, row_index: int) -> str:
        return f"{chr(ord('A') + column_index)}{row_index}"

    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            cells.append(f'<c r="{cell_ref(column_index, row_index)}" t="s"><v>{string_index[value]}</v></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    shared_strings = "".join(f"<si><t>{value}</t></si>" for value in strings)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
""")
        archive.writestr("_rels/.rels", """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
""")
        archive.writestr("xl/workbook.xml", """<?xml version="1.0"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>
""")
        archive.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>
""")
        archive.writestr("xl/sharedStrings.xml", f"""<?xml version="1.0"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" uniqueCount="{len(strings)}">{shared_strings}</sst>
""")
        archive.writestr("xl/worksheets/sheet1.xml", f"""<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>
""")
    return buffer.getvalue()


def make_docx_bytes(rows: list[list[str]]) -> bytes:
    def cell(value: str) -> str:
        return f"<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc>"

    table_rows = []
    for row in rows:
        table_rows.append(f"<w:tr>{''.join(cell(value) for value in row)}</w:tr>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:tbl>{''.join(table_rows)}</w:tbl></w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
""")
        archive.writestr("_rels/.rels", """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
""")
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


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


def write_single_supplement_fixture(
    artifact_dir: Path,
    *,
    record_id: str,
    title: str,
    text: str,
    supplement_url: str,
) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id=record_id,
                lane="literature",
                source="aedes_literature_openalex",
                title=title,
                text=text,
                species="Aedes aegypti",
                url=f"https://example.org/{record_id.replace(':', '-')}",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator=f"raw/literature/page.json#{record_id}",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="open metadata",
                    source_url=f"https://openalex.org/{record_id.split(':')[-1]}",
                ),
                payload={
                    "ids": {"doi": "10.1234/aedes.supplement"},
                    "supplementary_materials": [
                        {
                            "title": "Additional file",
                            "url": supplement_url,
                            "file_type": "docx",
                            "license": "CC-BY",
                            "source": "publisher",
                        }
                    ],
                },
            )
        ]
    )


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
            self.assertEqual(result.parsed_supplement_row_count, 0)

            manifest = next(record for record in result.records if record.payload["fact_type"] == "supplement_manifest")
            self.assertEqual(manifest.lane, "literature")
            self.assertEqual(manifest.payload["confidence"], "manifest")
            self.assertEqual(manifest.payload["supplement"]["url"], "https://example.org/aedes-facts/supp-table-1.csv")
            self.assertIn("records#openalex:WFACT1", manifest.provenance.locator)

    def test_build_extracted_fact_records_discovers_supplements_from_injected_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                self.assertEqual(request["pmcid"], "PMC1234567")
                return [
                    {
                        "title": "Europe PMC Supplementary Table A",
                        "url": "https://example.org/europepmc/table-a.tsv",
                        "file_type": "tsv",
                        "license": "CC-BY",
                        "source": "europe_pmc",
                    }
                ]

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
            )

            manifests = [record for record in result.records if record.payload["fact_type"] == "supplement_manifest"]
            self.assertEqual(result.discovered_supplement_count, 1)
            self.assertTrue(any(record.payload["supplement"]["source"] == "europe_pmc" for record in manifests))
            self.assertTrue(any(record.payload["supplement"]["url"] == "https://example.org/europepmc/table-a.tsv" for record in manifests))

    def test_build_extracted_fact_records_discovers_supplements_from_fulltext_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            paper = EvidenceRecord(
                record_id="openalex:WFULLTEXTSUPP",
                lane="literature",
                source="aedes_literature_openalex",
                title="Aedes aegypti vector competence paper with full text supplement link",
                text="Aedes aegypti dengue vector competence paper.",
                species="Aedes aegypti",
                url="https://publisher.example/fulltext-link-paper",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/literature/page.json#WFULLTEXTSUPP",
                    retrieved_at="2026-05-24T00:00:00Z",
                ),
                payload={"ids": {"doi": "10.1234/fulltext.supp"}},
            )
            fulltext = FullTextUnit(
                unit_id="openalex:WFULLTEXTSUPP:fulltext:0",
                record_id="openalex:WFULLTEXTSUPP",
                source="aedes_literature_openalex",
                unit_index=0,
                text=(
                    "The supplementary data are public at "
                    "https://publisher.example/files/supplementary-table-s2.csv. "
                    "Table S2 reports dengue vector competence infection rate results."
                ),
                url="https://publisher.example/fulltext-link-paper/fulltext",
                license="CC-BY",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WFULLTEXTSUPP.txt#chunk/0",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="CC-BY",
                    source_url="https://publisher.example/fulltext-link-paper/fulltext",
                ),
            )
            index.upsert_records_and_fulltext_units([paper], [fulltext])

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=lambda request: [],
            )

            manifests = [record for record in result.records if record.payload["fact_type"] == "supplement_manifest"]
            self.assertEqual(result.supplement_manifest_count, 1)
            self.assertEqual(result.supplement_discovery_route_counts["fulltext_link_mining"], 1)
            self.assertEqual(manifests[0].payload["supplement"]["source"], "fulltext_link_mining")
            self.assertEqual(
                manifests[0].payload["supplement"]["url"],
                "https://publisher.example/files/supplementary-table-s2.csv",
            )

    def test_fetch_public_supplement_metadata_discovers_zenodo_supported_files(self):
        def fake_json(url: str) -> dict[str, object]:
            if "europepmc" in url:
                return {}
            self.assertEqual(url, "https://zenodo.org/api/records/19918130")
            return {
                "metadata": {"license": {"id": "cc-by-4.0"}},
                "files": [
                    {
                        "key": "resistance-table.csv",
                        "size": 1200,
                        "checksum": "md5:abc123",
                        "links": {"self": "https://zenodo.org/api/records/19918130/files/resistance-table.csv/content"},
                    },
                    {
                        "key": "paper.pdf",
                        "size": 100000,
                        "links": {"self": "https://zenodo.org/api/records/19918130/files/paper.pdf/content"},
                    },
                ],
            }

        with patch("askinsects.sources.extracted_facts._fetch_json_url", side_effect=fake_json):
            supplements = fetch_public_supplement_metadata(
                {
                    "record_id": "openalex:WZENODO",
                    "doi": "10.5281/zenodo.19918130",
                    "url": "https://doi.org/10.5281/zenodo.19918130",
                }
            )

        self.assertEqual(len(supplements), 2)
        self.assertEqual(supplements[0]["source"], "zenodo")
        self.assertEqual(supplements[0]["file_type"], "csv")
        self.assertEqual(supplements[0]["license"], "cc-by-4.0")
        self.assertEqual(supplements[0]["checksum"], "md5:abc123")
        self.assertEqual(supplements[1]["file_type"], "pdf")

    def test_fetch_public_supplement_metadata_discovers_crossref_relations(self):
        def fake_json(url: str) -> dict[str, object]:
            if "europepmc" in url:
                return {}
            if "api.crossref.org/works/" in url:
                return {
                    "message": {
                        "relation": {
                            "has-supplement": [
                                {
                                    "id": "https://example.org/publisher/supplement-table.xlsx",
                                    "id-type": "uri",
                                }
                            ],
                            "is-supplemented-by": [
                                {
                                    "id": "10.6084/m9.figshare.12345",
                                    "id-type": "doi",
                                }
                            ],
                            "is-supplement-to": [
                                {
                                    "id": "10.1186/s13071-025-07140-z",
                                    "id-type": "doi",
                                }
                            ],
                        }
                    }
                }
            return {}

        with patch("askinsects.sources.extracted_facts._fetch_json_url", side_effect=fake_json):
            supplements = fetch_public_supplement_metadata(
                {
                    "record_id": "openalex:WCROSSREF",
                    "doi": "10.1111/aedes.crossref",
                    "url": "https://doi.org/10.1111/aedes.crossref",
                }
            )

        urls = {str(item["url"]) for item in supplements}
        self.assertIn("https://example.org/publisher/supplement-table.xlsx", urls)
        self.assertIn("https://doi.org/10.6084/m9.figshare.12345", urls)
        self.assertNotIn("https://doi.org/10.1186/s13071-025-07140-z", urls)
        self.assertTrue(any(item["source"] == "crossref_relation" for item in supplements))

    def test_fetch_public_supplement_metadata_discovers_datacite_relations(self):
        def fake_json(url: str) -> dict[str, object]:
            if "europepmc" in url:
                return {}
            if "api.datacite.org/dois/" in url:
                return {
                    "data": {
                        "attributes": {
                            "relatedIdentifiers": [
                                {
                                    "relatedIdentifier": "https://example.org/datacite/supplement.csv",
                                    "relatedIdentifierType": "URL",
                                    "relationType": "IsSupplementedBy",
                                },
                                {
                                    "relatedIdentifier": "10.1186/s13071-025-07140-z",
                                    "relatedIdentifierType": "DOI",
                                    "relationType": "IsSupplementTo",
                                },
                            ]
                        }
                    }
                }
            return {}

        with patch("askinsects.sources.extracted_facts._fetch_json_url", side_effect=fake_json):
            supplements = fetch_public_supplement_metadata(
                {
                    "record_id": "openalex:WDATACITE",
                    "doi": "10.5061/dryad.aedes",
                    "url": "https://doi.org/10.5061/dryad.aedes",
                }
            )

        self.assertTrue(any(item["source"] == "datacite_relation" for item in supplements))
        self.assertTrue(any(item["url"] == "https://example.org/datacite/supplement.csv" for item in supplements))
        self.assertFalse(any(item["url"] == "https://doi.org/10.1186/s13071-025-07140-z" for item in supplements))

    def test_fetch_public_supplement_metadata_discovers_unpaywall_oa_locations(self):
        def fake_json(url: str) -> dict[str, object]:
            if "europepmc" in url:
                return {}
            if "api.unpaywall.org" in url:
                return {
                    "best_oa_location": {
                        "url": "https://publisher.example/article",
                        "url_for_pdf": "https://publisher.example/article/supplement.pdf",
                        "license": "cc-by",
                    },
                    "oa_locations": [
                        {
                            "url": "https://repository.example/files/supplement-table.tsv",
                            "license": "cc-by",
                        }
                    ],
                }
            return {}

        with patch("askinsects.sources.extracted_facts._fetch_json_url", side_effect=fake_json):
            supplements = fetch_public_supplement_metadata(
                {
                    "record_id": "openalex:WUNPAYWALL",
                    "doi": "10.1000/aedes.unpaywall",
                    "url": "https://doi.org/10.1000/aedes.unpaywall",
                }
            )

        urls = {str(item["url"]) for item in supplements}
        self.assertIn("https://publisher.example/article/supplement.pdf", urls)
        self.assertIn("https://repository.example/files/supplement-table.tsv", urls)
        self.assertTrue(all(item["source"] == "unpaywall_oa_location" for item in supplements))

    def test_fetch_public_supplement_metadata_does_not_treat_article_ids_as_supplements(self):
        def fake_json(url: str) -> dict[str, object]:
            if "europepmc" in url:
                return {}
            if "api.unpaywall.org" in url:
                return {
                    "best_oa_location": {
                        "url_for_pdf": "https://www.nature.com/articles/s41598-024-63165-x.pdf",
                        "url_for_landing_page": "https://www.nature.com/articles/s41598-024-63165-x",
                    },
                    "oa_locations": [
                        {
                            "url_for_pdf": "https://ars.els-cdn.com/content/image/1-s2.0-S0306456522000201-ga1_lrg.jpg",
                            "license": "cc-by",
                        },
                        {
                            "url_for_pdf": "https://publisher.example/files/S1.pdf",
                            "license": "cc-by",
                        },
                        {
                            "url": "https://publisher.example/files/supplementary-table-s2.csv",
                            "license": "cc-by",
                        },
                    ],
                }
            return {}

        with patch("askinsects.sources.extracted_facts._fetch_json_url", side_effect=fake_json):
            supplements = fetch_public_supplement_metadata(
                {
                    "record_id": "openalex:WUNPAYWALLARTICLE",
                    "doi": "10.1000/aedes.unpaywall.article",
                    "url": "https://doi.org/10.1000/aedes.unpaywall.article",
                }
            )

        urls = {str(item["url"]) for item in supplements}
        self.assertNotIn("https://www.nature.com/articles/s41598-024-63165-x.pdf", urls)
        self.assertNotIn("https://www.nature.com/articles/s41598-024-63165-x", urls)
        self.assertNotIn("https://ars.els-cdn.com/content/image/1-s2.0-S0306456522000201-ga1_lrg.jpg", urls)
        self.assertIn("https://publisher.example/files/S1.pdf", urls)
        self.assertIn("https://publisher.example/files/supplementary-table-s2.csv", urls)

    def test_fetch_public_supplement_metadata_discovers_landing_page_links(self):
        html = b"""
        <html><body>
          <a href="/article/supplementary-table-s1.csv">Supplementary Table S1</a>
          <a href="https://example.org/article/Figure1.jpg">Figure 1</a>
        </body></html>
        """

        def fake_json(url: str) -> dict[str, object]:
            if "europepmc" in url:
                return {}
            return {}

        def fake_bytes(url: str, max_bytes: int) -> bytes:
            self.assertEqual(url, "https://publisher.example/article")
            return html

        with (
            patch("askinsects.sources.extracted_facts._fetch_json_url", side_effect=fake_json),
            patch("askinsects.sources.extracted_facts._fetch_bytes_url", side_effect=fake_bytes),
        ):
            supplements = fetch_public_supplement_metadata(
                {
                    "record_id": "openalex:WLANDING",
                    "doi": "10.1000/aedes.landing",
                    "url": "https://publisher.example/article",
                }
            )

        self.assertEqual(len(supplements), 1)
        self.assertEqual(supplements[0]["source"], "publisher_landing_page")
        self.assertEqual(supplements[0]["url"], "https://publisher.example/article/supplementary-table-s1.csv")

    def test_build_extracted_fact_records_emits_per_paper_supplement_audits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:WNO_SUPP",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti paper with no public supplement metadata",
                        text="Aedes aegypti dengue paper with identifier metadata.",
                        species="Aedes aegypti",
                        url="https://example.org/no-supp",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#WNO_SUPP",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.1234/no.supp"}},
                    )
                ]
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                download_supplements=True,
                fetch_supplement_metadata_fn=lambda request: [],
                fetch_supplement_file_fn=lambda url, max_bytes: b"",
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            audits = [record for record in result.records if record.payload["fact_type"] == "supplement_audit"]
            self.assertEqual(result.supplement_audit_record_count, 2)
            self.assertEqual({record.payload["source_record_id"] for record in audits}, {"openalex:WFACT1", "openalex:WNO_SUPP"})
            by_source = {record.payload["source_record_id"]: record for record in audits}
            self.assertEqual(by_source["openalex:WFACT1"].payload["fields"]["coverage_status"], "supplement_manifest_found_no_supported_table_rows_promoted")
            self.assertEqual(by_source["openalex:WNO_SUPP"].payload["fields"]["coverage_status"], "no_supplement_metadata_found")
            file_gaps = [
                record
                for record in result.records
                if record.payload["fact_type"] == "supplement_file_gap"
            ]
            self.assertEqual(len(file_gaps), 1)
            self.assertEqual(file_gaps[0].payload["fields"]["reason"], "supplement_table_no_rows")
            self.assertEqual(file_gaps[0].payload["fields"]["source_record_id"], "openalex:WFACT1")
            self.assertEqual(file_gaps[0].payload["fields"]["file_type"], "csv")
            self.assertIn("records#openalex:WFACT1", file_gaps[0].provenance.locator)
            self.assertIn("supplement#0", file_gaps[0].provenance.locator)
            self.assertEqual(result.papers_with_supplement_manifest_count, 1)
            self.assertEqual(result.papers_with_promoted_supplement_rows_count, 0)

    def test_build_extracted_fact_records_bounds_supplement_discovery_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:WFACT2",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Second Aedes aegypti supplement metadata paper",
                        text="Second indexed Aedes aegypti paper with supplement identifiers.",
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
                        payload={
                            "ids": {
                                "doi": "10.1234/aedes.fact.2",
                                "pmid": "22345678",
                                "pmcid": "PMC2234567",
                            }
                        },
                    )
                ]
            )
            requests: list[str] = []

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                requests.append(str(request["record_id"]))
                return []

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=1,
            )

            self.assertEqual(len(requests), 1)
            self.assertIn(requests[0], {"openalex:WFACT1", "openalex:WFACT2"})
            self.assertEqual(result.supplement_discovery_record_count, 1)
            self.assertTrue(any(gap["reason"] == "supplement_discovery_record_limit_applied" for gap in result.gaps))

    def test_build_extracted_fact_records_extracts_pubmed_articleids_for_supplement_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:WARTICLEIDS",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti article with PubMed article IDs",
                        text="Aedes aegypti dengue vector competence supplementary data.",
                        species="Aedes aegypti",
                        url="https://example.org/articleids",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#WARTICLEIDS",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={
                            "pubmed": {
                                "match": {
                                    "articleids": [
                                        {"idtype": "pubmed", "value": "41528154"},
                                        {"idtype": "pmcid", "value": "pmc-id: PMC12892943;"},
                                        {"idtype": "doi", "value": "10.1128/mbio.03173-25"},
                                    ]
                                }
                            }
                        },
                    )
                ]
            )
            seen: dict[str, dict[str, object]] = {}

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                seen[str(request["record_id"])] = request
                return []

            build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=10,
            )

            request = seen["openalex:WARTICLEIDS"]
            self.assertEqual(request["pmid"], "41528154")
            self.assertEqual(request["pmcid"], "PMC12892943")
            self.assertEqual(request["doi"], "10.1128/mbio.03173-25")

    def test_build_extracted_fact_records_prioritizes_identifier_rows_for_bounded_supplement_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:A_NOID",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti no identifier row",
                        text="Aedes aegypti supplement mention but no identifiers.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#A_NOID",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={},
                    ),
                    EvidenceRecord(
                        record_id="openalex:Z_ID",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Additional file 1 of Aedes aegypti vector competence table",
                        text="Aedes aegypti supplementary vector competence table.",
                        species="Aedes aegypti",
                        url="10.6084/m9.figshare.31976326.v1",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#Z_ID",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"raw_openalex_work": {"doi": "https://doi.org/10.6084/m9.figshare.31976326.v1"}},
                    ),
                ]
            )
            requests: list[str] = []

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                requests.append(str(request["record_id"]))
                return []

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=1,
            )

            self.assertEqual(requests, ["openalex:Z_ID"])
            self.assertEqual(result.supplement_discovery_record_count, 1)

    def test_build_extracted_fact_records_prioritizes_resistance_rows_for_bounded_supplement_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:Z_GENERIC",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Additional file 1 of Aedes aegypti vector competence table",
                        text="Aedes aegypti supplementary vector competence table.",
                        species="Aedes aegypti",
                        url="https://example.org/generic",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#Z_GENERIC",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.1234/generic", "pmid": "12345678"}},
                    ),
                    EvidenceRecord(
                        record_id="openalex:A_RESISTANCE",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti insecticide resistance and kdr supplementary table",
                        text="Field populations with deltamethrin mortality, V1016G, F1534C, and LC50 evidence.",
                        species="Aedes aegypti",
                        url="https://example.org/resistance",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#A_RESISTANCE",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.1234/resistance", "pmid": "22345678"}},
                    ),
                ]
            )
            requests: list[str] = []

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                requests.append(str(request["record_id"]))
                return []

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=1,
            )

            self.assertEqual(requests, ["openalex:A_RESISTANCE"])
            self.assertEqual(result.supplement_discovery_record_count, 1)

    def test_build_extracted_fact_records_prioritizes_zenodo_resistance_repository_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:Z_GENERIC_RESISTANCE",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti insecticide resistance supplementary table",
                        text="Deltamethrin mortality, V1016G, F1534C, and LC50 evidence.",
                        species="Aedes aegypti",
                        url="https://example.org/resistance",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#Z_GENERIC_RESISTANCE",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.1234/resistance", "pmid": "22345678"}},
                    ),
                    EvidenceRecord(
                        record_id="openalex:A_ZENODO_RESISTANCE",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti insecticide resistance repository dataset",
                        text="Field populations with pyrethroid resistance, knockdown resistance, mortality, and genotype evidence.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.5281/zenodo.19918130",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#A_ZENODO_RESISTANCE",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"raw_openalex_work": {"doi": "https://doi.org/10.5281/zenodo.19918130"}},
                    ),
                ]
            )
            requests: list[str] = []

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                requests.append(str(request["record_id"]))
                return []

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=1,
            )

            self.assertEqual(requests, ["openalex:A_ZENODO_RESISTANCE"])
            self.assertEqual(result.supplement_discovery_record_count, 1)

    def test_build_extracted_fact_records_always_discovers_repository_rows_after_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:Z_GENERIC_RESISTANCE",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti insecticide resistance supplementary table",
                        text="Deltamethrin mortality, V1016G, F1534C, and LC50 evidence.",
                        species="Aedes aegypti",
                        url="https://example.org/resistance",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#Z_GENERIC_RESISTANCE",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.1234/resistance", "pmid": "22345678"}},
                    ),
                    EvidenceRecord(
                        record_id="openalex:A_ZENODO_DATASET",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti repository dataset",
                        text="Aedes aegypti observation dataset.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.5281/zenodo.19918130",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#A_ZENODO_DATASET",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.5281/zenodo.19918130"}},
                    ),
                ]
            )
            requests: list[str] = []

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                requests.append(str(request["record_id"]))
                return []

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=1,
            )

            self.assertEqual(requests, ["openalex:Z_GENERIC_RESISTANCE", "openalex:A_ZENODO_DATASET"])
            self.assertEqual(result.supplement_discovery_record_count, 2)
            self.assertTrue(
                any(
                    gap.get("repository_backed_records_added_after_limit") == 1
                    and gap.get("repository_backed_records_available_after_limit") == 1
                    for gap in result.gaps
                    if gap.get("reason") == "supplement_discovery_record_limit_applied"
                )
            )

    def test_build_extracted_fact_records_bounds_repository_rows_after_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:Z_GENERIC_RESISTANCE",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti insecticide resistance supplementary table",
                        text="Deltamethrin mortality, V1016G, F1534C, and LC50 evidence.",
                        species="Aedes aegypti",
                        url="https://example.org/resistance",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#Z_GENERIC_RESISTANCE",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.1234/resistance", "pmid": "22345678"}},
                    ),
                    EvidenceRecord(
                        record_id="openalex:A_ZENODO_DATASET",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti repository dataset",
                        text="Aedes aegypti observation dataset.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.5281/zenodo.19918130",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#A_ZENODO_DATASET",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.5281/zenodo.19918130"}},
                    ),
                ]
            )
            requests: list[str] = []

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                requests.append(str(request["record_id"]))
                return []

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                max_supplement_discovery_records=1,
                max_repository_supplement_discovery_records=0,
            )

            self.assertEqual(requests, ["openalex:Z_GENERIC_RESISTANCE"])
            self.assertEqual(result.supplement_discovery_record_count, 1)
            self.assertEqual(result.max_repository_supplement_discovery_records, 0)
            gap = next(gap for gap in result.gaps if gap.get("reason") == "supplement_discovery_record_limit_applied")
            self.assertEqual(gap["repository_backed_records_added_after_limit"], 0)
            self.assertEqual(gap["repository_backed_records_available_after_limit"], 1)

    def test_build_extracted_fact_records_skips_generic_bioassay_resistance_table_noise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            payloads: dict[str, bytes] = {
                "https://example.org/aedes-facts/supp-table-1.csv": (
                    "domain,Replicate,Measurement\n"
                    "quality_control,A,9.06\n"
                ).encode("utf-8"),
                "https://example.org/europepmc/attractant.csv": (
                    "domain,Replicate,Measurement\n"
                    "quality_control,B,8.72\n"
                ).encode("utf-8"),
            }

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "title": "Attractant bioassay table",
                        "url": "https://example.org/europepmc/attractant.csv",
                        "file_type": "csv",
                        "source": "europe_pmc",
                    }
                ]

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                return payloads[url]

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                download_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed_resistance = [
                record
                for record in result.records
                if record.payload["fact_type"] == "resistance" and record.payload["confidence"] == "parsed"
            ]
            self.assertEqual(parsed_resistance, [])
            unpromoted_rows = [
                record
                for record in result.records
                if record.payload["fact_type"] == "supplement_table_row"
                and record.payload["confidence"] == "parsed_no_structured_lane_match"
            ]
            self.assertEqual(len(unpromoted_rows), 2)
            self.assertEqual(unpromoted_rows[0].payload["fields"]["table_row"]["Replicate"], "A")
            self.assertEqual(unpromoted_rows[0].payload["fields"]["table_row_index"], 1)
            self.assertIn("raw/extracted_facts/supplements/", unpromoted_rows[0].provenance.locator)
            self.assertIn("row#1", unpromoted_rows[0].provenance.locator)
            self.assertEqual(result.parsed_supplement_row_count, 2)

    def test_build_extracted_fact_records_promotes_true_resistance_table_without_declared_domain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            payloads: dict[str, bytes] = {
                "https://example.org/aedes-facts/supp-table-1.csv": (
                    "Population,Insecticide,Assay,Mortality %,V1016G allele frequency,Country\n"
                    "Brazil field population,deltamethrin,WHO tube bioassay,43,0.72,Brazil\n"
                ).encode("utf-8"),
                "https://example.org/europepmc/resistance.csv": (
                    "Population,Insecticide,Assay,Mortality %,V1016G allele frequency,Country\n"
                    "Brazil field population,deltamethrin,WHO tube bioassay,43,0.72,Brazil\n"
                ).encode("utf-8"),
            }

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "title": "Resistance table",
                        "url": "https://example.org/europepmc/resistance.csv",
                        "file_type": "csv",
                        "source": "europe_pmc",
                    }
                ]

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                return payloads[url]

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                download_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed_resistance = [
                record
                for record in result.records
                if record.payload["fact_type"] == "resistance" and record.payload["confidence"] == "parsed"
            ]
            self.assertEqual(len(parsed_resistance), 2)
            self.assertTrue(all("deltamethrin" in record.text for record in parsed_resistance))
            self.assertTrue(all(record.payload["fields"]["table_row"]["Mortality %"] == "43" for record in parsed_resistance))

    def test_build_extracted_fact_records_promotes_discriminating_concentration_docx_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://ndownloader.figshare.com/files/61896451"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:W7128925281",
                title=(
                    "Toxicity of ivermectin on multiple insecticide-resistant populations of "
                    "Anopheles gambiae sensu lato, Aedes aegypti, and Culex mosquitoes"
                ),
                text="Additional file with discriminating concentration insecticide class rows.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    ["Discriminating concentration s"],
                    ["Insecticide class"],
                    ["Pyrethroids"],
                    ["Deltamethrin"],
                    ["Carbamate"],
                    ["Organochlorine"],
                    ["Organophosphate"],
                ]
            )

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, supplement_url)
                self.assertLessEqual(len(payload), max_bytes)
                return payload

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed_resistance = [
                record
                for record in result.records
                if record.payload["fact_type"] == "resistance" and record.payload["confidence"] == "parsed"
            ]
            values = {
                record.payload["fields"]["table_row"]["Discriminating concentration s"]
                for record in parsed_resistance
            }
            self.assertEqual(result.parsed_supplement_row_count, 6)
            self.assertEqual(len(parsed_resistance), 6)
            self.assertIn("Deltamethrin", values)
            self.assertIn("Pyrethroids", values)
            self.assertIn("Organophosphate", values)
            self.assertTrue(all(record.lane == "resistance" for record in parsed_resistance))
            self.assertTrue(all("raw/extracted_facts/supplements/" in record.provenance.locator for record in parsed_resistance))

    def test_build_extracted_fact_records_parses_supported_supplement_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            payloads: dict[str, bytes] = {
                "https://example.org/aedes-facts/supp-table-1.csv": (
                    "domain,pathogen,infection rate,temperature,tissue,strain\n"
                    "vector competence,dengue virus,80%,28 C,saliva,Rockefeller\n"
                ).encode("utf-8"),
                "https://example.org/europepmc/resistance.tsv": (
                    "domain\tinsecticide\tmortality\tmutation\tcountry\n"
                    "resistance\tpermethrin\t55%\tV1016G\tBrazil\n"
                ).encode("utf-8"),
                "https://example.org/europepmc/behavior.xlsx": make_xlsx_bytes(
                    [
                        ["domain", "assay", "stimulus", "sex", "response rate"],
                        ["behavior", "Y-tube olfactometer", "lactic acid", "female", "62%"],
                    ]
                ),
                "https://example.org/europepmc/ecology.xml": (
                    "<table><tr><th>domain</th><th>habitat</th><th>breeding site</th><th>climate</th></tr>"
                    "<tr><td>ecology</td><td>urban habitat</td><td>water storage container</td><td>rainy season</td></tr></table>"
                ).encode("utf-8"),
                "https://example.org/europepmc/public-health.html": (
                    "<table><tr><th>domain</th><th>cases</th><th>deaths</th><th>serotype</th><th>intervention</th></tr>"
                    "<tr><td>public health</td><td>1234 cases</td><td>5 deaths</td><td>DENV-2</td><td>Wolbachia intervention</td></tr></table>"
                ).encode("utf-8"),
            }

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {"title": "Resistance TSV", "url": "https://example.org/europepmc/resistance.tsv", "file_type": "tsv", "source": "europe_pmc"},
                    {"title": "Behavior XLSX", "url": "https://example.org/europepmc/behavior.xlsx", "file_type": "xlsx", "source": "europe_pmc"},
                    {"title": "Ecology XML", "url": "https://example.org/europepmc/ecology.xml", "file_type": "xml", "source": "pmc_oa"},
                    {"title": "Public health HTML", "url": "https://example.org/europepmc/public-health.html", "file_type": "html", "source": "pmc_oa"},
                ]

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                payload = payloads[url]
                self.assertLessEqual(len(payload), max_bytes)
                return payload

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                download_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            parsed_lanes = {record.lane for record in parsed}
            self.assertEqual(result.parsed_supplement_file_count, 5)
            self.assertEqual(result.parsed_supplement_row_count, 5)
            self.assertIn("vector_competence", parsed_lanes)
            self.assertIn("resistance", parsed_lanes)
            self.assertIn("behavior", parsed_lanes)
            self.assertIn("ecology", parsed_lanes)
            self.assertIn("public_health", parsed_lanes)
            vector = next(record for record in parsed if record.lane == "vector_competence")
            self.assertEqual(vector.payload["extraction_method"], "deterministic_supplement_table_row_extract")
            self.assertEqual(vector.payload["supplement"]["url"], "https://example.org/aedes-facts/supp-table-1.csv")
            self.assertEqual(vector.payload["fields"]["table_row"]["infection rate"], "80%")
            self.assertEqual(vector.payload["fields"]["table_row_index"], 1)
            self.assertIn("raw/extracted_facts/supplements/", vector.provenance.locator)
            self.assertIn("row#1", vector.provenance.locator)
            self.assertTrue((artifact_dir / "raw" / "extracted_facts" / "supplements").exists())

    def test_build_extracted_fact_records_parses_docx_supplement_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            payload = make_docx_bytes(
                [
                    ["domain", "pathogen", "infection rate", "temperature", "tissue", "strain"],
                    ["vector competence", "dengue virus", "83%", "28 C", "saliva", "Rockefeller"],
                ]
            )

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "title": "Vector competence DOCX supplement",
                        "url": "https://example.org/aedes-facts/vector-competence.docx",
                        "file_type": "docx",
                        "source": "figshare",
                    }
                ]

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, "https://example.org/aedes-facts/vector-competence.docx")
                return payload

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                download_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertTrue(any(record.lane == "vector_competence" for record in parsed))
            vector = next(record for record in parsed if record.lane == "vector_competence")
            self.assertEqual(vector.payload["fields"]["table_row"]["infection rate"], "83%")
            self.assertIn(".docx", vector.provenance.locator)

    def test_build_extracted_fact_records_sniffs_semicolon_csv_supplement_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://example.org/aedes-facts/resistance-semicolon.csv"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WSEMICOLON",
                title=(
                    "A genomic amplification affecting a carboxylesterase gene cluster "
                    "confers organophosphate resistance in the mosquito Aedes aegypti"
                ),
                text="Aedes aegypti insecticide resistance mortality supplement.",
                supplement_url=supplement_url,
            )
            payload = (
                "lines;insecticide;repetition;nb_dead;nb_alive;total;mortality_rate\n"
                "G5_Mala;deltamethrin;1;12;4;16;75\n"
            ).encode("utf-8")

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].lane, "resistance")
            table_row = parsed[0].payload["fields"]["table_row"]
            self.assertEqual(table_row["lines"], "G5_Mala")
            self.assertEqual(table_row["insecticide"], "deltamethrin")
            self.assertEqual(table_row["mortality_rate"], "75")

    def test_build_extracted_fact_records_promotes_japanese_vector_surveillance_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://www.forth.go.jp/ihr/fragment2/index.html"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WJAPANVECTOR",
                title=(
                    "Genetic analysis of Aedes aegypti captured at two international airports "
                    "serving to the Greater Tokyo Area"
                ),
                text="Aedes aegypti airport introduction and quarantine vector surveillance report.",
                supplement_url=supplement_url,
            )
            payload = (
                "<table><tr><th>更新年月日</th><th>情報内容</th></tr>"
                "<tr><td>2025年9月29日</td>"
                "<td>2024年　検疫所ベクターサーベイランスデータ報告書［12.9MB］</td></tr>"
                "</table>"
            ).encode("utf-8")

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].lane, "public_health")
            self.assertIn("openalex:WJAPANVECTOR", parsed[0].text)
            self.assertIn(supplement_url, parsed[0].text)
            table_row = parsed[0].payload["fields"]["table_row"]
            self.assertEqual(table_row["更新年月日"], "2025年9月29日")
            self.assertIn("検疫所ベクターサーベイランスデータ報告書", table_row["情報内容"])

    def test_build_extracted_fact_records_promotes_zikv_infected_sample_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://example.org/aedes-facts/zikv-samples.docx"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WZIKV",
                title=(
                    "Mosquito host background impacts microbiome-Zika virus interactions "
                    "in field- and laboratory-reared Aedes aegypti"
                ),
                text="Aedes aegypti ZIKV infection sample metadata supplement.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    ["Sample ID", "Reads", "Type", "ZIKV", "Location", "Sequencing Batch"],
                    ["Austin1-4_S4", "R1.fastq.gz R2.fastq.gz", "Field", "Infected", "Austin", "Batch_1"],
                ]
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].lane, "vector_competence")
            self.assertIn("zikv", parsed[0].payload["fields"]["pathogen"])
            self.assertIn("infected", parsed[0].payload["fields"]["infection"])
            self.assertEqual(parsed[0].payload["fields"]["table_row"]["ZIKV"], "Infected")

    def test_build_extracted_fact_records_promotes_aedes_abundance_trap_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://example.org/aedes-facts/abundance.docx"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WABUNDANCE",
                title=(
                    "Environmental correlates of Aedes aegypti abundance in San Bernardino County: "
                    "an ecological modeling study"
                ),
                text="Aedes aegypti monthly abundance and trap summary supplement.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    [
                        "Month",
                        "total Ae. aegypti caught",
                        "mean per trap",
                        "median per trap",
                        "total number of traps",
                        "proportion of traps with no mosquitoes",
                    ],
                    ["04", "61", "0.13", "0", "484", "0.93"],
                ]
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].lane, "ecology")
            self.assertIn("total ae. aegypti caught", parsed[0].payload["fields"]["abundance"])
            self.assertIn("trap", parsed[0].payload["fields"]["sampling"])
            self.assertEqual(parsed[0].payload["fields"]["table_row"]["total Ae. aegypti caught"], "61")

    def test_build_extracted_fact_records_default_bytes_allow_medium_docx_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://example.org/aedes-facts/medium-abundance.docx"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WMEDIUM",
                title="Environmental correlates of Aedes aegypti abundance: an ecological modeling study",
                text="Aedes aegypti monthly abundance and trap summary supplement.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    ["Month", "total Ae. aegypti caught", "mean per trap", "total number of traps"],
                    ["05", "283", "0.37", "755"],
                ]
            )

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, supplement_url)
                self.assertEqual(max_bytes, DEFAULT_MAX_SUPPLEMENT_BYTES)
                self.assertGreaterEqual(max_bytes, 6_500_000)
                return payload

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].lane, "ecology")

    def test_build_extracted_fact_records_promotes_larvicide_mixture_control_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://ndownloader.figshare.com/files/61983853"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:W7130372072",
                title=(
                    "Ecotoxicological evidence of safe and effective low-dose mixture of "
                    "spinosad-pyriproxyfen application under semi-field conditions"
                ),
                text="Aedes aegypti larvae exposed to a larvicide mixture in semi-field conditions.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    [
                        "Day",
                        "Mixture Mean (%)",
                        "Mixture 95% CI (Lower-Upper)",
                        "Control Mean (%)",
                        "Control 95% CI (Lower-Upper)",
                        "Enzyme",
                        "p -value",
                    ],
                    ["1", "100.0", "100.0-100.0", "63.8", "43.6-83.9", "α-esterase", "0.0006"],
                ]
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(len(parsed), 1)
            self.assertTrue(all(record.lane == "public_health" for record in parsed))
            self.assertIn("mixture mean", parsed[0].payload["fields"]["intervention"])
            self.assertIn("mean (%)", parsed[0].payload["fields"]["effect_metric"])
            self.assertEqual(parsed[0].payload["fields"]["table_row"]["Mixture Mean (%)"], "100.0")
            self.assertIn("α-esterase", parsed[0].payload["fields"]["biochemical_response"])
            self.assertEqual(parsed[0].payload["fields"]["table_row"]["p -value"], "0.0006")

    def test_build_extracted_fact_records_keeps_prisma_checklists_as_audit_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://example.org/aedes-facts/prisma.docx"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WPRISMA",
                title="Repellent effects of insecticides against Aedes aegypti: a systematic review",
                text="Aedes aegypti repellent systematic review supplement.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    ["Section / Topic", "Item Number", "Checklist Item", "Reported on Page/Section in Manuscript"],
                    ["Title", "1", "Identify the report as a systematic review.", "The title states systematic review."],
                ]
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            audits = [record for record in result.records if record.payload["fact_type"] == "supplement_audit"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(parsed, [])
            self.assertEqual(audits[0].payload["fields"]["coverage_status"], "supplement_rows_parsed_no_structured_lane_match")

    def test_build_extracted_fact_records_does_not_promote_pathogen_title_only_collection_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            supplement_url = "https://example.org/aedes-facts/collections.docx"
            write_single_supplement_fixture(
                artifact_dir,
                record_id="openalex:WCOLLECTIONS",
                title=(
                    "Control and mitigation of dengue and Zika virus transmission in a hospital in Recife, "
                    "Brazil: an integrated control program against Aedes aegypti"
                ),
                text="Aedes aegypti collection summary supplement.",
                supplement_url=supplement_url,
            )
            payload = make_docx_bytes(
                [
                    ["Month of Collection", "Sample Name", "Species", "Number of females", "Capture Station"],
                    ["Aug/18", "Sample 1", "A. aegypti", "10", "General"],
                ]
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                download_supplements=True,
                fetch_supplement_file_fn=lambda url, max_bytes: payload,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            parsed = [record for record in result.records if record.payload["confidence"] == "parsed"]
            self.assertEqual(result.parsed_supplement_row_count, 1)
            self.assertEqual(parsed, [])

    def test_build_extracted_fact_records_extracts_text_supplement_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:WTEXTSUPP",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti vector competence repository supplement",
                        text="Aedes aegypti supplemental methods and results.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.5281/zenodo.12345",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#WTEXTSUPP",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.5281/zenodo.12345"}},
                    )
                ]
            )

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "title": "Vector competence text supplement",
                        "url": "https://zenodo.org/api/records/12345/files/vector-competence.txt/content",
                        "file_type": "text/plain",
                        "source": "zenodo",
                    }
                ]

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, "https://zenodo.org/api/records/12345/files/vector-competence.txt/content")
                return (
                    "Aedes aegypti vector competence assay. "
                    "Dengue virus infection rate was 81% in midgut tissue and transmission was detected in saliva."
                ).encode("utf-8")

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                discover_supplements=True,
                download_supplements=True,
                fetch_supplement_metadata_fn=fake_metadata,
                fetch_supplement_file_fn=fake_file_fetch,
                max_supplement_files=10,
                max_supplement_bytes=100_000,
            )

            vector = next(record for record in result.records if record.payload["fact_type"] == "vector_competence")
            self.assertEqual(result.downloaded_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_row_count, 0)
            self.assertEqual(vector.payload["confidence"], "candidate")
            self.assertEqual(vector.payload["extraction_method"], "deterministic_supplement_text_extract")
            self.assertIn("raw/extracted_facts/supplements/", vector.provenance.locator)
            self.assertIn(".txt", vector.provenance.locator)
            self.assertFalse(any(gap.get("reason") == "unsupported_supplement_type" for gap in result.gaps))

    def test_build_extracted_fact_records_extracts_pdf_supplement_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:WPDFSUPP",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti resistance PDF supplement",
                        text="Aedes aegypti supplemental resistance report.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.5281/zenodo.67890",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#WPDFSUPP",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.5281/zenodo.67890"}},
                    )
                ]
            )

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "title": "Resistance PDF supplement",
                        "url": "https://zenodo.org/api/records/67890/files/resistance.pdf/content",
                        "file_type": "application/pdf",
                        "source": "zenodo",
                    }
                ]

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                self.assertEqual(url, "https://zenodo.org/api/records/67890/files/resistance.pdf/content")
                return b"%PDF fixture bytes"

            with patch(
                "askinsects.sources.extracted_facts._parse_pdf_text",
                return_value=(
                    "Aedes aegypti insecticide resistance bioassay. "
                    "Deltamethrin mortality was 43% and kdr mutation V1016G was detected."
                ),
            ):
                result = build_extracted_fact_records(
                    artifact_dir,
                    retrieved_at="2026-05-24T00:00:00Z",
                    discover_supplements=True,
                    download_supplements=True,
                    fetch_supplement_metadata_fn=fake_metadata,
                    fetch_supplement_file_fn=fake_file_fetch,
                    max_supplement_files=10,
                    max_supplement_bytes=100_000,
                )

            resistance = next(record for record in result.records if record.payload["fact_type"] == "resistance")
            self.assertEqual(result.downloaded_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_file_count, 1)
            self.assertEqual(result.parsed_supplement_row_count, 0)
            self.assertEqual(resistance.payload["confidence"], "candidate")
            self.assertEqual(resistance.payload["extraction_method"], "deterministic_supplement_text_extract")
            self.assertIn("raw/extracted_facts/supplements/", resistance.provenance.locator)
            self.assertIn(".pdf", resistance.provenance.locator)
            self.assertFalse(any(gap.get("reason") == "unsupported_supplement_type" for gap in result.gaps))

    def test_build_extracted_fact_records_bounds_pdf_supplement_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="openalex:WPDFLIMIT",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti resistance PDF supplement collection",
                        text="Aedes aegypti supplemental resistance reports.",
                        species="Aedes aegypti",
                        url="https://doi.org/10.5281/zenodo.98765",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="raw/literature/page.json#WPDFLIMIT",
                            retrieved_at="2026-05-24T00:00:00Z",
                        ),
                        payload={"ids": {"doi": "10.5281/zenodo.98765"}},
                    )
                ]
            )

            def fake_metadata(request: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "title": "Resistance PDF supplement one",
                        "url": "https://zenodo.org/api/records/98765/files/resistance-1.pdf/content",
                        "file_type": "application/pdf",
                        "source": "zenodo",
                    },
                    {
                        "title": "Resistance PDF supplement two",
                        "url": "https://zenodo.org/api/records/98765/files/resistance-2.pdf/content",
                        "file_type": "application/pdf",
                        "source": "zenodo",
                    },
                ]

            fetched_urls: list[str] = []

            def fake_file_fetch(url: str, max_bytes: int) -> bytes:
                fetched_urls.append(url)
                return b"%PDF fixture bytes"

            with patch(
                "askinsects.sources.extracted_facts._parse_pdf_text",
                return_value=(
                    "Aedes aegypti insecticide resistance bioassay. "
                    "Deltamethrin mortality was 43% and kdr mutation V1016G was detected."
                ),
            ):
                result = build_extracted_fact_records(
                    artifact_dir,
                    retrieved_at="2026-05-24T00:00:00Z",
                    discover_supplements=True,
                    download_supplements=True,
                    fetch_supplement_metadata_fn=fake_metadata,
                    fetch_supplement_file_fn=fake_file_fetch,
                    max_supplement_files=10,
                    max_supplement_bytes=100_000,
                    max_pdf_supplement_files=1,
                )

            self.assertEqual(len(fetched_urls), 1)
            self.assertEqual(result.downloaded_supplement_file_count, 1)
            self.assertEqual(result.parsed_pdf_supplement_file_count, 1)
            self.assertEqual(result.skipped_pdf_supplement_file_count, 1)
            self.assertTrue(any(gap.get("reason") == "pdf_supplement_file_limit_applied" for gap in result.gaps))

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

    def test_build_extracted_fact_records_preserves_hyphenated_term_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            paper = EvidenceRecord(
                record_id="openalex:WFACT-HYPHEN",
                lane="literature",
                source="aedes_literature_openalex",
                title="Aedes aegypti vector-competence table",
                text="Aedes aegypti dengue assay.",
                species="Aedes aegypti",
                url="https://example.org/aedes-hyphen",
                media_url=None,
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/literature/page.json#WFACT-HYPHEN",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="open metadata",
                    source_url="https://example.org/aedes-hyphen",
                ),
                payload={},
            )
            unit = FullTextUnit(
                unit_id="openalex:WFACT-HYPHEN:fulltext:0",
                record_id="openalex:WFACT-HYPHEN",
                source="aedes_literature_openalex",
                unit_index=0,
                text="Aedes aegypti dengue vector-competence infection-rate 40% after blood-meal exposure.",
                url="https://example.org/aedes-hyphen/fulltext",
                license="CC-BY",
                provenance=Provenance(
                    source_id="aedes_literature_openalex",
                    locator="raw/fulltext/WFACT-HYPHEN.txt#chunk/0",
                    retrieved_at="2026-05-24T00:00:00Z",
                    license="CC-BY",
                    source_url="https://example.org/aedes-hyphen/fulltext",
                ),
            )
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_records_and_fulltext_units(
                [paper],
                [unit],
            )

            result = build_extracted_fact_records(
                artifact_dir,
                retrieved_at="2026-05-24T00:00:00Z",
                max_fulltext_units=10,
            )

            self.assertTrue(
                any(
                    record.payload["source_record_id"] == "openalex:WFACT-HYPHEN"
                    and record.payload["fact_type"] == "vector_competence"
                    for record in result.records
                )
            )

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

            html_records = [record for record in result.records if record.payload.get("source_record_id") == "openalex:WHTML"]
            self.assertEqual([record.payload["fact_type"] for record in html_records], ["supplement_audit"])

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
