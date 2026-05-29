from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import io
import json
import re
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID = "drosophila_suzukii_umn_flight_assay_rows"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
ITEM_UUID = "3c514fff-5e6e-4847-a083-3700326e8ad1"
BITSTREAM_UUID = "81028480-4f7d-4b2a-b648-403c683b7f26"
HANDLE = "11299/227164"
LANDING_URL = "https://hdl.handle.net/11299/227164"
ITEM_API_URL = f"https://conservancy.umn.edu/server/api/core/items/{ITEM_UUID}"
BITSTREAM_API_URL = f"https://conservancy.umn.edu/server/api/core/bitstreams/{BITSTREAM_UUID}"
CSV_CONTENT_URL = f"{BITSTREAM_API_URL}/content"
FILE_NAME = "data_archival.csv"
EXPECTED_SIZE_BYTES = 15_543
EXPECTED_MD5 = "57f90c4209fe9c677f40d90a60935360"
EXPECTED_ROW_COUNT = 401
DATASET_DOI = "10.13020/4nsz-x660"
LICENSE = "Attribution-NonCommercial 3.0 United States"
LICENSE_URL = "http://creativecommons.org/licenses/by-nc/3.0/us/"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class DrosophilaSuzukiiUmnFlightAssayRowsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    dataset_count: int
    file_count: int
    parsed_row_count: int


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _default_fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,*/*"})
    with urlopen(request, timeout=90) as response:
        return response.read()


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
    text = str(value or "").replace("\ufeff", "")
    if text.strip() == ".":
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", _clean(value)).strip("_") or "unknown"


def _metadata_values(payload: dict[str, object], key: str) -> list[str]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return []
    values = metadata.get(key)
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        if isinstance(value, dict):
            cleaned = _clean(value.get("value"))
            if cleaned:
                out.append(cleaned)
    return out


def _first_metadata(payload: dict[str, object], key: str, default: str = "") -> str:
    values = _metadata_values(payload, key)
    return values[0] if values else default


def _number(value: object) -> float | int | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _record(
    *,
    record_id: str,
    title: str,
    text: str,
    raw_path: Path,
    locator_suffix: str,
    retrieved_at: str,
    source_url: str,
    payload: dict[str, object],
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="behavior",
        source=DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=LANDING_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#{locator_suffix}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=source_url,
        ),
        payload=payload,
    )


def _gap_dict(reason: str, *, locator: str, retrieved_at: str, source_url: str, details: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "source": DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID,
        "species": SPECIES,
        "lane": "behavior",
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
    source_url: str,
    extra: dict[str, object] | None = None,
) -> EvidenceRecord:
    return _record(
        record_id=f"swd_umn_flight_assay:gap:{_safe_id(reason)}",
        title=title,
        text=text,
        raw_path=raw_path,
        locator_suffix=locator_suffix,
        retrieved_at=retrieved_at,
        source_url=source_url,
        payload={
            "atom_type": "source_gap",
            "reason": reason,
            "dataset_doi": DATASET_DOI,
            "item_uuid": ITEM_UUID,
            "bitstream_uuid": BITSTREAM_UUID,
            **(extra or {}),
        },
    )


def _dataset_record(item: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    title = _first_metadata(item, "dc.title", str(item.get("name") or ""))
    authors = _metadata_values(item, "dc.contributor.author")
    abstract = _first_metadata(item, "dc.description.abstract")
    issued = _first_metadata(item, "dc.date.issued")
    rights = _first_metadata(item, "dc.rights", LICENSE)
    rights_uri = _first_metadata(item, "dc.rights.uri", LICENSE_URL)
    text = (
        f"University of Minnesota dataset for {SPECIES} ({COMMON_NAME}) flight behavior. "
        "The dataset documents winter and summer morph flight behavior on two assay types: "
        "a free-flight chamber and a tethered flight mill. "
        f"It includes {EXPECTED_ROW_COUNT} row-level observations with treatment, morph, sex, age, flight propensity, "
        "phototactic response, duration, bouts, distance, and average velocity fields. "
        f"Issued: {issued or 'unknown'}. DOI: {DATASET_DOI}. License: {rights}."
    )
    return _record(
        record_id=f"swd_umn_flight_assay:dataset:{HANDLE.replace('/', '_')}",
        title=f"{SPECIES} UMN flight behavior assay dataset",
        text=text,
        raw_path=raw_path,
        locator_suffix="item",
        retrieved_at=retrieved_at,
        source_url=ITEM_API_URL,
        payload={
            "atom_type": "umn_flight_assay_dataset",
            "item_uuid": ITEM_UUID,
            "handle": HANDLE,
            "dataset_doi": DATASET_DOI,
            "title": title,
            "authors": authors,
            "issued": issued,
            "abstract": abstract,
            "rights": rights,
            "rights_uri": rights_uri,
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "expected_row_count": EXPECTED_ROW_COUNT,
            "assay_types": ["free-flight chamber", "tethered flight mill"],
            "row_fields": [
                "date",
                "treatment",
                "morph",
                "sex",
                "age",
                "propensity",
                "phototactic",
                "duration",
                "bouts",
                "distancecm",
                "avgvelcm/s",
            ],
        },
    )


def _file_record(bitstream: dict[str, object], *, raw_path: Path, csv_sha256: str, csv_md5: str, csv_byte_size: int, retrieved_at: str) -> EvidenceRecord:
    checksum = bitstream.get("checkSum") if isinstance(bitstream.get("checkSum"), dict) else {}
    title = _first_metadata(bitstream, "dc.title", FILE_NAME)
    description = _first_metadata(bitstream, "dc.description")
    return _record(
        record_id=f"swd_umn_flight_assay:file:{BITSTREAM_UUID}",
        title=f"{SPECIES} UMN flight behavior CSV file manifest",
        text=(
            f"File manifest for the UMN {SPECIES} flight behavior CSV {title}. "
            f"Description: {description or 'not supplied'}. Byte size: {csv_byte_size}. "
            f"MD5: {csv_md5}. SHA-256: {csv_sha256}."
        ),
        raw_path=raw_path,
        locator_suffix="bitstream",
        retrieved_at=retrieved_at,
        source_url=BITSTREAM_API_URL,
        payload={
            "atom_type": "umn_flight_assay_file_manifest",
            "item_uuid": ITEM_UUID,
            "bitstream_uuid": BITSTREAM_UUID,
            "file_name": title,
            "description": description,
            "content_url": CSV_CONTENT_URL,
            "api_url": BITSTREAM_API_URL,
            "landing_url": LANDING_URL,
            "dataset_doi": DATASET_DOI,
            "reported_size_bytes": bitstream.get("sizeBytes"),
            "byte_size": csv_byte_size,
            "reported_checksum": checksum,
            "md5": csv_md5,
            "sha256": csv_sha256,
            "license": LICENSE,
            "license_url": LICENSE_URL,
        },
    )


def _row_record(row: dict[str, str], *, raw_path: Path, row_number: int, retrieved_at: str) -> EvidenceRecord:
    treatment = _clean(row.get("treatment"))
    morph = _clean(row.get("morph"))
    sex = _clean(row.get("sex"))
    date = _clean(row.get("date"))
    age = _number(row.get("age"))
    propensity = _number(row.get("propensity"))
    phototactic = _number(row.get("phototactic"))
    duration = _number(row.get("duration"))
    bouts = _number(row.get("bouts"))
    distance_cm = _number(row.get("distancecm"))
    avg_velocity_cm_s = _number(row.get("avgvelcm/s"))
    assay_label = "free-flight chamber" if treatment == "chamber" else "tethered flight mill" if treatment == "mill" else treatment or "unknown assay"
    text_parts = [
        f"UMN {SPECIES} flight behavior row {row_number}: {assay_label}.",
        f"Date: {date}." if date else "",
        f"Morph code: {morph}." if morph else "",
        f"Sex: {sex}." if sex else "",
        f"Age: {age}." if age is not None else "",
        f"Flight propensity: {propensity}." if propensity is not None else "",
        f"Phototactic response: {phototactic}." if phototactic is not None else "",
        f"Duration: {duration}." if duration is not None else "",
        f"Bouts: {bouts}." if bouts is not None else "",
        f"Distance cm: {distance_cm}." if distance_cm is not None else "",
        f"Average velocity cm/s: {avg_velocity_cm_s}." if avg_velocity_cm_s is not None else "",
    ]
    return _record(
        record_id=f"swd_umn_flight_assay:row:{row_number}",
        title=f"{SPECIES} UMN flight assay row {row_number}: {assay_label}",
        text=" ".join(part for part in text_parts if part),
        raw_path=raw_path,
        locator_suffix=f"row/{row_number}",
        retrieved_at=retrieved_at,
        source_url=CSV_CONTENT_URL,
        payload={
            "atom_type": "umn_flight_assay_row",
            "dataset_doi": DATASET_DOI,
            "item_uuid": ITEM_UUID,
            "bitstream_uuid": BITSTREAM_UUID,
            "row_number": row_number,
            "date": date or None,
            "treatment": treatment or None,
            "assay": assay_label,
            "morph": morph or None,
            "sex": sex or None,
            "age_days": age,
            "behavior_type": "flight",
            "life_stage": "adult",
            "propensity": propensity,
            "phototactic": phototactic,
            "duration": duration,
            "bouts": bouts,
            "distance_cm": distance_cm,
            "avg_velocity_cm_s": avg_velocity_cm_s,
            "confidence": "source_table_row",
            "table_row": {key: _clean(value) for key, value in row.items()},
        },
    )


def fetch_drosophila_suzukii_umn_flight_assay_row_records(
    *,
    raw_dir: Path,
    fetch_json=None,
    fetch_bytes=None,
    retrieved_at: str,
    max_download_bytes: int = 1_000_000,
    max_rows: int | None = None,
) -> DrosophilaSuzukiiUmnFlightAssayRowsResult:
    fetch_json = fetch_json or _default_fetch_json
    fetch_bytes = fetch_bytes or _default_fetch_bytes
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls = [ITEM_API_URL, BITSTREAM_API_URL, CSV_CONTENT_URL]
    dataset_count = 0
    file_count = 0
    parsed_row_count = 0

    try:
        item = fetch_json(ITEM_API_URL)
        item_path = _write_json(raw_dir, "item.json", item)
        raw_artifacts.append(item_path.as_posix())
        records.append(_dataset_record(item, raw_path=item_path, retrieved_at=retrieved_at))
        dataset_count = 1
    except Exception as exc:
        gaps.append(
            _gap_dict(
                "umn_flight_assay_item_metadata_fetch_failed",
                locator=f"{ITEM_API_URL}#fetch",
                retrieved_at=retrieved_at,
                source_url=ITEM_API_URL,
                details={"error": str(exc)},
            )
        )
        item_path = raw_dir / "item.json"

    try:
        bitstream = fetch_json(BITSTREAM_API_URL)
        bitstream_path = _write_json(raw_dir, "bitstream.json", bitstream)
        raw_artifacts.append(bitstream_path.as_posix())
    except Exception as exc:
        bitstream = {}
        bitstream_path = item_path if item_path.exists() else raw_dir / "bitstream.json"
        gaps.append(
            _gap_dict(
                "umn_flight_assay_bitstream_metadata_fetch_failed",
                locator=f"{BITSTREAM_API_URL}#fetch",
                retrieved_at=retrieved_at,
                source_url=BITSTREAM_API_URL,
                details={"error": str(exc)},
            )
        )

    try:
        data = fetch_bytes(CSV_CONTENT_URL)
        if len(data) > max_download_bytes:
            gaps.append(
                _gap_dict(
                    "umn_flight_assay_csv_too_large",
                    locator=f"{CSV_CONTENT_URL}#bytes",
                    retrieved_at=retrieved_at,
                    source_url=CSV_CONTENT_URL,
                    details={"byte_size": len(data), "max_download_bytes": max_download_bytes},
                )
            )
            return DrosophilaSuzukiiUmnFlightAssayRowsResult(
                source_id=DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID,
                records=records,
                gaps=gaps,
                raw_artifacts=raw_artifacts,
                requested_urls=requested_urls,
                dataset_count=dataset_count,
                file_count=file_count,
                parsed_row_count=parsed_row_count,
            )
        csv_path = _write_bytes(raw_dir, FILE_NAME, data)
        raw_artifacts.append(csv_path.as_posix())
        file_count = 1
        csv_md5 = hashlib.md5(data).hexdigest()
        csv_sha256 = hashlib.sha256(data).hexdigest()
        records.append(
            _file_record(
                bitstream,
                raw_path=bitstream_path if bitstream_path.exists() else csv_path,
                csv_sha256=csv_sha256,
                csv_md5=csv_md5,
                csv_byte_size=len(data),
                retrieved_at=retrieved_at,
            )
        )
        if len(data) != EXPECTED_SIZE_BYTES:
            gaps.append(
                _gap_dict(
                    "umn_flight_assay_csv_byte_size_changed",
                    locator=f"{csv_path.as_posix()}#file",
                    retrieved_at=retrieved_at,
                    source_url=CSV_CONTENT_URL,
                    details={"expected_byte_size": EXPECTED_SIZE_BYTES, "actual_byte_size": len(data)},
                )
            )
        if csv_md5 != EXPECTED_MD5:
            gaps.append(
                _gap_dict(
                    "umn_flight_assay_csv_md5_changed",
                    locator=f"{csv_path.as_posix()}#file",
                    retrieved_at=retrieved_at,
                    source_url=CSV_CONTENT_URL,
                    details={"expected_md5": EXPECTED_MD5, "actual_md5": csv_md5},
                )
            )
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", "replace")))
        for row_number, row in enumerate(reader, start=1):
            if max_rows is not None and row_number > max_rows:
                gaps.append(
                    _gap_dict(
                        "umn_flight_assay_row_limit_applied",
                        locator=f"{csv_path.as_posix()}#row/{row_number}",
                        retrieved_at=retrieved_at,
                        source_url=CSV_CONTENT_URL,
                        details={"max_rows": max_rows},
                    )
                )
                break
            if not any(_clean(value) for value in row.values()):
                continue
            records.append(_row_record(row, raw_path=csv_path, row_number=row_number, retrieved_at=retrieved_at))
            parsed_row_count += 1
        if max_rows is None and parsed_row_count != EXPECTED_ROW_COUNT:
            gaps.append(
                _gap_dict(
                    "umn_flight_assay_row_count_changed",
                    locator=f"{csv_path.as_posix()}#rows",
                    retrieved_at=retrieved_at,
                    source_url=CSV_CONTENT_URL,
                    details={"expected_row_count": EXPECTED_ROW_COUNT, "actual_row_count": parsed_row_count},
                )
            )
    except Exception as exc:
        gaps.append(
            _gap_dict(
                "umn_flight_assay_csv_fetch_or_parse_failed",
                locator=f"{CSV_CONTENT_URL}#fetch",
                retrieved_at=retrieved_at,
                source_url=CSV_CONTENT_URL,
                details={"error": str(exc)},
            )
        )

    if parsed_row_count == 0:
        records.append(
            _gap_record(
                reason="umn_flight_assay_rows_not_queryable",
                title="UMN SWD flight assay gap: rows not queryable",
                text=(
                    "The UMN dataset was located, but no flight-assay rows were parsed in this pass. "
                    "Ask Insects keeps this explicit behavior-source gap until row records are available."
                ),
                raw_path=item_path if item_path.exists() else raw_dir,
                locator_suffix="rows#gap",
                retrieved_at=retrieved_at,
                source_url=CSV_CONTENT_URL,
            )
        )

    return DrosophilaSuzukiiUmnFlightAssayRowsResult(
        source_id=DROSOPHILA_SUZUKII_UMN_FLIGHT_ASSAY_ROWS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        dataset_count=dataset_count,
        file_count=file_count,
        parsed_row_count=parsed_row_count,
    )
