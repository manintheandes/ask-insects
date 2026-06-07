from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.extracted_facts import build_extracted_fact_records
from askinsects.sources.literature_depth_profiles import LITERATURE_DEPTH_PROFILES


def test_registry_wiring():
    expected = {
        "mosquito_repellent_literature_extracted_facts": ("mosquito_repellent_literature", "culicidae"),
        "mosquito_repellent_external_discovery_extracted_facts": ("mosquito_repellent_external_discovery", "culicidae"),
        "aedes_crossref_literature_audit_extracted_facts": ("aedes_crossref_literature_audit", "aedes aegypti"),
        "aedes_olfaction_literature_extracted_facts": ("aedes_olfaction_literature", "aedes aegypti"),
        "drosophila_suzukii_pubmed_literature_extracted_facts": ("drosophila_suzukii_pubmed_literature", "drosophila suzukii"),
    }
    assert set(LITERATURE_DEPTH_PROFILES) == set(expected)
    for out, (inp, sp) in expected.items():
        prof = LITERATURE_DEPTH_PROFILES[out]
        assert prof.input_literature_source_id == inp
        assert prof.species_name.lower() == sp


def test_miner_runs_for_a_culicidae_lane(tmp_path):
    index = SourceIndex(tmp_path / "source_index.sqlite")
    index.initialize()
    rec = EvidenceRecord(
        record_id="mosquito_repellent_literature:10.9/y",
        lane="literature",
        source="mosquito_repellent_literature",
        title="Spatial repellent reduces mosquito landing and biting behavior",
        text="A spatial repellent assay shows reduced landing and host-seeking behavior with high mortality at the diagnostic dose.",
        species="Culicidae",
        url="10.9/y",
        media_url=None,
        provenance=Provenance(source_id="mosquito_repellent_literature", locator="raw#0", retrieved_at="t"),
        payload={"doi": "10.9/y"},
    )
    index.replace_source_records("mosquito_repellent_literature", [rec])
    result = build_extracted_fact_records(
        tmp_path,
        retrieved_at="2026-06-07T00:00:00Z",
        max_fulltext_units=5,
        discover_supplements=False,
        download_supplements=False,
        profile=LITERATURE_DEPTH_PROFILES["mosquito_repellent_literature_extracted_facts"],
    )
    assert result.records
    assert all(r.source == "mosquito_repellent_literature_extracted_facts" for r in result.records)
    srids = {(r.payload or {}).get("source_record_id") for r in result.records}
    assert "mosquito_repellent_literature:10.9/y" in srids
