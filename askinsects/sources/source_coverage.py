from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from pathlib import Path

from askinsects.records import EvidenceRecord, Provenance


SOURCE_COVERAGE_SOURCE_ID = "aedes_source_coverage"
DEFAULT_COVERAGE_LEDGER = Path("config/mosquito-intelligence-coverage.json")
PUBLIC_REPO_BLOB_URL = "https://github.com/manintheandes/ask-insects/blob/main"
SOURCE_ID_BY_TAXON = {
    "aedes aegypti": "aedes_source_coverage",
    "anopheles": "anopheles_source_coverage",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    safe = re.sub(r"[^a-z0-9_.:-]+", "_", text).strip("_")
    return safe or "unknown"


def _list_text(values: object, *, limit: int = 6) -> str:
    if not isinstance(values, list) or not values:
        return "none recorded"
    rendered = [str(value) for value in values[:limit]]
    suffix = f"; plus {len(values) - limit} more" if len(values) > limit else ""
    return "; ".join(rendered) + suffix


def _public_ledger_url(path: Path) -> str:
    return f"{PUBLIC_REPO_BLOB_URL}/{path.as_posix()}"


def load_coverage_ledger(path: Path = DEFAULT_COVERAGE_LEDGER) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("coverage ledger must be a JSON object")
    domains = payload.get("domains")
    if not isinstance(domains, list):
        raise ValueError("coverage ledger must contain a domains list")
    return payload


def source_id_for_coverage_ledger(ledger: dict[str, object]) -> str:
    scope = ledger.get("scope") if isinstance(ledger.get("scope"), dict) else {}
    configured = scope.get("source_id")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    primary_taxon = str(scope.get("primary_taxon") or "Aedes aegypti").strip().lower()
    for taxon, source_id in SOURCE_ID_BY_TAXON.items():
        if primary_taxon == taxon or primary_taxon.startswith(f"{taxon} "):
            return source_id
    return SOURCE_COVERAGE_SOURCE_ID


def build_source_coverage_records(
    coverage_path: Path = DEFAULT_COVERAGE_LEDGER,
    *,
    retrieved_at: str | None = None,
) -> list[EvidenceRecord]:
    retrieved = retrieved_at or utc_now()
    ledger = load_coverage_ledger(coverage_path)
    source_id = source_id_for_coverage_ledger(ledger)
    record_prefix = source_id
    public_ledger_url = _public_ledger_url(coverage_path)
    domains = [domain for domain in ledger["domains"] if isinstance(domain, dict)]
    scope = ledger.get("scope") if isinstance(ledger.get("scope"), dict) else {}
    # Project-scope descriptor, not a per-row species label: this is the coverage
    # ledger's declared primary taxon for the whole intelligence project (Aedes aegypti).
    primary_taxon = str(scope.get("primary_taxon") or "Aedes aegypti")
    strategy = str(scope.get("strategy") or f"Build comprehensive {primary_taxon} mosquito intelligence.")
    status_counts: dict[str, int] = {}
    for domain in domains:
        status = str(domain.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    records: list[EvidenceRecord] = [
        EvidenceRecord(
            record_id=f"{record_prefix}:overview",
            lane="source_coverage",
            source=source_id,
            title=f"{primary_taxon} source coverage overview",
            text=(
                f"Ask Insects source coverage overview for {primary_taxon}. Strategy: {strategy} "
                f"Tracked domains: {len(domains)}. Status counts: "
                + "; ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
                + ". Missing coverage questions should inspect the per-domain and coverage-gap records from this lane."
            ),
            species=primary_taxon,
            url=public_ledger_url,
            media_url=None,
            provenance=Provenance(
                source_id=source_id,
                locator=f"{coverage_path.as_posix()}#scope",
                retrieved_at=retrieved,
                license="Repository coverage ledger",
                source_url=public_ledger_url,
            ),
            payload={
                "atom_type": "source_coverage_overview",
                "primary_taxon": primary_taxon,
                "strategy": strategy,
                "domain_count": len(domains),
                "status_counts": status_counts,
                "ledger_path": coverage_path.as_posix(),
            },
        )
    ]

    for index, domain in enumerate(domains):
        domain_id = str(domain.get("id") or f"domain_{index + 1}")
        status = str(domain.get("status") or "unknown")
        current_sources = domain.get("current_sources") if isinstance(domain.get("current_sources"), list) else []
        required_next_sources = domain.get("required_next_sources") if isinstance(domain.get("required_next_sources"), list) else []
        target_state = str(domain.get("target_state") or "")
        current_gates = domain.get("current_gates") if isinstance(domain.get("current_gates"), dict) else {}
        gate_text = "; ".join(f"{key}={value}" for key, value in current_gates.items()) or "no gates recorded"
        records.append(
            EvidenceRecord(
                record_id=f"{record_prefix}:domain:{_safe_id(domain_id)}",
                lane="source_coverage",
                source=source_id,
                title=f"{primary_taxon} coverage status: {domain_id}",
                text=(
                    f"{primary_taxon} {domain_id} coverage status: {status}. Target: {target_state} "
                    f"Current source lanes: {_list_text(current_sources)}. Source-contract gates: {gate_text}. "
                    f"Missing or next required coverage: {_list_text(required_next_sources)}."
                ),
                species=primary_taxon,
                url=public_ledger_url,
                media_url=None,
                provenance=Provenance(
                    source_id=source_id,
                    locator=f"{coverage_path.as_posix()}#domains/{index}",
                    retrieved_at=retrieved,
                    license="Repository coverage ledger",
                    source_url=public_ledger_url,
                ),
                payload={
                    "atom_type": "source_coverage_domain",
                    "domain": domain_id,
                    "priority": domain.get("priority"),
                    "status": status,
                    "target_state": target_state,
                    "current_sources": current_sources,
                    "current_gates": current_gates,
                    "current_evidence": domain.get("current_evidence") if isinstance(domain.get("current_evidence"), list) else [],
                    "required_next_sources": required_next_sources,
                    "completion_evidence": domain.get("completion_evidence") if isinstance(domain.get("completion_evidence"), list) else [],
                    "ledger_path": coverage_path.as_posix(),
                },
            )
        )
        for gap_index, required_source in enumerate(required_next_sources):
            records.append(
                EvidenceRecord(
                    record_id=f"{record_prefix}:gap:{_safe_id(domain_id)}:{gap_index + 1}",
                    lane="source_coverage",
                    source=source_id,
                    title=f"{primary_taxon} missing coverage: {domain_id}",
                    text=(
                        f"Missing {primary_taxon} {domain_id} source coverage: {required_source}. "
                        f"Domain status: {status}. This is a coverage-ledger gap, not a completed source lane."
                    ),
                    species=primary_taxon,
                    url=public_ledger_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=source_id,
                        locator=f"{coverage_path.as_posix()}#domains/{index}/required_next_sources/{gap_index}",
                        retrieved_at=retrieved,
                        license="Repository coverage ledger",
                        source_url=public_ledger_url,
                    ),
                    payload={
                        "atom_type": "source_coverage_gap",
                        "domain": domain_id,
                        "status": status,
                        "required_next_source": str(required_source),
                        "ledger_path": coverage_path.as_posix(),
                    },
                )
            )
    return records
