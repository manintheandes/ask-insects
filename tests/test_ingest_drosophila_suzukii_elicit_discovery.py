import importlib.util
import json
from pathlib import Path


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCRIPT = Path("scripts/ingest_drosophila_suzukii_elicit_discovery.py")


def test_ingest_writes_records_and_receipt(tmp_path):
    mod = _load("ingest_swd_elicit", SCRIPT)

    def fake_fetch(query, *, max_results, min_year):
        return {"papers": [{"title": f"P {query}", "doi": f"10.1/{abs(hash(query)) % 9}", "elicitId": "E"}]}

    result = mod.ingest(
        artifact_dir=tmp_path, fetch_json=fake_fetch,
        existing_doi_lookup=lambda d: set(), retrieved_at="2026-06-07T00:00:00Z")
    assert result["ok"] is True
    assert result["source"] == "drosophila_suzukii_elicit_discovery"
    assert result["new_count"] >= 1
    status = json.loads((tmp_path / "source_status.json").read_text())
    assert "drosophila_suzukii_elicit_discovery" in json.dumps(status)


def test_ingest_all_fail_preserves(tmp_path):
    mod = _load("ingest_swd_elicit2", SCRIPT)

    def boom(query, *, max_results, min_year):
        raise RuntimeError("429")

    result = mod.ingest(artifact_dir=tmp_path, fetch_json=boom,
                        existing_doi_lookup=lambda d: set(), retrieved_at="t")
    assert result["ok"] is False
    assert result["refresh_failed"] is True
