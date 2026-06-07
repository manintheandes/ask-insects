from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.extracted_facts import build_extracted_fact_records
from askinsects.sources.elicit_extracted_facts import (
    DROSOPHILA_SUZUKII_ELICIT_EXTRACTED_FACTS_PROFILE,
    ELICIT_EXTRACTED_FACTS_PROFILES,
)


def _seed(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    rec = EvidenceRecord(
        record_id="drosophila_suzukii_elicit_discovery:10.1/x",
        lane="literature",
        source="drosophila_suzukii_elicit_discovery",
        title="Oviposition choice assay reveals avoidance behaviour in Drosophila suzukii",
        text="Oviposition choice assay reveals strong avoidance behaviour and host preference in Drosophila suzukii to a repellent volatile.",
        species="Drosophila suzukii",
        url="10.1/x",
        media_url=None,
        provenance=Provenance(source_id="drosophila_suzukii_elicit_discovery", locator="raw#0", retrieved_at="t"),
        payload={"doi": "10.1/x", "confidence_band": "elicit_search_candidate"},
    )
    index.replace_source_records("drosophila_suzukii_elicit_discovery", [rec])


def test_profiles_point_at_elicit_inputs():
    ids = {p.input_literature_source_id for p in ELICIT_EXTRACTED_FACTS_PROFILES}
    assert ids == {"drosophila_suzukii_elicit_discovery", "aedes_aegypti_elicit_discovery"}
    outs = {p.source_id for p in ELICIT_EXTRACTED_FACTS_PROFILES}
    assert outs == {"drosophila_suzukii_elicit_extracted_facts", "aedes_aegypti_elicit_extracted_facts"}


def test_miner_produces_depth_records_for_elicit_paper(tmp_path):
    _seed(tmp_path)
    result = build_extracted_fact_records(
        tmp_path,
        retrieved_at="2026-06-07T00:00:00Z",
        max_fulltext_units=5,
        discover_supplements=False,
        download_supplements=False,
        profile=DROSOPHILA_SUZUKII_ELICIT_EXTRACTED_FACTS_PROFILE,
    )
    assert result.records, "miner should produce at least one depth record for the seeded paper"
    assert all(r.source == "drosophila_suzukii_elicit_extracted_facts" for r in result.records)
    # the seeded paper is the source_record for the produced facts
    srids = {(r.payload or {}).get("source_record_id") for r in result.records}
    assert "drosophila_suzukii_elicit_discovery:10.1/x" in srids
