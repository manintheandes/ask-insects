from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.extracted_facts import (
    EXTRACTED_FACTS_SOURCE_ID,
    build_extracted_fact_records,
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

    def test_build_extracted_fact_records_skips_generic_bioassay_resistance_table_noise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_extracted_facts_fixture(artifact_dir)
            payloads: dict[str, bytes] = {
                "https://example.org/aedes-facts/supp-table-1.csv": (
                    "Attractant,Assay,Area (%)\n"
                    "Isoamyl acetate,Cage bioassay,9.06\n"
                ).encode("utf-8"),
                "https://example.org/europepmc/attractant.csv": (
                    "Attractant,Assay,Area (%)\n"
                    "Isoamyl acetate,Cage bioassay,9.06\n"
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
