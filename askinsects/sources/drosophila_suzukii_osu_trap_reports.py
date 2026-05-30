from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID = "drosophila_suzukii_osu_trap_reports"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
LANDING_URL = "https://u.osu.edu/pestmanagement/trap-reports/spotted-wing-drosophila-trap-reports/"
LICENSE = "Ohio State public extension trap report"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class FetchBody:
    body: bytes
    content_type: str
    status: int
    final_url: str = ""


@dataclass(frozen=True)
class ReportSpec:
    year: int
    url: str
    filename: str
    file_kind: str
    sheet_name: str | None = None
    expected_unavailable: bool = False


@dataclass(frozen=True)
class ParsedTrapReport:
    spec: ReportSpec
    raw_path: Path
    response: FetchBody
    trap_sites: list[dict[str, object]]
    observations: list[dict[str, object]]


@dataclass(frozen=True)
class DrosophilaSuzukiiOsuTrapReportsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    file_count: int
    parsed_trap_site_count: int
    parsed_trap_observation_count: int


REPORT_SPECS = [
    ReportSpec(
        year=2021,
        url="https://docs.google.com/spreadsheets/d/1KLU8rEoaz1Cnt9ILbUf77tSxOIriwZR0Xtj-wwNZgDA/gviz/tq?tqx=out:csv&sheet=Spotted-wing%20drosophila",
        filename="osu_swd_trap_report_2021_spotted_wing_drosophila.csv",
        file_kind="csv",
        sheet_name="Spotted-wing drosophila",
    ),
    ReportSpec(
        year=2020,
        url="https://u.osu.edu/pestmanagement/files/2021/05/Spotted-wing-drosophila-trapping-2020.xlsx",
        filename="osu_swd_trap_report_2020.xlsx",
        file_kind="xlsx",
        sheet_name="SWD 2020",
    ),
    ReportSpec(
        year=2019,
        url="https://u.osu.edu/pestmanagement/files/2020/03/Spotted-wing-drosophila-trapping-2019.xlsx",
        filename="osu_swd_trap_report_2019.xlsx",
        file_kind="xlsx",
        sheet_name="Sheet1",
    ),
    ReportSpec(
        year=2018,
        url="https://u.osu.edu/pestmanagement/files/2020/03/Spotted-wing-drosophila-trapping-2018.xlsx",
        filename="osu_swd_trap_report_2018.xlsx",
        file_kind="xlsx",
        sheet_name="Sheet1",
    ),
    ReportSpec(
        year=2017,
        url="https://u.osu.edu/pestmanagement/files/2016/05/Spotted-Wing-Drosophila-Trap-Reports-2017-11wn5is.xlsx",
        filename="osu_swd_trap_report_2017.xlsx",
        file_kind="xlsx",
        sheet_name="Sheet1",
    ),
    ReportSpec(
        year=2016,
        url="https://docs.google.com/spreadsheets/d/1qNQEBjIwxSTA3JYi00CuhzkkLAJtnkdczdfqeQD2IbQ/pub?output=csv",
        filename="osu_swd_trap_report_2016.csv",
        file_kind="csv",
    ),
    ReportSpec(
        year=2015,
        url="https://docs.google.com/spreadsheets/d/1g2sFMxG-EKJdBXdXyF1fFLUfCGp6piwwWvjv-IQEoWw/pub?output=csv",
        filename="osu_swd_trap_report_2015.csv",
        file_kind="csv",
        expected_unavailable=True,
    ),
]


def _default_fetch_body(url: str) -> FetchBody:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*"})
    with urlopen(request, timeout=90) as response:
        return FetchBody(
            body=response.read(),
            content_type=str(response.headers.get("content-type") or ""),
            status=int(getattr(response, "status", 200)),
            final_url=str(response.geturl()),
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_.:-]+", "_", text).strip("_") or "unknown"


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _cell_value(value: object) -> object:
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 8)
    return value


def _xlsx_namespaces() -> dict[str, str]:
    return {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }


def _xlsx_column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return max(index - 1, 0)


def _coerce_xlsx_scalar(text: str | None) -> object:
    if text is None:
        return None
    value = text.strip()
    if not value:
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else round(number, 8)


def _read_xlsx_shared_strings(zip_file: ZipFile) -> list[str]:
    try:
        xml = zip_file.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    ns = _xlsx_namespaces()
    strings: list[str] = []
    for item in root.findall("main:si", ns):
        strings.append("".join(node.text or "" for node in item.findall(".//main:t", ns)))
    return strings


def _read_xlsx_sheet_paths(zip_file: ZipFile) -> list[tuple[str, str]]:
    ns = _xlsx_namespaces()
    workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
    relationships = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib.get("Id"): rel.attrib.get("Target", "")
        for rel in relationships.findall("pkgrel:Relationship", ns)
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall("main:sheets/main:sheet", ns):
        sheet_name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get(f"{{{ns['rel']}}}id")
        target = rel_targets.get(rel_id, "")
        if not target:
            continue
        path = target.lstrip("/")
        if not path.startswith("xl/"):
            path = f"xl/{path}"
        sheets.append((sheet_name, path))
    return sheets


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> object:
    ns = _xlsx_namespaces()
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        raw_index = cell.findtext("main:v", default="", namespaces=ns)
        try:
            return shared_strings[int(raw_index)]
        except (ValueError, IndexError):
            return raw_index
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", ns))
    if cell_type == "b":
        return cell.findtext("main:v", default="", namespaces=ns) == "1"
    return _coerce_xlsx_scalar(cell.findtext("main:v", default="", namespaces=ns))


def _worksheet_rows(zip_file: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[object]]:
    ns = _xlsx_namespaces()
    root = ET.fromstring(zip_file.read(sheet_path))
    rows: list[list[object]] = []
    for row in root.findall(".//main:sheetData/main:row", ns):
        values: list[object] = []
        for cell in row.findall("main:c", ns):
            column_index = _xlsx_column_index(cell.attrib.get("r", ""))
            while len(values) <= column_index:
                values.append(None)
            values[column_index] = _xlsx_cell_value(cell, shared_strings)
        rows.append(values)
    return rows


def _rows_from_xlsx(path: Path, sheet_name: str | None = None) -> list[list[object]]:
    with ZipFile(path) as zip_file:
        shared_strings = _read_xlsx_shared_strings(zip_file)
        sheets = _read_xlsx_sheet_paths(zip_file)
        if sheet_name:
            selected = [sheet for sheet in sheets if sheet[0] == sheet_name]
            sheets = selected or sheets
        if not sheets:
            return []
        return _worksheet_rows(zip_file, sheets[0][1], shared_strings)


def _rows_from_csv(path: Path) -> list[list[object]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return [list(row) for row in csv.reader(io.StringIO(text))]


def _is_date_label(value: object) -> bool:
    text = _clean(value).lower()
    if not text:
        return False
    months = ("jan", "feb", "mar", "apr", "may", "june", "jun", "july", "jul", "aug", "sept", "sep", "oct", "nov", "dec")
    return any(month in text for month in months)


def _count_or_status(value: object) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value), None
    text = _clean(value)
    if not text:
        return None, None
    if re.fullmatch(r"-?\d+(\.0+)?", text):
        return int(float(text)), None
    return None, text


def _site_record(year: int, trap_index: int, fields: dict[str, object]) -> dict[str, object]:
    return {
        "year": year,
        "trap_index": trap_index,
        "county": _clean(fields.get("county")),
        "cooperator": _clean(fields.get("cooperator")),
        "farm": _clean(fields.get("farm")),
        "crop": _clean(fields.get("crop")),
        "trap_id": _clean(fields.get("trap_id")),
        "lure": _clean(fields.get("lure")),
    }


def _split_2021_site(text: str) -> dict[str, object]:
    parts = [part for part in _clean(text).split(" ") if part]
    if len(parts) <= 2:
        return {"county": parts[0] if parts else "", "farm": "", "cooperator": "", "crop": parts[-1] if parts else ""}
    county = parts[0]
    crop = parts[-1]
    middle = " ".join(parts[1:-1])
    return {"county": county, "farm": middle, "cooperator": middle, "crop": crop}


def _parse_vertical_report(rows: list[list[object]], spec: ReportSpec) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    header_index = None
    for index, row in enumerate(rows):
        labels = [_clean(cell).lower() for cell in row[:8]]
        if any(label in {"county", "location:", "location"} for label in labels) and any("trap" in label for label in labels):
            header_index = index
            break
    if header_index is None:
        for index, row in enumerate(rows):
            labels = [_clean(cell).lower() for cell in row[:8]]
            if labels[:5] and "cooperator" in labels and any("trap" in label for label in labels):
                header_index = index
                break
    if header_index is None:
        return [], []

    headers = [_clean(cell).lower().strip(":") for cell in rows[header_index]]
    date_columns = [(idx, _clean(value)) for idx, value in enumerate(rows[header_index]) if idx >= 5 and _is_date_label(value)]
    trap_sites: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        county = _clean(row[0] if len(row) > 0 else "")
        cooperator = _clean(row[1] if len(row) > 1 else "")
        crop = _clean(row[2] if len(row) > 2 else "")
        trap_id = _clean(row[3] if len(row) > 3 else "")
        lure = _clean(row[4] if len(row) > 4 else "")
        if not any((county, cooperator, crop, trap_id, lure)):
            continue
        trap_index = len(trap_sites) + 1
        trap_sites.append(_site_record(spec.year, trap_index, {"county": county, "cooperator": cooperator, "crop": crop, "trap_id": trap_id, "lure": lure}))
        for column_index, period in date_columns:
            value = row[column_index] if column_index < len(row) else None
            count, status = _count_or_status(value)
            if count is None and status is None:
                continue
            observations.append(
                {
                    "year": spec.year,
                    "trap_index": trap_index,
                    "period": period,
                    "count": count,
                    "status": status,
                    "raw_value": _clean(value),
                    "row_number": row_number,
                    "column_number": column_index + 1,
                    "county": county,
                    "cooperator": cooperator,
                    "crop": crop,
                    "trap_id": trap_id,
                    "lure": lure,
                    "layout": "vertical",
                }
            )
    return trap_sites, observations


def _metadata_row_index(rows: list[list[object]], label_terms: tuple[str, ...]) -> int | None:
    for index, row in enumerate(rows[:12]):
        first = _clean(row[0] if row else "").lower().strip(":")
        if first in label_terms:
            return index
    return None


def _parse_wide_report(rows: list[list[object]], spec: ReportSpec) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not rows:
        return [], []
    location_row = _metadata_row_index(rows, ("location", "county", "county farm cooperator crop"))
    cooperator_row = _metadata_row_index(rows, ("cooperator",))
    crop_row = _metadata_row_index(rows, ("crop",))
    trap_row = _metadata_row_index(rows, ("trap id/#", "trap number", "trap number"))
    lure_row = _metadata_row_index(rows, ("lure",))
    if location_row is None and rows and "county farm cooperator crop" in _clean(rows[0][0]).lower():
        location_row = 0
    if trap_row is None:
        trap_row = 1 if len(rows) > 1 and "trap" in _clean(rows[1][0]).lower() else None
    if lure_row is None:
        lure_row = 2 if len(rows) > 2 and "lure" in _clean(rows[2][0]).lower() else None
    if location_row is None or trap_row is None:
        return [], []

    max_width = max((len(row) for row in rows), default=0)
    trap_sites: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    column_to_trap: dict[int, dict[str, object]] = {}
    for column_index in range(1, max_width):
        location_text = _clean(rows[location_row][column_index] if column_index < len(rows[location_row]) else "")
        if not location_text:
            continue
        if cooperator_row is not None or crop_row is not None:
            fields = {
                "county": location_text,
                "cooperator": rows[cooperator_row][column_index] if cooperator_row is not None and column_index < len(rows[cooperator_row]) else "",
                "crop": rows[crop_row][column_index] if crop_row is not None and column_index < len(rows[crop_row]) else "",
            }
        else:
            fields = _split_2021_site(location_text)
        fields["trap_id"] = rows[trap_row][column_index] if column_index < len(rows[trap_row]) else ""
        fields["lure"] = rows[lure_row][column_index] if lure_row is not None and column_index < len(rows[lure_row]) else ""
        trap_index = len(trap_sites) + 1
        site = _site_record(spec.year, trap_index, fields)
        trap_sites.append(site)
        column_to_trap[column_index] = site

    data_start = max(index for index in (location_row, cooperator_row or 0, crop_row or 0, trap_row or 0, lure_row or 0) if index is not None) + 1
    for row_index, row in enumerate(rows[data_start:], start=data_start + 1):
        period = _clean(row[0] if row else "")
        if not _is_date_label(period):
            continue
        for column_index, site in column_to_trap.items():
            value = row[column_index] if column_index < len(row) else None
            count, status = _count_or_status(value)
            if count is None and status is None:
                continue
            observations.append(
                {
                    "year": spec.year,
                    "trap_index": site["trap_index"],
                    "period": period,
                    "count": count,
                    "status": status,
                    "raw_value": _clean(value),
                    "row_number": row_index,
                    "column_number": column_index + 1,
                    "county": site["county"],
                    "cooperator": site["cooperator"],
                    "farm": site["farm"],
                    "crop": site["crop"],
                    "trap_id": site["trap_id"],
                    "lure": site["lure"],
                    "layout": "wide",
                }
            )
    return trap_sites, observations


def _parse_report_rows(rows: list[list[object]], spec: ReportSpec) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    vertical_sites, vertical_observations = _parse_vertical_report(rows, spec)
    wide_sites, wide_observations = _parse_wide_report(rows, spec)
    if len(vertical_observations) >= len(wide_observations):
        return vertical_sites, vertical_observations
    return wide_sites, wide_observations


def _report_manifest_record(report: ParsedTrapReport, retrieved_at: str) -> EvidenceRecord:
    body = report.response.body
    payload = {
        "atom_type": "osu_swd_trap_report_file_manifest",
        "year": report.spec.year,
        "filename": report.spec.filename,
        "file_kind": report.spec.file_kind,
        "source_url": report.spec.url,
        "final_url": report.response.final_url,
        "content_type": report.response.content_type,
        "byte_size": len(body),
        "sha256": _sha256(body),
        "raw_path": report.raw_path.as_posix(),
        "trap_site_count": len(report.trap_sites),
        "trap_observation_count": len(report.observations),
    }
    return EvidenceRecord(
        record_id=f"swd_osu_trap_reports:file:{report.spec.year}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        title=f"Ohio State spotted-wing drosophila trap report file, {report.spec.year}",
        text=(
            f"Ohio State public spotted-wing drosophila trap report for {report.spec.year}. "
            f"Parsed {len(report.trap_sites)} trap sites and {len(report.observations)} trap-period observations."
        ),
        species=SPECIES,
        url=LANDING_URL,
        media_url=report.spec.url,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
            locator=report.raw_path.as_posix(),
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=report.spec.url,
        ),
        payload=payload,
    )


def _trap_site_record(site: dict[str, object], raw_path: Path, source_url: str, retrieved_at: str) -> EvidenceRecord:
    county = _clean(site.get("county"))
    crop = _clean(site.get("crop"))
    trap_id = _clean(site.get("trap_id"))
    year = int(site.get("year") or 0)
    trap_index = int(site.get("trap_index") or 0)
    payload = {"atom_type": "osu_swd_trap_site", **site}
    return EvidenceRecord(
        record_id=f"swd_osu_trap_reports:site:{year}:{trap_index:04d}:{_safe_id(county)}:{_safe_id(trap_id)}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        title=f"Ohio State SWD trap site {year}: {county} {crop} trap {trap_id}",
        text=(
            f"Ohio State spotted-wing drosophila trap site for {year}. "
            f"County: {county or 'not listed'}. Crop: {crop or 'not listed'}. Trap: {trap_id or 'not listed'}. "
            f"Lure: {_clean(site.get('lure')) or 'not listed'}."
        ),
        species=SPECIES,
        url=LANDING_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#trap/{trap_index}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=source_url,
        ),
        payload=payload,
    )


def _trap_observation_record(observation: dict[str, object], raw_path: Path, source_url: str, retrieved_at: str) -> EvidenceRecord:
    year = int(observation.get("year") or 0)
    trap_index = int(observation.get("trap_index") or 0)
    period = _clean(observation.get("period"))
    count = observation.get("count")
    status = _clean(observation.get("status"))
    county = _clean(observation.get("county"))
    crop = _clean(observation.get("crop"))
    trap_id = _clean(observation.get("trap_id"))
    value_text = f"count {count}" if count is not None else f"status {status}"
    payload = {"atom_type": "osu_swd_trap_observation", **observation}
    return EvidenceRecord(
        record_id=f"swd_osu_trap_reports:observation:{year}:{trap_index:04d}:{_safe_id(period)}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        title=f"Ohio State SWD trap observation {year} {period}: {county} {crop}",
        text=(
            f"Ohio State spotted-wing drosophila trap observation for {period} {year}: {value_text}. "
            f"County: {county or 'not listed'}. Crop: {crop or 'not listed'}. Trap: {trap_id or 'not listed'}."
        ),
        species=SPECIES,
        url=LANDING_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#row/{observation.get('row_number')}/column/{observation.get('column_number')}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=source_url,
        ),
        payload=payload,
    )


def _gap_record(spec: ReportSpec, *, reason: str, retrieved_at: str, error: str | None = None) -> EvidenceRecord:
    payload = {
        "atom_type": "source_gap",
        "reason": reason,
        "year": spec.year,
        "source_url": spec.url,
        "filename": spec.filename,
        "error": error,
    }
    return EvidenceRecord(
        record_id=f"swd_osu_trap_reports:gap:{spec.year}:{_safe_id(reason)}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        title=f"Ohio State SWD trap report gap {spec.year}: {reason}",
        text=f"Ohio State spotted-wing drosophila trap report gap for {spec.year}: {reason}.",
        species=SPECIES,
        url=LANDING_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
            locator=f"{LANDING_URL}#report/{spec.year}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=spec.url,
        ),
        payload=payload,
    )


def _gap_payload(record: EvidenceRecord) -> dict[str, object]:
    return {
        "source": DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        "lane": record.lane,
        "reason": str(record.payload.get("reason") if record.payload else "unknown"),
        "record_id": record.record_id,
        "locator": record.provenance.locator,
        "retrieved_at": record.provenance.retrieved_at,
    }


def fetch_drosophila_suzukii_osu_trap_report_records(
    *,
    raw_dir: Path,
    fetch_body: Callable[[str], FetchBody] | None = None,
    retrieved_at: str | None = None,
    report_specs: list[ReportSpec] | None = None,
) -> DrosophilaSuzukiiOsuTrapReportsResult:
    fetch = fetch_body or _default_fetch_body
    retrieved = retrieved_at or datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    specs = report_specs or REPORT_SPECS
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    parsed_trap_site_count = 0
    parsed_trap_observation_count = 0

    for spec in specs:
        requested_urls.append(spec.url)
        try:
            response = fetch(spec.url)
            if response.status >= 400 or not response.body:
                raise RuntimeError(f"HTTP {response.status}")
            if response.body[:64].lower().startswith(b"<!doctype html") and spec.expected_unavailable:
                raise RuntimeError("report returned HTML instead of tabular data")
            raw_path = raw_dir / spec.filename
            raw_path.write_bytes(response.body)
            raw_artifacts.append(raw_path.as_posix())
            rows = _rows_from_csv(raw_path) if spec.file_kind == "csv" else _rows_from_xlsx(raw_path, spec.sheet_name)
            trap_sites, observations = _parse_report_rows(rows, spec)
            if not trap_sites or not observations:
                raise RuntimeError("no trap rows parsed")
            report = ParsedTrapReport(spec=spec, raw_path=raw_path, response=response, trap_sites=trap_sites, observations=observations)
            records.append(_report_manifest_record(report, retrieved))
            records.extend(_trap_site_record(site, raw_path, spec.url, retrieved) for site in trap_sites)
            records.extend(_trap_observation_record(observation, raw_path, spec.url, retrieved) for observation in observations)
            parsed_trap_site_count += len(trap_sites)
            parsed_trap_observation_count += len(observations)
        except Exception as exc:
            reason = "osu_swd_trap_report_unavailable" if spec.expected_unavailable else "osu_swd_trap_report_fetch_or_parse_failed"
            gap = _gap_record(spec, reason=reason, retrieved_at=retrieved, error=str(exc))
            records.append(gap)
            gaps.append(_gap_payload(gap))

    return DrosophilaSuzukiiOsuTrapReportsResult(
        source_id=DROSOPHILA_SUZUKII_OSU_TRAP_REPORTS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        file_count=len(raw_artifacts),
        parsed_trap_site_count=parsed_trap_site_count,
        parsed_trap_observation_count=parsed_trap_observation_count,
    )
