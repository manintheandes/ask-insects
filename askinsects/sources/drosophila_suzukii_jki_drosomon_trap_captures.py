from __future__ import annotations

import base64
import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
from html import unescape
import http.cookiejar
import io
import json
from pathlib import Path
import re
import time
import urllib.parse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

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
MAX_OPENAGRAR_POW_DIFFICULTY = 22
MAX_OPENAGRAR_POW_NONCE = 10_000_000


@dataclass(frozen=True)
class FetchBody:
    body: bytes
    content_type: str
    status: int
    final_url: str = ""
    pow_challenge: dict[str, object] | None = None


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
    cookie_jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    first = _open_url(opener, url)
    if not _is_openagrar_pow_challenge(first):
        return first

    token = _extract_openagrar_pow_token(first.body)
    if not token:
        return FetchBody(
            body=first.body,
            content_type=first.content_type,
            status=first.status,
            final_url=first.final_url,
            pow_challenge={"attempted": True, "solved": False, "reason": "pow_token_not_found"},
        )

    try:
        challenge_payload = _decode_openagrar_pow_payload(token)
        difficulty = int(challenge_payload.get("difficulty", 0))
        if difficulty > MAX_OPENAGRAR_POW_DIFFICULTY:
            return FetchBody(
                body=first.body,
                content_type=first.content_type,
                status=first.status,
                final_url=first.final_url,
                pow_challenge={
                    "attempted": True,
                    "solved": False,
                    "reason": "pow_difficulty_too_high",
                    "difficulty": difficulty,
                    "redirect_url": challenge_payload.get("redirect_url"),
                },
            )
        nonce = _solve_openagrar_pow(str(challenge_payload.get("challenge", "")), difficulty)
        _submit_openagrar_pow(opener, first.final_url or url, token, nonce)
        retried = _open_url(opener, url)
        return FetchBody(
            body=retried.body,
            content_type=retried.content_type,
            status=retried.status,
            final_url=retried.final_url,
            pow_challenge={
                "attempted": True,
                "solved": not _is_security_check(retried),
                "difficulty": difficulty,
                "nonce": nonce,
                "redirect_url": challenge_payload.get("redirect_url"),
            },
        )
    except Exception as exc:
        return FetchBody(
            body=first.body,
            content_type=first.content_type,
            status=first.status,
            final_url=first.final_url,
            pow_challenge={"attempted": True, "solved": False, "reason": "pow_solve_failed", "error": str(exc)},
        )


def _open_url(opener, url: str) -> FetchBody:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/pdf,*/*"})
    with opener.open(request, timeout=90) as response:
        return FetchBody(
            body=response.read(),
            content_type=str(response.headers.get("content-type") or ""),
            status=int(getattr(response, "status", 200)),
            final_url=str(response.geturl()),
        )


def _is_openagrar_pow_challenge(response: FetchBody) -> bool:
    if "openagrar.de/pow-challenge" in response.final_url:
        return True
    prefix = response.body[:4096].decode("utf-8", "replace")
    return "challengeToken" in prefix and "pow-challenge" in prefix


def _extract_openagrar_pow_token(body: bytes) -> str | None:
    text = body[:100_000].decode("utf-8", "replace")
    match = re.search(r"challengeToken\s*=\s*'([^']+)'", text)
    return match.group(1) if match else None


def _decode_openagrar_pow_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _leading_zero_bits(digest: bytes) -> int:
    zeroes = 0
    for byte in digest:
        if byte == 0:
            zeroes += 8
            continue
        while byte < 128:
            zeroes += 1
            byte <<= 1
        break
    return zeroes


def _solve_openagrar_pow(challenge: str, difficulty: int) -> int:
    if not challenge:
        raise ValueError("OpenAgrar proof-of-work challenge is empty")
    for nonce in range(MAX_OPENAGRAR_POW_NONCE + 1):
        digest = hashlib.sha256((challenge + str(nonce)).encode("utf-8")).digest()
        if _leading_zero_bits(digest) >= difficulty:
            return nonce
    raise TimeoutError(f"OpenAgrar proof-of-work nonce not found within {MAX_OPENAGRAR_POW_NONCE}")


def _submit_openagrar_pow(opener, challenge_url: str, token: str, nonce: int) -> None:
    endpoint = urllib.parse.urljoin(challenge_url, "/pow-challenge")
    browser_info = {
        "userAgent": USER_AGENT,
        "language": "en-US",
        "languages": ["en-US", "en"],
        "platform": "MacIntel",
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "screenResolution": "1440x900",
        "colorDepth": 24,
        "timezone": "America/Los_Angeles",
        "timezoneOffset": 420,
        "plugins": [],
        "webdriver": False,
        "headless": False,
        "cookieEnabled": True,
        "doNotTrack": None,
        "touchSupport": False,
        "timestamp": int(time.time() * 1000),
    }
    payload = urllib.parse.urlencode(
        {
            "pow_solution": str(nonce),
            "information": json.dumps(browser_info, separators=(",", ":")),
            "pow_challenge_token": token,
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,application/pdf,*/*",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with opener.open(request, timeout=90) as response:
        response.read()


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


def _parse_int(value: object) -> int | None:
    text = _clean(value)
    if text == "":
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None


def _parse_german_date(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _trap_days(start_iso: str | None, stop_iso: str | None) -> int | None:
    if not start_iso or not stop_iso:
        return None
    try:
        start = datetime.strptime(start_iso, "%Y-%m-%d").date()
        stop = datetime.strptime(stop_iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    days = (stop - start).days
    return days if days >= 0 else None


def _parse_captures_csv_records(body: bytes, *, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    text = body.decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    records: list[EvidenceRecord] = []
    for row_index, row in enumerate(reader, start=2):
        trap_name = _clean(row.get("trap_name"))
        date_start = _parse_german_date(row.get("date_start"))
        date_stop = _parse_german_date(row.get("date_stop"))
        males = _parse_int(row.get("males")) or 0
        females = _parse_int(row.get("females")) or 0
        total = males + females
        trap_days = _trap_days(date_start, date_stop)
        if not trap_name or date_start is None or date_stop is None:
            continue
        row_number = row_index - 1
        title = f"JKI DrosoMon SWD trap deployment {trap_name}, {date_start} to {date_stop}"
        text_parts = [
            f"JKI DrosoMon trap-deployment row for {SPECIES} at trap {trap_name}.",
            f"Deployment window: {date_start} to {date_stop}.",
            f"Adult captures: {total} total ({males} males, {females} females).",
        ]
        if trap_days is not None:
            text_parts.append(f"Trap-days in this deployment: {trap_days}.")
        text_parts.append(
            "The captures_data.csv table gives trap name and capture counts; coordinates are described by the dataset but are not present in this CSV row."
        )
        records.append(
            _record(
                record_id=f"swd_jki_drosomon_trap_captures:trap_row:{row_number}",
                title=title,
                text=" ".join(text_parts),
                raw_path=raw_path,
                locator_suffix=f"row/{row_number}",
                retrieved_at=retrieved_at,
                url=OPENAGRAR_LANDING_URL,
                source_url=CAPTURES_CSV_URL,
                payload={
                    "atom_type": "jki_drosomon_trap_deployment_row",
                    "dataset_id": DATASET_ID,
                    "article_doi": ARTICLE_DOI,
                    "row_number": row_number,
                    "trap_name": trap_name,
                    "date_start": date_start,
                    "date_stop": date_stop,
                    "trap_days": trap_days,
                    "males": males,
                    "females": females,
                    "adult_captures": total,
                    "coordinates_available": False,
                    "raw_row": {str(key): value for key, value in row.items()},
                },
            )
        )
    return records


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
            details = {
                "status": response.status,
                "content_type": response.content_type,
                "access_url": CAPTURES_CSV_URL,
                "pow_challenge": response.pow_challenge,
            }
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
                    extra=details,
                )
            )
            gaps.append(
                _gap_dict(
                    reason,
                    locator=f"{security_path.as_posix()}#html",
                    retrieved_at=retrieved_at,
                    source_url=CAPTURES_CSV_URL,
                    details=details,
                )
            )
        else:
            csv_path = _write_bytes(raw_dir, "captures_data.csv", response.body)
            raw_artifacts.append(csv_path.as_posix())
            trap_records = _parse_captures_csv_records(response.body, raw_path=csv_path, retrieved_at=retrieved_at)
            records.extend(trap_records)
            parsed_trap_row_count = len(trap_records)
            if parsed_trap_row_count == 0:
                reason = "jki_trap_rows_parse_empty"
                records.append(
                    _gap_record(
                        reason=reason,
                        title="JKI DrosoMon SWD trap-capture gap: CSV parser found no rows",
                        text=(
                            "The captures_data.csv file was fetched, but the schema-checked parser did not produce trap-deployment rows. "
                            "Ask Insects keeps the source file and records this as a parsing gap."
                        ),
                        raw_path=csv_path,
                        locator_suffix="file",
                        retrieved_at=retrieved_at,
                        source_url=CAPTURES_CSV_URL,
                        extra={
                            "status": response.status,
                            "content_type": response.content_type,
                            "byte_size": len(response.body),
                            "pow_challenge": response.pow_challenge,
                        },
                    )
                )
                gaps.append(
                    _gap_dict(
                        reason,
                        locator=f"{csv_path.as_posix()}#file",
                        retrieved_at=retrieved_at,
                        source_url=CAPTURES_CSV_URL,
                        details={
                            "status": response.status,
                            "content_type": response.content_type,
                            "byte_size": len(response.body),
                            "pow_challenge": response.pow_challenge,
                        },
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
