from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Callable
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID = "drosophila_suzukii_dryad_landscape_monitoring"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
DRYAD_BASE = "https://datadryad.org"
DATASET_DOI = "doi:10.5061/dryad.52c2k52"
DATASET_URL = f"{DRYAD_BASE}/dataset/doi%3A10.5061/dryad.52c2k52"
DATASET_API_URL = f"{DRYAD_BASE}/api/v2/datasets/doi%3A10.5061%2Fdryad.52c2k52"
VERSION_API_URL = f"{DRYAD_BASE}/api/v2/versions/13824/files"
PRIMARY_ARTICLE_DOI = "10.1016/j.agee.2018.11.014"
LICENSE = "CC0-1.0"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class DryadLandscapeMonitoringResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    row_count: int
    file_count: int
    gap_count: int


class _PreviewTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._current_row: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        if tag in {"th", "td"}:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._in_cell:
            if self._current_row is not None:
                self._current_row.append(_clean(" ".join(self._cell_parts)))
            self._in_cell = False
            self._cell_parts = []
        if tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", _clean(value)).strip("_") or "unknown"


def _float(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: object) -> int | None:
    number = _float(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else None


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _default_fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/javascript, application/javascript, */*;q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": DRYAD_BASE,
        },
    )
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _write_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(raw_dir: Path, filename: str, payload: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(payload, encoding="utf-8")
    return path


def _files_from_version_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    embedded = payload.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    files = embedded.get("stash:files")
    return [file for file in files if isinstance(file, dict)] if isinstance(files, list) else []


def _link(payload: dict[str, object], rel: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, dict):
        return None
    item = links.get(rel)
    if not isinstance(item, dict):
        return None
    href = item.get("href")
    if not href:
        return None
    return str(href) if str(href).startswith("http") else f"{DRYAD_BASE}{href}"


def _file_id(file_payload: dict[str, object]) -> str:
    self_url = _link(file_payload, "self") or ""
    match = re.search(r"/files/([0-9]+)\b", self_url)
    return match.group(1) if match else _safe_id(file_payload.get("path"))


def _preview_url(file_payload: dict[str, object]) -> str:
    return f"{DRYAD_BASE}/data_file/preview/{_file_id(file_payload)}.js"


def _parse_preview_rows(preview_js: str) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    parser = _PreviewTableParser()
    parser.feed(preview_js)
    parser.close()
    rows = [row for row in parser.rows if any(cell for cell in row)]
    if not rows:
        return [], []
    headers = [header or f"column_{index + 1}" for index, header in enumerate(rows[0])]
    parsed: list[tuple[int, dict[str, str]]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        values = {
            headers[index]: row[index]
            for index in range(min(len(headers), len(row)))
            if row[index] != ""
        }
        if values:
            parsed.append((row_number, values))
    return headers, parsed


def _predator_counts(values: dict[str, str]) -> dict[str, int]:
    metadata_fields = {
        "Week",
        "Gdate",
        "fieldcd",
        "Field ID",
        "Treatment",
        "Transect",
        "veg",
        "PropNoncrop",
        "PropBBtot",
        "FRAGEdge",
        "FRAGSHDI",
        "chgNP",
        "chgF",
        "SWD",
    }
    counts: dict[str, int] = {}
    for key, value in values.items():
        if key in metadata_fields:
            continue
        count = _int(value)
        if count is not None:
            counts[key] = count
    return counts


def _dataset_manifest_record(dataset: dict[str, object], raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    payload = {
        "atom_type": "dryad_landscape_dataset_manifest",
        "dataset_doi": DATASET_DOI,
        "primary_article_doi": PRIMARY_ARTICLE_DOI,
        "title": dataset.get("title"),
        "license": dataset.get("license"),
        "publication_date": dataset.get("publicationDate"),
        "storage_size": dataset.get("storageSize"),
        "usage_notes": _clean(dataset.get("usageNotes")),
        "locations": dataset.get("locations"),
        "raw_path": raw_path.as_posix(),
    }
    return EvidenceRecord(
        record_id="swd_dryad_landscape_monitoring:dataset:52c2k52",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        title="Dryad southeast U.S. blueberry landscape monitoring dataset for Drosophila suzukii",
        text=(
            "Dryad dataset for Drosophila suzukii activity and natural enemy abundance in southeast U.S. "
            "blueberry systems. The file description states that SWD is trap counts for Drosophila suzukii."
        ),
        species=SPECIES,
        url=DATASET_URL,
        media_url=DATASET_API_URL,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
            locator=raw_path.as_posix(),
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=DATASET_API_URL,
        ),
        payload=payload,
    )


def _file_manifest_record(file_payload: dict[str, object], raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    download_url = _link(file_payload, "stash:download")
    preview_url = _preview_url(file_payload)
    payload = {
        "atom_type": "dryad_landscape_file_manifest",
        "dataset_doi": DATASET_DOI,
        "file_id": _file_id(file_payload),
        "file_path": file_payload.get("path"),
        "mime_type": file_payload.get("mimeType"),
        "byte_size": file_payload.get("size"),
        "digest": file_payload.get("digest"),
        "digest_type": file_payload.get("digestType"),
        "description": file_payload.get("description"),
        "download_url": download_url,
        "preview_url": preview_url,
        "raw_path": raw_path.as_posix(),
    }
    return EvidenceRecord(
        record_id=f"swd_dryad_landscape_monitoring:file:{_safe_id(file_payload.get('path'))}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        title=f"Dryad SWD landscape monitoring file {file_payload.get('path')}",
        text=(
            f"Dryad file manifest for {file_payload.get('path')}. "
            "The source description identifies SWD as trap counts for Drosophila suzukii."
        ),
        species=SPECIES,
        url=DATASET_URL,
        media_url=download_url,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
            locator=raw_path.as_posix(),
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=download_url,
        ),
        payload=payload,
    )


def _row_record(file_payload: dict[str, object], row_number: int, values: dict[str, str], preview_path: Path, retrieved_at: str) -> EvidenceRecord:
    week = _clean(values.get("Week"))
    date = _clean(values.get("Gdate"))
    field_id = _clean(values.get("Field ID") or values.get("fieldcd"))
    treatment = _clean(values.get("Treatment"))
    transect = _clean(values.get("Transect"))
    swd_count = _int(values.get("SWD"))
    predator_counts = _predator_counts(values)
    payload = {
        "atom_type": "dryad_landscape_monitoring_row",
        "dataset_doi": DATASET_DOI,
        "primary_article_doi": PRIMARY_ARTICLE_DOI,
        "file_path": file_payload.get("path"),
        "row_number": row_number,
        "week": week,
        "date": date,
        "field_code": _clean(values.get("fieldcd")),
        "field_id": field_id,
        "treatment": treatment,
        "transect": transect,
        "vegetation_between_rows": _clean(values.get("veg")),
        "proportion_noncrop_1km": _float(values.get("PropNoncrop")),
        "proportion_blueberry_1km": _float(values.get("PropBBtot")),
        "edge_density": _float(values.get("FRAGEdge")),
        "landscape_composition_shannon": _float(values.get("FRAGSHDI")),
        "change_noncrop": _float(values.get("chgNP")),
        "change_forest": _float(values.get("chgF")),
        "swd_trap_count": swd_count,
        "predator_counts": predator_counts,
        "row_values": values,
    }
    return EvidenceRecord(
        record_id=f"swd_dryad_landscape_monitoring:row:{row_number:04d}:{_safe_id(field_id)}:{_safe_id(transect)}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        title=f"Southeast U.S. blueberry SWD monitoring row {row_number}: field {field_id}, week {week}",
        text=(
            f"Dryad southeast U.S. blueberry monitoring row for Drosophila suzukii. "
            f"Date: {date or 'not listed'}. Week: {week or 'not listed'}. Field: {field_id or 'not listed'}. "
            f"Treatment: {treatment or 'not listed'}. Transect: {transect or 'not listed'}. "
            f"SWD trap count: {swd_count if swd_count is not None else 'not listed'}. "
            f"Natural enemy taxa counted: {len(predator_counts)}."
        ),
        species=SPECIES,
        url=DATASET_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
            locator=f"{preview_path.as_posix()}#row/{row_number}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=_preview_url(file_payload),
        ),
        payload=payload,
    )


def _gap_record(reason: str, retrieved_at: str, *, locator: str, source_url: str | None = None, error: str | None = None) -> EvidenceRecord:
    payload = {
        "atom_type": "source_gap",
        "reason": reason,
        "dataset_doi": DATASET_DOI,
        "primary_article_doi": PRIMARY_ARTICLE_DOI,
        "source_url": source_url,
        "error": error,
    }
    return EvidenceRecord(
        record_id=f"swd_dryad_landscape_monitoring:gap:{_safe_id(reason)}",
        lane="ecology",
        source=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        title=f"Dryad SWD landscape monitoring gap: {reason}",
        text=f"Dryad SWD landscape monitoring source gap: {reason}.",
        species=SPECIES,
        url=DATASET_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
            locator=locator,
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=source_url,
        ),
        payload=payload,
    )


def _gap_payload(record: EvidenceRecord) -> dict[str, object]:
    return {
        "source": record.source,
        "lane": record.lane,
        "reason": str(record.payload.get("reason") if record.payload else "unknown"),
        "record_id": record.record_id,
        "locator": record.provenance.locator,
        "retrieved_at": record.provenance.retrieved_at,
    }


def fetch_drosophila_suzukii_dryad_landscape_monitoring_records(
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    fetch_text: Callable[[str], str] | None = None,
    retrieved_at: str | None = None,
) -> DryadLandscapeMonitoringResult:
    json_fetcher = fetch_json or _default_fetch_json
    text_fetcher = fetch_text or _default_fetch_text
    retrieved = retrieved_at or utc_now()
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    row_count = 0
    file_count = 0

    try:
        dataset = json_fetcher(DATASET_API_URL)
        dataset_path = _write_json(raw_dir, "dryad_52c2k52_dataset.json", dataset)
        raw_artifacts.append(dataset_path.as_posix())
        records.append(_dataset_manifest_record(dataset, dataset_path, retrieved))
    except Exception as exc:
        gap = _gap_record(
            "dryad_landscape_dataset_metadata_fetch_failed",
            retrieved,
            locator=f"{DATASET_API_URL}#metadata",
            source_url=DATASET_API_URL,
            error=str(exc),
        )
        records.append(gap)
        gaps.append(_gap_payload(gap))
        return DryadLandscapeMonitoringResult(
            source_id=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
            records=records,
            gaps=gaps,
            raw_artifacts=raw_artifacts,
            row_count=0,
            file_count=0,
            gap_count=len(gaps),
        )

    try:
        files_payload = json_fetcher(VERSION_API_URL)
        files_path = _write_json(raw_dir, "dryad_52c2k52_files.json", files_payload)
        raw_artifacts.append(files_path.as_posix())
        files = _files_from_version_payload(files_payload)
    except Exception as exc:
        gap = _gap_record(
            "dryad_landscape_file_manifest_fetch_failed",
            retrieved,
            locator=f"{VERSION_API_URL}#files",
            source_url=VERSION_API_URL,
            error=str(exc),
        )
        records.append(gap)
        gaps.append(_gap_payload(gap))
        files = []

    for file_payload in files:
        if _clean(file_payload.get("path")).lower() != "schmidtetalaee_dyrad.csv":
            continue
        file_count += 1
        records.append(_file_manifest_record(file_payload, files_path, retrieved))
        preview_url = _preview_url(file_payload)
        try:
            preview = text_fetcher(preview_url)
            preview_path = _write_text(raw_dir, "dryad_52c2k52_schmidtetalAEE_dyrad_preview.js", preview)
            raw_artifacts.append(preview_path.as_posix())
            headers, rows = _parse_preview_rows(preview)
            if not headers or not rows:
                raise RuntimeError("public preview did not contain tabular rows")
            for row_number, values in rows:
                records.append(_row_record(file_payload, row_number, values, preview_path, retrieved))
                row_count += 1
            gap = _gap_record(
                "dryad_landscape_full_csv_download_blocked_preview_used",
                retrieved,
                locator=f"{preview_path.as_posix()}#preview",
                source_url=preview_url,
            )
            records.append(gap)
            gaps.append(_gap_payload(gap))
        except Exception as exc:
            gap = _gap_record(
                "dryad_landscape_preview_fetch_or_parse_failed",
                retrieved,
                locator=f"{preview_url}#preview",
                source_url=preview_url,
                error=str(exc),
            )
            records.append(gap)
            gaps.append(_gap_payload(gap))

    if file_count == 0:
        gap = _gap_record(
            "dryad_landscape_csv_file_not_found",
            retrieved,
            locator=f"{VERSION_API_URL}#files",
            source_url=VERSION_API_URL,
        )
        records.append(gap)
        gaps.append(_gap_payload(gap))

    return DryadLandscapeMonitoringResult(
        source_id=DROSOPHILA_SUZUKII_DRYAD_LANDSCAPE_MONITORING_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        row_count=row_count,
        file_count=file_count,
        gap_count=len(gaps),
    )
