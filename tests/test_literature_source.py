from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, unquote, urlparse

from askinsects.sources.literature import (
    LITERATURE_SOURCE_ID,
    abstract_from_inverted_index,
    fetch_literature_records,
    fulltext_units_for_record,
)


def openalex_work(
    work_id: str,
    *,
    title: str,
    abstract_terms: dict[str, list[int]],
    doi: str | None = None,
) -> dict[str, object]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "display_name": title,
        "publication_date": "2024-03-01",
        "type": "article",
        "abstract_inverted_index": abstract_terms,
        "authorships": [{"author": {"display_name": "Ada Researcher"}}],
        "primary_location": {"source": {"display_name": "Journal of Mosquito Work"}},
        "open_access": {"is_oa": bool(doi), "oa_url": "https://example.org/open.pdf" if doi else None},
        "ids": {"openalex": f"https://openalex.org/{work_id}", "doi": doi},
        "primary_topic": {
            "id": "https://openalex.org/T-AEDES",
            "display_name": "Aedes aegypti vector biology",
        },
        "topics": [{"id": "https://openalex.org/T-AEDES", "display_name": "Aedes aegypti vector biology"}],
        "keywords": [{"display_name": "Aedes aegypti"}],
    }


class LiteratureSourceTests(unittest.TestCase):
    def create_tmpdir(self) -> str:
        return tempfile.mkdtemp(prefix="askinsects-literature-test-")

    def test_reconstructs_openalex_abstract(self) -> None:
        abstract = abstract_from_inverted_index({"Aedes": [0], "aegypti": [1], "vector": [2], "biology": [3]})
        self.assertEqual(abstract, "Aedes aegypti vector biology")

    def test_fulltext_units_for_record_splits_cleaned_text(self) -> None:
        units = fulltext_units_for_record(
            record_id="openalex:W1",
            text=" Aedes aegypti  " + ("x" * 4100),
            url="https://example.org/fulltext",
            license="cc-by",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertEqual(len(units), 2)
        self.assertEqual(units[0].unit_id, "openalex:W1:fulltext:0")
        self.assertEqual(units[0].unit_index, 0)
        self.assertLessEqual(len(units[0].text), 4000)
        self.assertEqual(units[0].provenance.source_id, LITERATURE_SOURCE_ID)
        self.assertEqual(units[0].provenance.source_url, "https://example.org/fulltext")
        self.assertEqual(units[0].provenance.license, "cc-by")

    def test_fetches_cursor_pages_and_normalizes_literature_records(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "/topics" in url:
                return {
                    "results": [
                        {
                            "id": "https://openalex.org/T-AEDES",
                            "display_name": "Aedes aegypti vector biology",
                            "description": "Aedes aegypti mosquito papers",
                            "keywords": ["Aedes aegypti"],
                        }
                    ]
                }
            if "cursor=%2A" in url or "cursor=*" in url:
                return {
                    "meta": {"count": 2, "next_cursor": "page-2"},
                    "results": [
                        openalex_work(
                            "W1",
                            title="Aedes aegypti control",
                            abstract_terms={"Aedes": [0], "aegypti": [1], "control": [2]},
                            doi="https://doi.org/10.1000/aedes1",
                        )
                    ],
                }
            return {
                "meta": {"count": 2, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W2",
                        title="Dengue vector study",
                        abstract_terms={"material": [0], "topic": [1]},
                        doi=None,
                    )
                ],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=1,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            fetch_text=lambda url: "legal open full text for Aedes aegypti",
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertEqual(result.source_id, LITERATURE_SOURCE_ID)
        self.assertEqual(len(result.records), 2)
        self.assertTrue(any(record.record_id == "openalex:W1" for record in result.records))
        self.assertTrue(any(record.lane == "literature" for record in result.records))
        self.assertGreaterEqual(len(result.raw_artifacts), 2)
        self.assertIn("title", result.inclusion_path_counts)
        self.assertIn("abstract", result.inclusion_path_counts)
        self.assertTrue(calls)

    def test_openalex_works_request_sorts_by_publication_date_desc(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            return {"meta": {"count": 0, "next_cursor": None}, "results": []}

        fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=False,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertEqual(len(calls), 1)
        works_url = calls[0]
        self.assertIn("/works?", works_url)
        self.assertEqual(parse_qs(urlparse(works_url).query).get("sort"), ["publication_date:desc"])

    def test_openalex_search_mode_uses_search_param_and_marks_candidate(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "/topics" in url:
                return {"results": []}
            query = parse_qs(urlparse(url).query)
            self.assertEqual(query.get("search"), ["Drosophila suzukii management"])
            filter_value = unquote(query.get("filter", [""])[0])
            self.assertNotIn("title_and_abstract.search", filter_value)
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W10",
                        title="Fruit pest management without visible species name",
                        abstract_terms={"management": [0], "soft": [1], "fruit": [2]},
                        doi="https://doi.org/10.1000/swd-candidate",
                    )
                ],
            }

        result = fetch_literature_records(
            species="Drosophila suzukii",
            from_date="2020-01-01",
            to_date="2026-06-06",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            retrieved_at="2026-06-06T00:00:00Z",
            skip_pubmed=True,
            search_terms=[
                {
                    "term": "Drosophila suzukii management",
                    "mode": "search",
                    "topic_group": "management",
                    "confidence": "openalex_search_candidate",
                }
            ],
        )

        self.assertEqual([record.record_id for record in result.records], ["openalex:W10"])
        record = result.records[0]
        self.assertIn("openalex_search_candidate", record.payload["inclusion_paths"])
        self.assertEqual(record.payload["openalex_search_mode"], "search")
        self.assertEqual(record.payload["openalex_topic_group"], "management")
        self.assertEqual(record.payload["openalex_candidate_status"], "openalex_search_candidate")

    def test_records_closed_full_text_gap(self) -> None:
        def fake_fetch_json(url: str) -> dict[str, object]:
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W3",
                        title="Aedes aegypti closed paper",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi=None,
                    )
                ],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            retrieved_at="2026-05-23T00:00:00Z",
        )

        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("missing_doi", reasons)
        self.assertIn("openalex_topic_search_empty", reasons)

    def test_enriches_with_unpaywall_and_pubmed(self) -> None:
        def fake_fetch_json(url: str) -> dict[str, object]:
            if "api.unpaywall.org" in url:
                return {
                    "doi": "10.1000/aedes1",
                    "is_oa": True,
                    "best_oa_location": {
                        "url_for_pdf": "https://example.org/aedes.pdf",
                        "license": "cc-by",
                    },
                }
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["123"]}}
            if "esummary.fcgi" in url:
                return {
                    "result": {
                        "uids": ["123"],
                        "123": {
                            "uid": "123",
                            "title": "Aedes aegypti open paper",
                            "elocationid": "doi: 10.1000/aedes1",
                        },
                    }
                }
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W4",
                        title="Aedes aegypti open paper",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi="https://doi.org/10.1000/aedes1",
                    )
                ],
            }

        def fake_fetch_text(url: str) -> str:
            if url == "https://example.org/aedes.pdf":
                return "Aedes aegypti legal open full text"
            raise AssertionError(f"unexpected full-text URL: {url}")

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            fetch_text=fake_fetch_text,
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertEqual(result.unpaywall_queried_count, 1)
        self.assertEqual(result.open_fulltext_count, 1)
        self.assertEqual(len(result.fulltext_units), 1)
        self.assertEqual(result.fulltext_units[0].license, "cc-by")
        self.assertIsNotNone(result.records[0].payload)
        self.assertIn("unpaywall", result.records[0].payload or {})
        self.assertIn("pubmed", result.records[0].payload or {})

    def test_doi_missing_work_uses_title_pubmed_lookup_and_keeps_gap(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "api.unpaywall.org" in url:
                raise AssertionError(f"unexpected Unpaywall URL for missing DOI: {url}")
            if "esearch.fcgi" in url:
                self.assertIn("term=Aedes+aegypti+title+only+paper%5BTitle%5D", url)
                return {"esearchresult": {"idlist": ["456"]}}
            if "esummary.fcgi" in url:
                self.assertIn("id=456", url)
                return {
                    "result": {
                        "uids": ["456"],
                        "456": {
                            "uid": "456",
                            "title": "Aedes aegypti title only paper",
                            "elocationid": "",
                        },
                    }
                }
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W5",
                        title="Aedes aegypti title only paper",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi=None,
                    )
                ],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertTrue(any("esearch.fcgi" in call for call in calls))
        self.assertIsNotNone(result.records[0].payload)
        self.assertIsNotNone((result.records[0].payload or {}).get("pubmed"))
        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("missing_doi", reasons)

    def test_unpaywall_landing_page_only_is_gap_not_fulltext(self) -> None:
        fetch_text_calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            if "api.unpaywall.org" in url:
                return {
                    "doi": "10.1000/landing",
                    "is_oa": True,
                    "best_oa_location": {
                        "url_for_landing_page": "https://example.org/article",
                        "license": "cc-by",
                    },
                }
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": []}}
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W6",
                        title="Aedes aegypti landing page paper",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi="https://doi.org/10.1000/landing",
                    )
                ],
            }

        def fake_fetch_text(url: str) -> str:
            fetch_text_calls.append(url)
            raise AssertionError(f"landing page should not be fetched as full text: {url}")

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            fetch_text=fake_fetch_text,
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertEqual(result.fulltext_units, [])
        self.assertEqual(fetch_text_calls, [])
        reasons = {gap["reason"] for gap in result.gaps}
        self.assertIn("fulltext_landing_page_only", reasons)

    def test_pubmed_esearch_uses_retmax_and_matches_later_summary(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "api.unpaywall.org" in url:
                return {"doi": "10.1000/aedes-later", "is_oa": False, "best_oa_location": None}
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["111", "222"]}}
            if "esummary.fcgi" in url:
                ids = parse_qs(urlparse(url).query).get("id", [""])[0].split(",")
                result: dict[str, object] = {"uids": ids}
                if "111" in ids:
                    result["111"] = {
                        "uid": "111",
                        "title": "Unrelated paper",
                        "elocationid": "doi: 10.1000/unrelated",
                    }
                if "222" in ids:
                    result["222"] = {
                        "uid": "222",
                        "title": "Aedes aegypti later PubMed match",
                        "elocationid": "doi: 10.1000/aedes-later",
                    }
                return {"result": result}
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W7",
                        title="Aedes aegypti later PubMed match",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi="https://doi.org/10.1000/aedes-later",
                    )
                ],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        esearch_url = next(call for call in calls if "esearch.fcgi" in call)
        self.assertEqual(parse_qs(urlparse(esearch_url).query).get("retmax"), ["5"])
        pubmed = (result.records[0].payload or {}).get("pubmed")
        self.assertIsNotNone(pubmed)
        self.assertEqual((pubmed or {}).get("match", {}).get("uid"), "222")

    def test_pubmed_fetch_failure_keeps_openalex_record_and_records_gap(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "api.unpaywall.org" in url:
                return {"doi": "10.1000/aedes-rate", "is_oa": False, "best_oa_location": None}
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["999"]}}
            if "esummary.fcgi" in url:
                raise RuntimeError("HTTP Error 429: Too Many Requests")
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W8",
                        title="Aedes aegypti rate limited PubMed paper",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi="https://doi.org/10.1000/aedes-rate",
                    )
                ],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
        )

        self.assertTrue(any("esearch.fcgi" in call for call in calls))
        self.assertTrue(any("esummary.fcgi" in call for call in calls))
        self.assertEqual([record.record_id for record in result.records], ["openalex:W8"])
        self.assertIsNone((result.records[0].payload or {}).get("pubmed"))

        pubmed_gaps = [gap for gap in result.gaps if gap.get("reason") == "pubmed_fetch_failed"]
        self.assertEqual(len(pubmed_gaps), 1)
        gap = pubmed_gaps[0]
        self.assertEqual(gap["source"], LITERATURE_SOURCE_ID)
        self.assertEqual(gap["lane"], "literature")
        self.assertEqual(gap["record_id"], "openalex:W8")
        self.assertEqual(gap["retrieved_at"], "2026-05-23T00:00:00Z")
        self.assertIn("W8", str(gap["locator"]))
        self.assertEqual(gap["species"], "Aedes aegypti")
        self.assertIn("HTTP Error 429", str(gap["error"]))

    def test_skip_pubmed_keeps_openalex_record_and_records_structured_gap(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> dict[str, object]:
            calls.append(url)
            if "esearch.fcgi" in url or "esummary.fcgi" in url:
                raise AssertionError(f"unexpected PubMed URL when skip_pubmed=True: {url}")
            if "api.unpaywall.org" in url:
                return {"doi": "10.1000/aedes-skip", "is_oa": False, "best_oa_location": None}
            if "/topics" in url:
                return {"results": []}
            return {
                "meta": {"count": 1, "next_cursor": None},
                "results": [
                    openalex_work(
                        "W9",
                        title="Aedes aegypti PubMed skipped paper",
                        abstract_terms={"Aedes": [0], "aegypti": [1]},
                        doi="https://doi.org/10.1000/aedes-skip",
                    )
                ],
            }

        result = fetch_literature_records(
            species="Aedes aegypti",
            from_date="2020-01-01",
            to_date="2026-05-23",
            work_type="article",
            include_topic_discovery=True,
            raw_dir=Path(self.create_tmpdir()) / "raw",
            page_size=25,
            delay_seconds=0,
            fetch_json=fake_fetch_json,
            unpaywall_email="test@example.com",
            retrieved_at="2026-05-23T00:00:00Z",
            skip_pubmed=True,
        )

        self.assertFalse(any("esearch.fcgi" in call or "esummary.fcgi" in call for call in calls))
        self.assertEqual([record.record_id for record in result.records], ["openalex:W9"])
        self.assertTrue((result.records[0].payload or {}).get("skip_pubmed"))
        self.assertEqual(result.pubmed_skipped_count, 1)

        pubmed_gaps = [gap for gap in result.gaps if gap.get("reason") == "pubmed_skipped"]
        self.assertEqual(len(pubmed_gaps), 1)
        gap = pubmed_gaps[0]
        self.assertEqual(gap["source"], LITERATURE_SOURCE_ID)
        self.assertEqual(gap["lane"], "literature")
        self.assertEqual(gap["record_id"], "openalex:W9")
        self.assertEqual(gap["retrieved_at"], "2026-05-23T00:00:00Z")
        self.assertIn("W9", str(gap["locator"]))
        self.assertEqual(gap["species"], "Aedes aegypti")


if __name__ == "__main__":
    unittest.main()
