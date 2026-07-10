from __future__ import annotations

import json
from pathlib import Path
import re
from unittest.mock import patch

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature_depth_profiles import LITERATURE_DEPTH_PROFILES
from askinsects.server import dispatch_request
from scripts.ingest_literature_depth import ingest_profile


def test_ingest_profile_writes_source_grade_status_and_receipt(tmp_path: Path):
    index = SourceIndex(tmp_path / "source_index.sqlite")
    index.initialize()
    index.upsert_records(
        [
            EvidenceRecord(
                record_id="mosquito_repellent_literature:doi:10.1000/depth",
                lane="literature",
                source="mosquito_repellent_literature",
                title="Non-contact spatial DEET repellency assay",
                text=(
                    "Adult female Aedes aegypti showed 80% landing inhibition with 10% DEET "
                    "in a non-contact chamber after 30 minutes."
                ),
                species="Culicidae",
                url="https://doi.org/10.1000/depth",
                media_url=None,
                provenance=Provenance(
                    source_id="mosquito_repellent_literature",
                    locator="fixture.json#0",
                    retrieved_at="2026-07-01T00:00:00Z",
                ),
                payload={"doi": "10.1000/depth"},
            )
        ]
    )

    profile = LITERATURE_DEPTH_PROFILES["mosquito_repellent_literature_extracted_facts"]
    result = ingest_profile(
        profile,
        artifact_dir=tmp_path,
        retrieved_at=None,
        max_fulltext_units=5,
        discover_supplements=False,
        download_supplements=False,
        max_supplement_discovery_records=10,
        max_repository_supplement_discovery_records=10,
        max_supplement_files=5,
        max_supplement_bytes=1_000_000,
        max_pdf_supplement_files=1,
    )

    assert result["ok"] is True
    assert result["retrieved_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result["retrieved_at"])
    assert result["record_count"] >= 2

    for filename in ("source_status.json", "source_receipt.json"):
        payload = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert profile.source_id in payload["sources"]
        source = payload[profile.source_id]
        assert source["source"] == profile.source_id
        assert source["input_source"] == profile.input_literature_source_id
        assert source["retrieved_at"] == result["retrieved_at"]
        assert source["record_count"] == result["record_count"]
        assert source["refresh_failed"] is False


def test_hosted_route_runs_a_bounded_literature_depth_profile(tmp_path: Path):
    with (
        patch(
            "scripts.ingest_literature_depth.ingest_literature_depth",
            return_value={
                "ok": True,
                "results": [{"source": "mosquito_repellent_literature_extracted_facts"}],
            },
        ) as ingest,
        patch(
            "askinsects.server.rewrite_artifact_references",
            side_effect=lambda _staging, _artifact_dir, result, **_kwargs: result,
        ) as rewrite,
    ):
        response = dispatch_request(
            "POST",
            "/ingest/literature-depth",
            {
                "profile": "mosquito_repellent_literature_extracted_facts",
                "max_fulltext_units": 25,
                "discover_supplements": True,
                "max_supplement_files": 7,
            },
            headers={"Authorization": "Bearer secret"},
            artifact_dir=tmp_path,
            token="secret",
        )

    assert response.status == 200
    assert response.payload["ok"] is True
    ingest.assert_called_once()
    kwargs = ingest.call_args.kwargs
    assert kwargs["artifact_dir"] != tmp_path
    assert kwargs["artifact_dir"].name == f".{tmp_path.name}.literature-depth-staging"
    assert kwargs["profile"] == "mosquito_repellent_literature_extracted_facts"
    assert kwargs["max_fulltext_units"] == 25
    assert kwargs["discover_supplements"] is True
    assert kwargs["max_supplement_files"] == 7
    assert rewrite.call_args.kwargs["source"] == (
        "mosquito_repellent_literature_extracted_facts"
    )
    assert response.payload["staged"] is True
    assert response.payload["activated_artifact_dir"] == str(tmp_path)


def test_hosted_route_rejects_string_boolean_options(tmp_path: Path):
    with patch("scripts.ingest_literature_depth.ingest_literature_depth") as ingest:
        response = dispatch_request(
            "POST",
            "/ingest/literature-depth",
            {
                "profile": "mosquito_repellent_literature_extracted_facts",
                "download_supplements": "false",
            },
            headers={"Authorization": "Bearer secret"},
            artifact_dir=tmp_path,
            token="secret",
        )

    assert response.status == 400
    assert response.payload["error"] == "download_supplements must be a boolean"
    ingest.assert_not_called()
