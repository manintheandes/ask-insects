from pathlib import Path

from askinsects.sources.elicit_discovery import fetch_elicit_discovery_records


def _fake_fetch(papers_by_query):
    def _fetch(query, *, max_results, min_year):
        return {"papers": papers_by_query.get(query, [])}
    return _fetch


def test_builds_candidate_record_with_payload(tmp_path):
    papers = {"q1": [{
        "title": "Repellency of X against Drosophila suzukii",
        "authors": ["A. Author"], "year": 2023, "venue": "Pest Manag Sci",
        "doi": "10.1000/abc", "pmid": "123", "elicitId": "E1",
        "citedByCount": 4, "abstract": "We test repellency."}]}
    result = fetch_elicit_discovery_records(
        species="drosophila_suzukii", queries=["q1"], raw_dir=tmp_path,
        retrieved_at="2026-06-07T00:00:00Z",
        fetch_json=_fake_fetch(papers),
        existing_doi_lookup=lambda dois: set())
    assert result.source_id == "drosophila_suzukii_elicit_discovery"
    assert len(result.records) == 1
    rec = result.records[0]
    assert rec.lane == "literature"
    assert rec.url == "10.1000/abc"
    assert rec.species == "Drosophila suzukii"
    assert rec.payload["confidence_band"] == "elicit_search_candidate"
    assert rec.payload["depth_outcome"] == "supplement_discovery_not_run"
    assert rec.payload["discovery"]["query"] == "q1"
    assert rec.payload["doi"] == "10.1000/abc"
    assert result.returned_count == 1 and result.new_count == 1


def test_drops_dois_already_in_hosted(tmp_path):
    papers = {"q1": [
        {"title": "New paper", "doi": "10.1/new", "elicitId": "E1"},
        {"title": "Old paper", "doi": "10.1/old", "elicitId": "E2"}]}
    result = fetch_elicit_discovery_records(
        species="aedes_aegypti", queries=["q1"], raw_dir=tmp_path,
        retrieved_at="t", fetch_json=_fake_fetch(papers),
        existing_doi_lookup=lambda dois: {"10.1/old"})
    assert result.new_count == 1
    assert result.dedup_dropped == 1
    assert result.records[0].url == "10.1/new"


def test_dedups_same_doi_across_queries(tmp_path):
    paper = {"title": "Dup", "doi": "10.1/dup", "elicitId": "E1"}
    papers = {"q1": [paper], "q2": [paper]}
    result = fetch_elicit_discovery_records(
        species="aedes_aegypti", queries=["q1", "q2"], raw_dir=tmp_path,
        retrieved_at="t", fetch_json=_fake_fetch(papers),
        existing_doi_lookup=lambda dois: set())
    assert result.new_count == 1
    assert result.records[0].payload["discovery"]["all_queries"] == ["q1", "q2"]


def test_fetch_failure_records_gap(tmp_path):
    def _boom(query, *, max_results, min_year):
        raise RuntimeError("403 plan")
    result = fetch_elicit_discovery_records(
        species="aedes_aegypti", queries=["q1"], raw_dir=tmp_path,
        retrieved_at="t", fetch_json=_boom, existing_doi_lookup=lambda d: set())
    assert result.records == []
    assert result.gaps and result.gaps[0]["reason"].startswith("elicit_fetch_failed:")


def test_default_fetch_builds_request(monkeypatch):
    import askinsects.sources.elicit_discovery as ed
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"papers": []}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["ua"] = req.headers.get("User-agent")
        captured["body"] = req.data
        return FakeResp()

    monkeypatch.setattr(ed, "urlopen", fake_urlopen)
    out = ed.default_fetch_json("q", max_results=5, min_year=2020, api_key="elk_live_X")
    assert captured["url"] == ed.ELICIT_SEARCH_URL
    assert captured["auth"] == "Bearer elk_live_X"
    # urllib's default Python-urllib UA is blocked (403) by Elicit's edge; require a real UA.
    assert captured["ua"] and "python-urllib" not in captured["ua"].lower()
    assert b'"q"' in captured["body"]
    assert out == {"papers": []}


def test_existing_lookup_uses_or_not_in(monkeypatch):
    import askinsects.sources.elicit_discovery as ed
    calls = []

    class R:
        returncode = 0
        stdout = '{"rows":[{"url":"10.1/a"}]}'
        stderr = ""

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return R()

    monkeypatch.setattr(ed.subprocess, "run", fake_run)
    found = ed.default_existing_doi_lookup({"10.1/a", "10.1/b"})
    sql = calls[0][2]
    # OR-of-equalities stays on the index; IN(...) and LIKE full-scan and time out on hosted.
    assert " or " in sql
    assert " in (" not in sql.lower()
    assert "like" not in sql.lower()
    assert found == {"10.1/a"}
