from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Callable
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import zipfile

from askinsects.records import EvidenceRecord, Provenance


VECTORNET_SOURCE_ID = "vectornet_aedes_surveillance"
VECTORNET_RESOURCE_URL = "https://ipt.gbif.org/resource?r=vndatabase"
VECTORNET_ARCHIVE_URL = "https://ipt.gbif.org/archive.do?r=vndatabase"
VECTORNET_DATASET_KEY = "7a5757c3-58f8-4ff6-9662-32296965a2f3"
VECTORNET_LICENSE = "CC-BY-4.0"
VECTORNET_DATASET_TITLE = "VectorNet"
DEFAULT_VECTORNET_SPECIES = "Aedes aegypti"


@dataclass(frozen=True)
class VectorNetBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    dataset_key: str
    dataset_title: str
    species: str
    archive_url: str
    resource_url: str
    row_count: int
    matched_row_count: int
    observation_record_count: int
    ecology_record_count: int
    filtered_rows_path: str | None
    pub_date: str | None
    license: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ask-insects-vectornet-source/0.1"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _safe_id(value: object) -> str:
    text = str(value or "")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    if safe:
        return safe
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or text.upper() in {"NA", "N/A", "NULL", "NONE"}:
        return None
    return text


def _matches_species(row: dict[str, str], species: str) -> bool:
    target = species.lower()
    names = [
        row.get("scientificName", ""),
        row.get("verbatimIdentification", ""),
    ]
    return any(target in str(name).lower() for name in names)


def _event_start_date(event_date: str | None) -> str | None:
    if not event_date:
        return None
    return event_date.split("/", 1)[0].strip() or None


def _presence_bucket(row: dict[str, str]) -> str:
    degree = (_clean(row.get("degreeOfEstablishment")) or "").lower()
    count_text = _clean(row.get("individualCount"))
    count = None
    if count_text is not None:
        try:
            count = float(count_text)
        except ValueError:
            count = None
    if "absent" in degree:
        return "absence_surveillance"
    if "present" in degree or "established" in degree or (count is not None and count > 0):
        return "detection_or_presence_evidence"
    return "surveillance_status_unclear"


def _vectornet_url(row: dict[str, str]) -> str:
    occurrence_id = _clean(row.get("occurrenceID")) or _clean(row.get("id"))
    if occurrence_id:
        return f"{VECTORNET_RESOURCE_URL}#occurrence/{occurrence_id}"
    return VECTORNET_RESOURCE_URL


def _parse_eml(eml_bytes: bytes) -> dict[str, object]:
    metadata: dict[str, object] = {
        "dataset_key": VECTORNET_DATASET_KEY,
        "dataset_title": VECTORNET_DATASET_TITLE,
        "license": VECTORNET_LICENSE,
        "pub_date": None,
        "citation": None,
        "resource_url": VECTORNET_RESOURCE_URL,
    }
    try:
        root = ET.fromstring(eml_bytes)
    except ET.ParseError:
        return metadata

    def first_text(local_name: str) -> str | None:
        for elem in root.iter():
            if elem.tag.split("}")[-1] == local_name and elem.text and elem.text.strip():
                return elem.text.strip()
        return None

    alternates = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.split("}")[-1] == "alternateIdentifier" and elem.text and elem.text.strip()
    ]
    for alternate in alternates:
        if re.fullmatch(r"[0-9a-fA-F-]{36}", alternate):
            metadata["dataset_key"] = alternate
            break
    metadata["dataset_title"] = first_text("title") or VECTORNET_DATASET_TITLE
    metadata["pub_date"] = first_text("pubDate")
    metadata["citation"] = first_text("citation")
    for elem in root.iter():
        if elem.tag.split("}")[-1] == "identifier" and elem.text and elem.text.strip():
            value = elem.text.strip()
            if value.startswith("CC-"):
                metadata["license"] = value
                break
    return metadata


def observation_record(
    row: dict[str, str],
    *,
    raw_archive_path: Path,
    filtered_rows_path: Path,
    row_number: int,
    filtered_row_number: int,
    metadata: dict[str, object],
    retrieved_at: str,
    species: str,
) -> EvidenceRecord:
    occurrence_id = _clean(row.get("occurrenceID")) or _clean(row.get("id")) or f"row-{row_number}"
    country = _clean(row.get("higherGeography")) or _clean(row.get("countryCode")) or "unknown geography"
    event_date = _clean(row.get("eventDate")) or "unknown date"
    protocol = _clean(row.get("samplingProtocol")) or "sampling protocol not supplied"
    establishment = _clean(row.get("degreeOfEstablishment")) or "establishment status not supplied"
    count = _clean(row.get("individualCount")) or "count not supplied"
    life_stage = _clean(row.get("lifeStage")) or "life stage not supplied"
    sex = _clean(row.get("sex")) or "sex not supplied"
    identification = _clean(row.get("identificationRemarks")) or "identification method not supplied"
    presence_bucket = _presence_bucket(row)
    record_id = f"vectornet:observation:{_safe_id(occurrence_id)}"
    text = (
        f"Official VectorNet ECDC/EFSA surveillance occurrence row for {species} in {country}, "
        f"event date {event_date}, sampling protocol {protocol}, reported individual count {count}, "
        f"life stage {life_stage}, sex {sex}, degree of establishment {establishment}, "
        f"presence bucket {presence_bucket}, identification {identification}."
    )
    return EvidenceRecord(
        record_id=record_id,
        lane="observations",
        source=VECTORNET_SOURCE_ID,
        title=f"VectorNet {species} surveillance row {occurrence_id}",
        text=text,
        species=species,
        url=_vectornet_url(row),
        media_url=None,
        provenance=Provenance(
            source_id=VECTORNET_SOURCE_ID,
            locator=(
                f"{raw_archive_path.as_posix()}#occurrence.txt/row/{row_number};"
                f"{filtered_rows_path.as_posix()}#row/{filtered_row_number}"
            ),
            retrieved_at=retrieved_at,
            license=str(metadata.get("license") or VECTORNET_LICENSE),
            source_url=VECTORNET_ARCHIVE_URL,
        ),
        payload={
            "atom_type": "vectornet_surveillance_observation",
            "raw_occurrence": row,
            "dataset_key": metadata.get("dataset_key"),
            "dataset_title": metadata.get("dataset_title"),
            "dataset_pub_date": metadata.get("pub_date"),
            "dataset_citation": metadata.get("citation"),
            "archive_url": VECTORNET_ARCHIVE_URL,
            "resource_url": VECTORNET_RESOURCE_URL,
            "row_number": row_number,
            "filtered_row_number": filtered_row_number,
            "presence_bucket": presence_bucket,
            "event_start_date": _event_start_date(_clean(row.get("eventDate"))),
        },
    )


def ecology_record(
    key: str,
    rows: list[dict[str, str]],
    *,
    metadata: dict[str, object],
    filtered_rows_path: Path,
    retrieved_at: str,
    species: str,
) -> EvidenceRecord:
    countries = sorted({_clean(row.get("higherGeography")) or _clean(row.get("countryCode")) or "unknown geography" for row in rows})
    protocols = sorted({_clean(row.get("samplingProtocol")) or "not supplied" for row in rows})
    stages = sorted({_clean(row.get("lifeStage")) or "not supplied" for row in rows})
    buckets = [_presence_bucket(row) for row in rows]
    dates = sorted(date for date in (_event_start_date(_clean(row.get("eventDate"))) for row in rows) if date)
    detections = sum(1 for bucket in buckets if bucket == "detection_or_presence_evidence")
    absences = sum(1 for bucket in buckets if bucket == "absence_surveillance")
    unclear = len(rows) - detections - absences
    record_key = _safe_id(key)
    title = f"VectorNet {species} regional surveillance summary: {key}"
    text = (
        f"VectorNet ECDC/EFSA has {len(rows)} {species} surveillance row(s) for {key}. "
        f"Presence-evidence rows: {detections}; absence-surveillance rows: {absences}; unclear status rows: {unclear}. "
        f"Date range: {dates[0] if dates else 'unknown'} to {dates[-1] if dates else 'unknown'}. "
        f"Sample protocols: {', '.join(protocols[:4])}. Life stages: {', '.join(stages[:4])}."
    )
    return EvidenceRecord(
        record_id=f"vectornet:ecology:{record_key}",
        lane="ecology",
        source=VECTORNET_SOURCE_ID,
        title=title,
        text=text,
        species=species,
        url=VECTORNET_RESOURCE_URL,
        media_url=None,
        provenance=Provenance(
            source_id=VECTORNET_SOURCE_ID,
            locator=f"{filtered_rows_path.as_posix()}#summary/{record_key}",
            retrieved_at=retrieved_at,
            license=str(metadata.get("license") or VECTORNET_LICENSE),
            source_url=VECTORNET_RESOURCE_URL,
        ),
        payload={
            "atom_type": "vectornet_surveillance_ecology_summary",
            "summary_key": key,
            "dataset_key": metadata.get("dataset_key"),
            "dataset_title": metadata.get("dataset_title"),
            "species": species,
            "row_count": len(rows),
            "presence_evidence_count": detections,
            "absence_surveillance_count": absences,
            "unclear_status_count": unclear,
            "first_event_date": dates[0] if dates else None,
            "last_event_date": dates[-1] if dates else None,
            "higher_geographies": countries[:25],
            "sampling_protocols": protocols[:25],
            "life_stages": stages[:25],
            "sample_occurrence_ids": [row.get("occurrenceID") or row.get("id") for row in rows[:10]],
        },
    )


def _write_filtered_rows(path: Path, rows: list[tuple[int, dict[str, str]]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_row_number", *fieldnames], delimiter="\t")
        writer.writeheader()
        for row_number, row in rows:
            writer.writerow({"source_row_number": row_number, **row})


def _country_key(row: dict[str, str]) -> str:
    geography = _clean(row.get("higherGeography")) or _clean(row.get("countryCode")) or "unknown geography"
    country = geography.split("|", 1)[0].strip()
    return f"country:{country}"


def _establishment_key(row: dict[str, str]) -> str:
    establishment = _clean(row.get("degreeOfEstablishment")) or "not supplied"
    return f"establishment:{establishment}"


def fetch_vectornet_surveillance_records(
    *,
    raw_dir: Path,
    species: str = DEFAULT_VECTORNET_SPECIES,
    archive_url: str = VECTORNET_ARCHIVE_URL,
    fetch_bytes: Callable[[str], bytes] | None = None,
    retrieved_at: str | None = None,
    max_records: int | None = None,
) -> VectorNetBuildResult:
    if max_records is not None and max_records < 0:
        raise ValueError("max_records must be zero or greater")

    retrieved = retrieved_at or utc_now()
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive_bytes = (fetch_bytes or _fetch_bytes)(archive_url)
    archive_path = raw_dir / "dwca-vndatabase-v1.3.zip"
    archive_path.write_bytes(archive_bytes)
    raw_artifacts = [archive_path.as_posix()]

    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    filtered_rows: list[tuple[int, dict[str, str]]] = []
    row_count = 0

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        gaps.append(
            {
                "source": VECTORNET_SOURCE_ID,
                "lane": "observations",
                "reason": "vectornet_archive_not_zip",
                "archive_url": archive_url,
                "error": str(exc),
                "retrieved_at": retrieved,
            }
        )
        return VectorNetBuildResult(
            source_id=VECTORNET_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=raw_artifacts,
            dataset_key=VECTORNET_DATASET_KEY,
            dataset_title=VECTORNET_DATASET_TITLE,
            species=species,
            archive_url=archive_url,
            resource_url=VECTORNET_RESOURCE_URL,
            row_count=0,
            matched_row_count=0,
            observation_record_count=0,
            ecology_record_count=0,
            filtered_rows_path=None,
            pub_date=None,
            license=VECTORNET_LICENSE,
        )

    with archive:
        eml_bytes = archive.read("eml.xml") if "eml.xml" in archive.namelist() else b""
        metadata = _parse_eml(eml_bytes)
        if eml_bytes:
            eml_path = raw_dir / "eml.xml"
            eml_path.write_bytes(eml_bytes)
            raw_artifacts.append(eml_path.as_posix())
        if "meta.xml" in archive.namelist():
            meta_path = raw_dir / "meta.xml"
            meta_path.write_bytes(archive.read("meta.xml"))
            raw_artifacts.append(meta_path.as_posix())
        if "occurrence.txt" not in archive.namelist():
            gaps.append(
                {
                    "source": VECTORNET_SOURCE_ID,
                    "lane": "observations",
                    "reason": "vectornet_archive_missing_occurrence_txt",
                    "archive_url": archive_url,
                    "retrieved_at": retrieved,
                }
            )
            return VectorNetBuildResult(
                source_id=VECTORNET_SOURCE_ID,
                records=[],
                gaps=gaps,
                raw_artifacts=raw_artifacts,
                dataset_key=str(metadata.get("dataset_key") or VECTORNET_DATASET_KEY),
                dataset_title=str(metadata.get("dataset_title") or VECTORNET_DATASET_TITLE),
                species=species,
                archive_url=archive_url,
                resource_url=VECTORNET_RESOURCE_URL,
                row_count=0,
                matched_row_count=0,
                observation_record_count=0,
                ecology_record_count=0,
                filtered_rows_path=None,
                pub_date=str(metadata.get("pub_date")) if metadata.get("pub_date") else None,
                license=str(metadata.get("license") or VECTORNET_LICENSE),
            )
        with archive.open("occurrence.txt") as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text, delimiter="\t")
            fieldnames = list(reader.fieldnames or [])
            for row_index, row in enumerate(reader, start=2):
                row_count += 1
                if not _matches_species(row, species):
                    continue
                if max_records is not None and len(filtered_rows) >= max_records:
                    break
                filtered_rows.append((row_index, dict(row)))

    filtered_path = raw_dir / "vectornet_aedes_aegypti_occurrence_rows.tsv"
    _write_filtered_rows(filtered_path, filtered_rows, fieldnames)
    raw_artifacts.append(filtered_path.as_posix())

    for filtered_index, (source_row_number, row) in enumerate(filtered_rows, start=2):
        records.append(
            observation_record(
                row,
                raw_archive_path=archive_path,
                filtered_rows_path=filtered_path,
                row_number=source_row_number,
                filtered_row_number=filtered_index,
                metadata=metadata,
                retrieved_at=retrieved,
                species=species,
            )
        )

    if not filtered_rows:
        gaps.append(
            {
                "source": VECTORNET_SOURCE_ID,
                "lane": "observations",
                "reason": "vectornet_no_matching_species_rows",
                "species": species,
                "archive_url": archive_url,
                "retrieved_at": retrieved,
            }
        )
    grouped: dict[str, list[dict[str, str]]] = {}
    for _row_number, row in filtered_rows:
        for key in (_country_key(row), _establishment_key(row)):
            grouped.setdefault(key, []).append(row)
    ecology_records = [
        ecology_record(
            key,
            rows,
            metadata=metadata,
            filtered_rows_path=filtered_path,
            retrieved_at=retrieved,
            species=species,
        )
        for key, rows in sorted(grouped.items())
    ]
    records.extend(ecology_records)
    if max_records is not None and len(filtered_rows) >= max_records:
        gaps.append(
            {
                "source": VECTORNET_SOURCE_ID,
                "lane": "observations",
                "reason": "vectornet_record_limit_applied",
                "species": species,
                "max_records": max_records,
                "retrieved_at": retrieved,
            }
        )

    return VectorNetBuildResult(
        source_id=VECTORNET_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        dataset_key=str(metadata.get("dataset_key") or VECTORNET_DATASET_KEY),
        dataset_title=str(metadata.get("dataset_title") or VECTORNET_DATASET_TITLE),
        species=species,
        archive_url=archive_url,
        resource_url=VECTORNET_RESOURCE_URL,
        row_count=row_count,
        matched_row_count=len(filtered_rows),
        observation_record_count=len(filtered_rows),
        ecology_record_count=len(ecology_records),
        filtered_rows_path=filtered_path.as_posix(),
        pub_date=str(metadata.get("pub_date")) if metadata.get("pub_date") else None,
        license=str(metadata.get("license") or VECTORNET_LICENSE),
    )
