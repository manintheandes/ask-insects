from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID = "drosophila_suzukii_jki_drosomon_trap_captures"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
DATASET_ID = "openagrar_mods_00041381"
DATA_EUROPA_URL = "https://data.europa.eu/api/hub/search/datasets/openagrar_mods_00041381"
OPENAGRAR_LANDING_URL = "https://www.openagrar.de/receive/openagrar_mods_00041381"
CAPTURES_CSV_URL = "https://www.openagrar.de/servlets/MCRFileNodeServlet/openagrar_derivate_00016480/captures_data.csv"
PARAMETER_DESCRIPTION_URL = "https://www.openagrar.de/servlets/MCRFileNodeServlet/openagrar_derivate_00016482/parameter_description.pdf"
ARTICLE_DOI = "10.3390/insects9040125"
LICENSE = "CC-BY-4.0"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class FetchBody:
    body: bytes
    content_type: str
    status: int


@dataclass(frozen=True)
class DrosophilaSuzukiiJkiDrosomonTrapCapturesResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    file_count: int
    parsed_trap_row_count: int


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _default_fetch_body(url: str) -> FetchBody:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/pdf,*/*"})
    with urlopen(request, timeout=90) as response:
        return FetchBody(
            body=response.read(),
            content_type=str(response.headers.get("content-type") or ""),
            status=int(getattr(response, "status", 200)),
        )


def _write_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_bytes(raw_dir: Path, filename: str, payload: bytes) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_bytes(payload)
    return path


def _clean(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", _clean(value)).strip("_") or "unknown"


def _localized(payload: dict[str, object], key: str, *, language: str = "en") -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return _clean(value.get(language) or value.get("de") or next(iter(value.values()), ""))
    return _clean(value)


def _first_access_url(distribution: dict[str, object]) -> str:
    urls = distribution.get("access_url")
    if isinstance(urls, list) and urls:
        return str(urls[0])
    if isinstance(urls, str):
        return urls
    return ""


def _license_label(distribution: dict[str, object]) -> str:
    license_payload = distribution.get("license")
    if isinstance(license_payload, dict):
        return _clean(license_payload.get("label") or license_payload.get("id") or license_payload.get("resource"))
    return _clean(license_payload) or LICENSE


def _extract_count(description: str, pattern: str) -> int | None:
    match = re.search(pattern, description, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _reported_counts(description: str) -> dict[str, int | None]:
    return {
        "trap_count_reported": _extract_count(description, r"lists\s+([\d,]+)\s+traps"),
        "deployment_count_reported": _extract_count(description, r"contains\s+([\d,]+)\s+records"),
        "trap_days_reported": _extract_count(description, r"total\s+of\s+([\d,]+)\s+days"),
        "adult_captures_reported": _extract_count(description, r"(?:captured|recorded)\s+([\d,]+)\s+adult"),
    }


def _record(
    *,
    record_id: str,
    title: str,
    text: str,
    raw_path: Path,
    locator_suffix: str,
    retrieved_at: str,
    url: str | None,
    source_url: str | None,
    payload: dict[str, object],
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="ecology",
        source=DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#{locator_suffix}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=source_url or url,
        ),
        payload=payload,
    )


def _gap_dict(reason: str, *, locator: str, retrieved_at: str, source_url: str | None, details: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "source": DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
        "species": SPECIES,
        "reason": reason,
        "locator": locator,
        "retrieved_at": retrieved_at,
        "source_url": source_url,
        **(details or {}),
    }


def _gap_record(
    *,
    reason: str,
    title: str,
    text: str,
    raw_path: Path,
    locator_suffix: str,
    retrieved_at: str,
    source_url: str | None,
    extra: dict[str, object] | None = None,
) -> EvidenceRecord:
    return _record(
        record_id=f"swd_jki_drosomon_trap_captures:gap:{_safe_id(reason)}",
        title=title,
        text=text,
        raw_path=raw_path,
        locator_suffix=locator_suffix,
        retrieved_at=retrieved_at,
        url=OPENAGRAR_LANDING_URL,
        source_url=source_url,
        payload={
            "atom_type": "source_gap",
            "reason": reason,
            "dataset_id": DATASET_ID,
            "article_doi": ARTICLE_DOI,
            **(extra or {}),
        },
    )


def _dataset_record(dataset: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    title = _localized(dataset, "title")
    description = _localized(dataset, "description")
    counts = _reported_counts(description)
    text = (
        f"JKI DrosoMon trap-capture dataset for {SPECIES} ({COMMON_NAME}) in southwest Germany. "
        f"The registry description says the monitoring ran from 2011 to February 2018, used traps near JKI institutes, "
        f"recorded trap coordinates with handheld GPS, and used apple-cider-vinegar bait. "
        f"Reported scale: {counts['trap_count_reported'] or 'unknown'} traps, "
        f"{counts['deployment_count_reported'] or 'unknown'} trap-deployment records, "
        f"{counts['trap_days_reported'] or 'unknown'} trap-days, and "
        f"{counts['adult_captures_reported'] or 'unknown'} captured adult D. suzukii. "
        f"Related article DOI: {ARTICLE_DOI}. Title: {title}."
    )
    return _record(
        record_id=f"swd_jki_drosomon_trap_captures:dataset:{DATASET_ID}",
        title=f"JKI DrosoMon SWD trap-capture dataset {DATASET_ID}",
        text=text,
        raw_path=raw_path,
        locator_suffix="result",
        retrieved_at=retrieved_at,
        url=OPENAGRAR_LANDING_URL,
        source_url=DATA_EUROPA_URL,
        payload={
            "atom_type": "jki_drosomon_trap_dataset",
            "dataset_id": DATASET_ID,
            "article_doi": ARTICLE_DOI,
            "title": title,
            "description": description,
            "geography": "southwest Germany",
            "monitoring_start_year": 2011,
            "monitoring_end": "2018-02",
            "bait": "unfiltered apple cider vinegar diluted with water",
            "habitat_context": "semi-natural habitats, mainly hedges with wild host plants near institutes",
            "license": LICENSE,
            "data_europa_url": DATA_EUROPA_URL,
            "openagrar_landing_url": OPENAGRAR_LANDING_URL,
            **counts,
        },
    )


def _file_manifest_record(
    distribution: dict[str, object],
    *,
    raw_path: Path,
    retrieved_at: str,
    index: int,
) -> EvidenceRecord:
    access_url = _first_access_url(distribution)
    distribution_id = _clean(distribution.get("id")) or str(index)
    media_type = _clean(distribution.get("media_type"))
    fmt = distribution.get("format") if isinstance(distribution.get("format"), dict) else {}
    format_label = _clean(fmt.get("label") if isinstance(fmt, dict) else "")
    license_label = _license_label(distribution)
    return _record(
        record_id=f"swd_jki_drosomon_trap_captures:file:{_safe_id(distribution_id)}",
        title="JKI DrosoMon SWD captures_data.csv file manifest",
        text=(
            f"File manifest for the JKI DrosoMon {SPECIES} trap-capture table. "
            f"Distribution id: {distribution_id}. Format: {format_label or media_type or 'unknown'}. "
            f"Access URL: {access_url or 'not supplied'}. License: {license_label}."
        ),
        raw_path=raw_path,
        locator_suffix=f"result/distributions/{index}",
        retrieved_at=retrieved_at,
        url=OPENAGRAR_LANDING_URL,
        source_url=access_url or DATA_EUROPA_URL,
        payload={
            "atom_type": "jki_drosomon_file_manifest",
            "dataset_id": DATASET_ID,
            "article_doi": ARTICLE_DOI,
            "distribution_id": distribution_id,
            "access_url": access_url,
            "media_type": media_type,
            "format": format_label,
            "issued": distribution.get("issued"),
            "modified": distribution.get("modified"),
            "license": license_label,
            "raw_distribution": distribution,
        },
    )


def _parameter_manifest_record(page: dict[str, object], *, raw_path: Path, retrieved_at: str, index: int) -> EvidenceRecord:
    resource = _clean(page.get("resource"))
    return _record(
        record_id=f"swd_jki_drosomon_trap_captures:file:parameter_description_pdf",
        title="JKI DrosoMon SWD parameter description file manifest",
        text=(
            f"Parameter-description file manifest for the JKI DrosoMon {SPECIES} trap-capture dataset. "
            f"Resource URL: {resource or PARAMETER_DESCRIPTION_URL}."
        ),
        raw_path=raw_path,
        locator_suffix=f"result/page/{index}",
        retrieved_at=retrieved_at,
        url=OPENAGRAR_LANDING_URL,
        source_url=resource or PARAMETER_DESCRIPTION_URL,
        payload={
            "atom_type": "jki_drosomon_file_manifest",
            "dataset_id": DATASET_ID,
            "article_doi": ARTICLE_DOI,
            "distribution_id": "parameter_description_pdf",
            "access_url": resource or PARAMETER_DESCRIPTION_URL,
            "media_type": "application/pdf",
            "format": "PDF",
            "license": LICENSE,
        },
    )


def _is_security_check(response: FetchBody) -> bool:
    content_type = response.content_type.lower()
    prefix = response.body[:4096].decode("utf-8", "replace").lower()
    return "text/html" in content_type and ("sicherheits" in prefix or "security" in prefix or "<html" in prefix)


def fetch_drosophila_suzukii_jki_drosomon_trap_capture_records(
    *,
    raw_dir: Path,
    fetch_json=None,
    fetch_body=None,
    retrieved_at: str,
) -> DrosophilaSuzukiiJkiDrosomonTrapCapturesResult:
    fetch_json = fetch_json or _default_fetch_json
    fetch_body = fetch_body or _default_fetch_body
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls = [DATA_EUROPA_URL]

    try:
        dataset_payload = fetch_json(DATA_EUROPA_URL)
    except Exception as exc:
        gap = _gap_dict(
            "jki_drosomon_metadata_fetch_failed",
            locator=f"{DATA_EUROPA_URL}#fetch",
            retrieved_at=retrieved_at,
            source_url=DATA_EUROPA_URL,
            details={"error": str(exc)},
        )
        gaps.append(gap)
        return DrosophilaSuzukiiJkiDrosomonTrapCapturesResult(
            source_id=DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=[],
            requested_urls=requested_urls,
            file_count=0,
            parsed_trap_row_count=0,
        )

    metadata_path = _write_json(raw_dir, "data_europa_dataset.json", dataset_payload)
    raw_artifacts.append(metadata_path.as_posix())
    dataset = dataset_payload.get("result") if isinstance(dataset_payload.get("result"), dict) else dataset_payload
    records.append(_dataset_record(dataset, raw_path=metadata_path, retrieved_at=retrieved_at))

    distributions = dataset.get("distributions") if isinstance(dataset, dict) else []
    file_count = 0
    for index, distribution in enumerate(distributions if isinstance(distributions, list) else [], start=1):
        if not isinstance(distribution, dict):
            continue
        file_count += 1
        records.append(_file_manifest_record(distribution, raw_path=metadata_path, retrieved_at=retrieved_at, index=index))

    for index, page in enumerate(dataset.get("page", []) if isinstance(dataset.get("page"), list) else [], start=1):
        if isinstance(page, dict) and _clean(page.get("resource")).lower().endswith(".pdf"):
            file_count += 1
            records.append(_parameter_manifest_record(page, raw_path=metadata_path, retrieved_at=retrieved_at, index=index))

    requested_urls.append(CAPTURES_CSV_URL)
    parsed_trap_row_count = 0
    try:
        response = fetch_body(CAPTURES_CSV_URL)
        if _is_security_check(response):
            security_path = _write_bytes(raw_dir, "captures_data_security_check.html", response.body[:200_000])
            raw_artifacts.append(security_path.as_posix())
            reason = "openagrar_security_check_blocks_csv_download"
            records.append(
                _gap_record(
                    reason=reason,
                    title="JKI DrosoMon SWD trap-capture gap: CSV blocked by OpenAgrar security check",
                    text=(
                        "The public data.europa registry exposes captures_data.csv for the 7-year JKI DrosoMon SWD trap-capture dataset, "
                        "but the current direct OpenAgrar file URL returns an HTML security-check page instead of CSV. "
                        "Ask Insects keeps the dataset summary and file manifest, but individual trap-deployment rows are not queryable in this pass."
                    ),
                    raw_path=security_path,
                    locator_suffix="html",
                    retrieved_at=retrieved_at,
                    source_url=CAPTURES_CSV_URL,
                    extra={"status": response.status, "content_type": response.content_type, "access_url": CAPTURES_CSV_URL},
                )
            )
            gaps.append(
                _gap_dict(
                    reason,
                    locator=f"{security_path.as_posix()}#html",
                    retrieved_at=retrieved_at,
                    source_url=CAPTURES_CSV_URL,
                    details={"status": response.status, "content_type": response.content_type},
                )
            )
        else:
            csv_path = _write_bytes(raw_dir, "captures_data.csv", response.body)
            raw_artifacts.append(csv_path.as_posix())
            reason = "jki_trap_rows_not_parsed_yet"
            records.append(
                _gap_record(
                    reason=reason,
                    title="JKI DrosoMon SWD trap-capture gap: CSV fetched but row parser not enabled",
                    text=(
                        "The captures_data.csv file was fetched, but this ingest pass only installs dataset and file-manifest atoms. "
                        "Trap-deployment rows still need a schema-checked parser before Ask Insects can answer at individual trap/date grain."
                    ),
                    raw_path=csv_path,
                    locator_suffix="file",
                    retrieved_at=retrieved_at,
                    source_url=CAPTURES_CSV_URL,
                    extra={"status": response.status, "content_type": response.content_type, "byte_size": len(response.body)},
                )
            )
            gaps.append(
                _gap_dict(
                    reason,
                    locator=f"{csv_path.as_posix()}#file",
                    retrieved_at=retrieved_at,
                    source_url=CAPTURES_CSV_URL,
                    details={"status": response.status, "content_type": response.content_type, "byte_size": len(response.body)},
                )
            )
    except Exception as exc:
        reason = "jki_drosomon_csv_fetch_failed"
        records.append(
            _gap_record(
                reason=reason,
                title="JKI DrosoMon SWD trap-capture gap: CSV fetch failed",
                text=f"The captures_data.csv file could not be fetched from OpenAgrar in this pass. Error: {exc}.",
                raw_path=metadata_path,
                locator_suffix="result/distributions/1#gap/csv_fetch_failed",
                retrieved_at=retrieved_at,
                source_url=CAPTURES_CSV_URL,
                extra={"error": str(exc)},
            )
        )
        gaps.append(
            _gap_dict(
                reason,
                locator=f"{metadata_path.as_posix()}#result/distributions/1",
                retrieved_at=retrieved_at,
                source_url=CAPTURES_CSV_URL,
                details={"error": str(exc)},
            )
        )

    if parsed_trap_row_count == 0:
        reason = "jki_trap_deployment_rows_not_queryable"
        records.append(
            _gap_record(
                reason=reason,
                title="JKI DrosoMon SWD trap-capture gap: deployment rows not queryable",
                text=(
                    "The source description reports 9,967 trap-deployment records, but those individual rows are not atomically queryable until "
                    "the captures_data table is fetched and parsed. Dataset-level counts remain queryable as summary evidence."
                ),
                raw_path=metadata_path,
                locator_suffix="result/description#gap/trap_rows_not_queryable",
                retrieved_at=retrieved_at,
                source_url=DATA_EUROPA_URL,
                extra={"reported_deployment_count": 9967},
            )
        )
        gaps.append(
            _gap_dict(
                reason,
                locator=f"{metadata_path.as_posix()}#result/description",
                retrieved_at=retrieved_at,
                source_url=DATA_EUROPA_URL,
                details={"reported_deployment_count": 9967},
            )
        )

    return DrosophilaSuzukiiJkiDrosomonTrapCapturesResult(
        source_id=DROSOPHILA_SUZUKII_JKI_DROSOMON_TRAP_CAPTURES_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        file_count=file_count,
        parsed_trap_row_count=parsed_trap_row_count,
    )
