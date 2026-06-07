import importlib.util
from pathlib import Path


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCRIPT = Path("scripts/ingest_aedes_aegypti_elicit_discovery.py")


def test_aedes_ingest_writes_records(tmp_path):
    mod = _load("ingest_aedes_elicit", SCRIPT)

    def fake_fetch(query, *, max_results, min_year):
        return {"papers": [{"title": f"A {query}", "doi": f"10.2/{abs(hash(query)) % 9}", "elicitId": "E"}]}

    result = mod.ingest(artifact_dir=tmp_path, fetch_json=fake_fetch,
                        existing_doi_lookup=lambda d: set(), retrieved_at="2026-06-07T00:00:00Z")
    assert result["ok"] is True
    assert result["source"] == "aedes_aegypti_elicit_discovery"
    assert result["new_count"] >= 1
