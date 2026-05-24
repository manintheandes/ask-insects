import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit, LITERATURE_SOURCE_ID


def openalex_payload(work_id: str, *, doi: str | None = None, pmid: str | None = None, pdf_url: str | None = None) -> dict[str, object]:
    ids: dict[str, str] = {"openalex": f"https://openalex.org/{work_id}"}
    if doi:
        ids["doi"] = f"https://doi.org/{doi}"
    if pmid:
        ids["pmid"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
    return {
        "raw_openalex_work": {
            "id": f"https://openalex.org/{work_id}",
            "display_name": f"Aedes aegypti paper {work_id}",
            "ids": ids,
            "doi": f"https://doi.org/{doi}" if doi else None,
            "best_oa_location": {"pdf_url": pdf_url} if pdf_url else None,
        },
        "inclusion_paths": ["abstract"],
        "pubmed": None,
        "unpaywall": None,
    }


def seed_record(artifact_dir: Path, record_id: str, payload: dict[str, object]) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id=record_id,
                lane="literature",
                source=LITERATURE_SOURCE_ID,
                title=str(payload["raw_openalex_work"]["display_name"]),
                text="Aedes aegypti literature record",
                species="Aedes aegypti",
                url="https://example.org/work",
                media_url=None,
                provenance=Provenance(
                    source_id=LITERATURE_SOURCE_ID,
                    locator=f"raw/literature/{record_id}.json",
                    retrieved_at="2026-05-23T00:00:00Z",
                ),
                payload=payload,
            )
        ]
    )


class LiteratureEnrichmentTests(unittest.TestCase):
    def read_payload(self, artifact_dir: Path, record_id: str) -> dict[str, object]:
        conn = sqlite3.connect(artifact_dir / "source_index.sqlite")
        try:
            row = conn.execute("select payload_json from record_payloads where record_id=?", (record_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        return json.loads(row[0])

    def test_pubmed_batches_openalex_pmids_and_updates_payloads(self) -> None:
        from scripts.enrich_literature_index import EnrichmentConfig, run_enrichment

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            seed_record(artifact_dir, "openalex:W1", openalex_payload("W1", doi="10.1/a", pmid="111"))
            seed_record(artifact_dir, "openalex:W2", openalex_payload("W2", doi="10.1/b", pmid="222"))
            seed_record(artifact_dir, "openalex:W3", openalex_payload("W3", doi="10.1/c"))
            calls: list[str] = []

            def fake_fetch_json(url: str) -> dict[str, object]:
                calls.append(url)
                self.assertIn("esummary.fcgi", url)
                self.assertIn("tool=ask-insects", url)
                self.assertIn("email=test%40example.com", url)
                return {
                    "result": {
                        "uids": ["111", "222"],
                        "111": {"uid": "111", "title": "one"},
                        "222": {"uid": "222", "title": "two"},
                    }
                }

            summary = run_enrichment(
                EnrichmentConfig(
                    artifact_dir=artifact_dir,
                    email="test@example.com",
                    pubmed=True,
                    unpaywall=False,
                    fulltext=False,
                    pubmed_batch_size=2,
                    ncbi_delay_seconds=0,
                ),
                fetch_json=fake_fetch_json,
            )

            self.assertEqual(len(calls), 1)
            self.assertIn("id=111%2C222", calls[0])
            self.assertEqual(summary["pubmed"]["enriched"], 2)
            self.assertEqual(summary["pubmed"]["missing_pmid"], 1)
            self.assertEqual(self.read_payload(artifact_dir, "openalex:W1")["pubmed"]["match"]["uid"], "111")
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual([gap["reason"] for gap in gaps], ["pubmed_missing_pmid"])

    def test_unpaywall_fulltext_direct_pdf_success_creates_fulltext_units(self) -> None:
        from scripts.enrich_literature_index import EnrichmentConfig, run_enrichment

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            seed_record(artifact_dir, "openalex:WPDF", openalex_payload("WPDF", doi="10.1/pdf", pmid="333"))

            def fake_fetch_json(url: str) -> dict[str, object]:
                self.assertIn("api.unpaywall.org", url)
                return {
                    "doi": "10.1/pdf",
                    "is_oa": True,
                    "best_oa_location": {
                        "url_for_pdf": "https://example.org/legal.pdf",
                        "license": "cc-by",
                    },
                }

            def fake_fetch_bytes(url: str) -> tuple[bytes, str]:
                self.assertEqual(url, "https://example.org/legal.pdf")
                return b"%PDF fake", "application/pdf"

            def fake_pdf_to_text(_pdf_path: Path) -> str:
                return "Aedes aegypti legal open full text from a PDF."

            summary = run_enrichment(
                EnrichmentConfig(
                    artifact_dir=artifact_dir,
                    email="test@example.com",
                    pubmed=False,
                    unpaywall=True,
                    fulltext=True,
                    delay_seconds=0,
                ),
                fetch_json=fake_fetch_json,
                fetch_bytes=fake_fetch_bytes,
                pdf_to_text=fake_pdf_to_text,
            )

            self.assertEqual(summary["unpaywall"]["queried"], 1)
            self.assertEqual(summary["fulltext"]["records"], 1)
            self.assertGreaterEqual(summary["fulltext"]["units"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select record_id, text, license from literature_fulltext_units"
            )
            self.assertEqual(rows[0]["record_id"], "openalex:WPDF")
            self.assertIn("legal open full text", rows[0]["text"])
            self.assertEqual(rows[0]["license"], "cc-by")
            self.assertEqual(self.read_payload(artifact_dir, "openalex:WPDF")["unpaywall"]["doi"], "10.1/pdf")
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            receipt = json.loads((artifact_dir / "source_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(status["literature"]["fulltext_record_count"], 1)
            self.assertEqual(status["literature"]["fulltext_unit_count"], rows.__len__())
            self.assertEqual(receipt["literature"]["fulltext_record_count"], 1)
            self.assertEqual(receipt["literature"]["payload_store"], "record_payloads.payload_json")

    def test_resume_skips_already_enriched_rows(self) -> None:
        from scripts.enrich_literature_index import EnrichmentConfig, run_enrichment

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            payload = openalex_payload("WRESUME", doi="10.1/resume", pmid="444")
            payload["pubmed"] = {"match": {"uid": "444"}}
            payload["unpaywall"] = {
                "is_oa": True,
                "best_oa_location": {"url_for_pdf": "https://example.org/resume.pdf"},
            }
            seed_record(artifact_dir, "openalex:WRESUME", payload)
            SourceIndex(artifact_dir / "source_index.sqlite").upsert_fulltext_units(
                [
                    FullTextUnit(
                        unit_id="openalex:WRESUME:fulltext:0",
                        record_id="openalex:WRESUME",
                        source=LITERATURE_SOURCE_ID,
                        unit_index=0,
                        text="already extracted Aedes aegypti full text",
                        url="https://example.org/resume.pdf",
                        license="cc-by",
                        provenance=Provenance(
                            source_id=LITERATURE_SOURCE_ID,
                            locator="openalex:WRESUME#fulltext/0",
                            retrieved_at="2026-05-23T00:00:00Z",
                        ),
                    )
                ]
            )

            def fail_fetch_json(url: str) -> dict[str, object]:
                raise AssertionError(f"resume should not fetch JSON: {url}")

            summary = run_enrichment(
                EnrichmentConfig(
                    artifact_dir=artifact_dir,
                    email="test@example.com",
                    pubmed=True,
                    unpaywall=True,
                    fulltext=True,
                    resume=True,
                    ncbi_delay_seconds=0,
                    delay_seconds=0,
                ),
                fetch_json=fail_fetch_json,
                fetch_bytes=lambda url: (_ for _ in ()).throw(AssertionError(f"resume should not fetch full text: {url}")),
            )

            self.assertEqual(summary["pubmed"]["skipped"], 1)
            self.assertEqual(summary["unpaywall"]["skipped"], 1)
            self.assertEqual(summary["fulltext"]["skipped"], 1)

    def test_record_id_shards_are_disjoint_and_complete(self) -> None:
        from scripts.enrich_literature_index import EnrichmentConfig, run_enrichment

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            for index in range(12):
                record_id = f"openalex:WSHARD{index}"
                payload = openalex_payload(f"WSHARD{index}", pdf_url=f"https://example.org/{index}.pdf")
                seed_record(artifact_dir, record_id, payload)

            seen_by_shard: list[set[str]] = []
            for shard_index in range(3):
                fetched: set[str] = set()

                def fake_fetch_bytes(url: str) -> tuple[bytes, str]:
                    fetched.add(url.rsplit("/", 1)[-1].removesuffix(".pdf"))
                    return b"%PDF fake", "application/pdf"

                summary = run_enrichment(
                    EnrichmentConfig(
                        artifact_dir=artifact_dir,
                        pubmed=False,
                        unpaywall=False,
                        fulltext=True,
                        delay_seconds=0,
                        record_id_shard_count=3,
                        record_id_shard_index=shard_index,
                    ),
                    fetch_bytes=fake_fetch_bytes,
                    pdf_to_text=lambda _path: "Aedes aegypti direct full text.",
                )
                self.assertEqual(summary["records_seen"], len(fetched))
                seen_by_shard.append(fetched)

            self.assertEqual(set().union(*seen_by_shard), {str(index) for index in range(12)})
            self.assertFalse(seen_by_shard[0] & seen_by_shard[1])
            self.assertFalse(seen_by_shard[0] & seen_by_shard[2])
            self.assertFalse(seen_by_shard[1] & seen_by_shard[2])

    def test_gap_append_deduplicates_resume_safe_rows(self) -> None:
        from scripts.enrich_literature_index import _append_gaps

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            gap = {
                "source": LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "missing_doi",
                "record_id": "openalex:W1",
                "species": "Aedes aegypti",
                "retrieved_at": "2026-05-23T00:00:00Z",
                "locator": "record_payloads#openalex:W1",
            }
            _append_gaps(artifact_dir, [gap])
            _append_gaps(artifact_dir, [gap])
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(gaps, [gap])


if __name__ == "__main__":
    unittest.main()
