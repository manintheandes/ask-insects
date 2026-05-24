from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import csv
from html import unescape
import io
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from askinsects.records import EvidenceRecord, Provenance


MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID = "mendeley_aedes_behavior_media"
MENDELEY_DATA_BASE = "https://data.mendeley.com"
MENDELEY_PUBLIC_API_BASE = f"{MENDELEY_DATA_BASE}/public-api"
USER_AGENT = "AskInsects/0.1 source-plane"
MEDIA_EXTENSIONS = (
    ".7z",
    ".avi",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
    ".webm",
    ".zip",
)
TABLE_EXTENSIONS = (".csv", ".tsv", ".xlsx")


@dataclass(frozen=True)
class MendeleyDatasetSpec:
    dataset_id: str
    version: int
    behavior_labels: tuple[str, ...]


DEFAULT_MENDELEY_DATASETS = (
    MendeleyDatasetSpec(
        dataset_id="6gvs94p6r2",
        version=1,
        behavior_labels=("mating", "mate recognition", "wing flash", "wingbeat", "acoustic signal", "high-speed video"),
    ),
    MendeleyDatasetSpec(
        dataset_id="g79w8wxpr7",
        version=2,
        behavior_labels=("hearing", "flight tones", "mate recognition", "wingbeat", "auditory system"),
    ),
    MendeleyDatasetSpec(
        dataset_id="sg5rrvdzvg",
        version=1,
        behavior_labels=("locomotory behavior", "temperature regime", "video analysis", "flight", "thermal response"),
    ),
)


@dataclass(frozen=True)
class MendeleyBehaviorMediaResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_datasets: list[str]
    dataset_count: int
    folder_count: int
    file_count: int
    media_file_count: int
    table_file_count: int = 0
    parsed_table_file_count: int = 0
    skipped_table_file_count: int = 0
    table_sheet_count: int = 0
    table_row_count: int = 0


@dataclass(frozen=True)
class ParsedTableSheet:
    name: str
    rows: list[list[str]]


class MendeleyClient:
    def __init__(self, fetch_json: Callable[[str], object] | None = None, fetch_bytes: Callable[[str], bytes] | None = None):
        self.fetch_json = fetch_json or self._fetch_json
        self.fetch_bytes = fetch_bytes or self._fetch_bytes

    def snapshot(self, dataset_id: str, version: int) -> tuple[str, dict[str, object]]:
        url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{quote(dataset_id)}/snapshot/{version}"
        payload = self.fetch_json(url)
        if not isinstance(payload, dict):
            raise ValueError(f"Mendeley snapshot returned non-object JSON for {url}")
        return url, payload

    def folders(self, dataset_id: str, version: int) -> tuple[str, list[dict[str, object]]]:
        url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{quote(dataset_id)}/folders/{version}"
        payload = self.fetch_json(url)
        if not isinstance(payload, list):
            raise ValueError(f"Mendeley folders returned non-list JSON for {url}")
        return url, [item for item in payload if isinstance(item, dict)]

    def files(self, dataset_id: str, version: int, folder_id: str) -> tuple[str, list[dict[str, object]]]:
        url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{quote(dataset_id)}/files?folder_id={quote(folder_id)}&version={version}"
        payload = self.fetch_json(url)
        if not isinstance(payload, list):
            raise ValueError(f"Mendeley files returned non-list JSON for {url}")
        return url, [item for item in payload if isinstance(item, dict)]

    def download_file(self, url: str) -> bytes:
        return self.fetch_bytes(url)

    @staticmethod
    def _fetch_json(url: str) -> object:
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.mendeley-public-dataset.1+json",
                "User-Agent": USER_AGENT,
            },
        )
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _fetch_bytes(url: str) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "*/*",
                "User-Agent": USER_AGENT,
            },
        )
        with urlopen(request, timeout=120) as response:
            return response.read()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "mendeley"


def _dataset_label(spec: MendeleyDatasetSpec) -> str:
    return f"{spec.dataset_id}:v{spec.version}"


def _dataset_web_url(snapshot: dict[str, object], spec: MendeleyDatasetSpec) -> str:
    dataset_id = str(snapshot.get("id") or spec.dataset_id)
    version = int(snapshot.get("version") or spec.version)
    return f"{MENDELEY_DATA_BASE}/datasets/{quote(dataset_id)}/{version}"


def _doi(snapshot: dict[str, object], spec: MendeleyDatasetSpec) -> str:
    doi = str(snapshot.get("doi") or "").strip()
    return doi or f"10.17632/{spec.dataset_id}.{spec.version}"


def _license(snapshot: dict[str, object]) -> str:
    licence = snapshot.get("licence")
    if isinstance(licence, dict):
        parts = [str(licence.get("short_name") or licence.get("full_name") or "").strip(), str(licence.get("url") or "").strip()]
        text = " ".join(part for part in parts if part)
        if text:
            return text
    license_value = snapshot.get("license")
    return str(license_value or "Mendeley Data license not supplied")


def _contributors(snapshot: dict[str, object]) -> str:
    contributors = snapshot.get("contributors")
    if not isinstance(contributors, list):
        return ""
    names = []
    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue
        name = " ".join(part for part in (contributor.get("first_name"), contributor.get("last_name")) if part)
        if name:
            names.append(name)
    return ", ".join(names[:8])


def _category_labels(snapshot: dict[str, object]) -> list[str]:
    categories = snapshot.get("categories")
    if not isinstance(categories, list):
        return []
    labels = []
    for category in categories:
        if isinstance(category, dict) and category.get("label"):
            labels.append(str(category["label"]))
    return labels


def _folder_path(folder: dict[str, object], folder_by_id: dict[str, dict[str, object]]) -> str:
    names = []
    seen: set[str] = set()
    current: dict[str, object] | None = folder
    while current:
        folder_id = str(current.get("id") or "")
        if folder_id in seen:
            break
        seen.add(folder_id)
        name = str(current.get("name") or folder_id or "folder")
        if name:
            names.append(name)
        parent_id = current.get("parent_id")
        current = folder_by_id.get(str(parent_id)) if parent_id else None
    return "/".join(reversed(names))


def _file_folder_path(file_payload: dict[str, object], folder_paths: dict[str, str]) -> str:
    folder_id = file_payload.get("folder_id")
    if folder_id and str(folder_id) in folder_paths:
        return folder_paths[str(folder_id)]
    return "root"


def _content_details(file_payload: dict[str, object]) -> dict[str, object]:
    details = file_payload.get("content_details")
    return details if isinstance(details, dict) else {}


def _is_media_file(filename: str, content_type: str) -> bool:
    lower = filename.lower()
    ctype = content_type.lower()
    return lower.endswith(MEDIA_EXTENSIONS) or ctype.startswith("video/") or ctype.startswith("audio/") or "zip" in ctype


def _is_table_file(filename: str, content_type: str) -> bool:
    lower = filename.lower()
    ctype = content_type.lower()
    return (
        lower.endswith(TABLE_EXTENSIONS)
        or "csv" in ctype
        or "tab-separated-values" in ctype
        or "spreadsheetml" in ctype
    )


def _is_aedes_aegypti_table_file(spec: MendeleyDatasetSpec, filename: str) -> bool:
    lower = filename.lower().replace(" ", "").replace("_", "")
    if spec.dataset_id == "sg5rrvdzvg" and "japonicus" in lower and "aegypti" not in lower:
        return False
    return True


def _table_file_path(raw_dir: Path, spec: MendeleyDatasetSpec, file_payload: dict[str, object], filename: str) -> Path:
    suffix = Path(filename).suffix.lower() or ".table"
    file_token = str(file_payload.get("id") or filename)
    return raw_dir / "table_files" / f"{_safe_id(spec.dataset_id)}_v{spec.version}_{_safe_id(file_token)}{suffix}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xlsx_text(element: ET.Element) -> str:
    values = [node.text or "" for node in element.iter() if _local_name(node.tag) == "t"]
    return "".join(values).strip()


def _xlsx_shared_strings(zip_file: ZipFile) -> list[str]:
    try:
        with zip_file.open("xl/sharedStrings.xml") as handle:
            root = ET.parse(handle).getroot()
    except KeyError:
        return []
    strings = []
    for item in root.iter():
        if _local_name(item.tag) == "si":
            strings.append(_xlsx_text(item))
    return strings


def _xlsx_sheet_targets(zip_file: ZipFile) -> list[tuple[str, str]]:
    with zip_file.open("xl/workbook.xml") as handle:
        workbook = ET.parse(handle).getroot()
    rels: dict[str, str] = {}
    try:
        with zip_file.open("xl/_rels/workbook.xml.rels") as handle:
            rels_root = ET.parse(handle).getroot()
        for rel in rels_root:
            rel_id = str(rel.attrib.get("Id") or "")
            target = str(rel.attrib.get("Target") or "")
            if target:
                rels[rel_id] = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
    except KeyError:
        pass
    sheets = []
    for sheet in workbook.iter():
        if _local_name(sheet.tag) != "sheet":
            continue
        name = str(sheet.attrib.get("name") or f"Sheet {len(sheets) + 1}")
        rid = next((value for key, value in sheet.attrib.items() if key.endswith("}id") or key == "id"), "")
        target = rels.get(str(rid)) or f"xl/worksheets/sheet{len(sheets) + 1}.xml"
        sheets.append((name, target))
    return sheets


def _xlsx_column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Za-z]", "", cell_ref).upper()
    if not letters:
        return 0
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(0, index - 1)


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _xlsx_text(cell)
    value = ""
    for child in cell:
        if _local_name(child.tag) == "v":
            value = child.text or ""
            break
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return value
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value.strip()


def _parse_xlsx(path: Path) -> list[ParsedTableSheet]:
    sheets = []
    with ZipFile(path) as zip_file:
        shared_strings = _xlsx_shared_strings(zip_file)
        for sheet_name, target in _xlsx_sheet_targets(zip_file):
            try:
                with zip_file.open(target) as handle:
                    root = ET.parse(handle).getroot()
            except KeyError:
                continue
            rows = []
            for row in root.iter():
                if _local_name(row.tag) != "row":
                    continue
                values: list[str] = []
                for cell in row:
                    if _local_name(cell.tag) != "c":
                        continue
                    column = _xlsx_column_index(str(cell.attrib.get("r") or ""))
                    while len(values) <= column:
                        values.append("")
                    values[column] = _xlsx_cell_value(cell, shared_strings)
                rows.append(values)
            sheets.append(ParsedTableSheet(name=sheet_name, rows=rows))
    return sheets


def _decode_table_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_delimited(path: Path, filename: str) -> list[ParsedTableSheet]:
    text = _decode_table_bytes(path.read_bytes())
    sample = text[:4096]
    delimiter = "\t" if filename.lower().endswith(".tsv") else ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = dialect.delimiter
    except csv.Error:
        pass
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [ParsedTableSheet(name="table", rows=[[cell.strip() for cell in row] for row in reader])]


def _parse_table(path: Path, filename: str) -> list[ParsedTableSheet]:
    if filename.lower().endswith(".xlsx"):
        return _parse_xlsx(path)
    return _parse_delimited(path, filename)


def _is_blank_row(row: list[str]) -> bool:
    return not any(str(value).strip() for value in row)


def _looks_numeric(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


def _looks_like_header(row: list[str]) -> bool:
    cells = [cell.strip() for cell in row if cell.strip()]
    if not cells:
        return False
    numeric_count = sum(1 for cell in cells if _looks_numeric(cell))
    return numeric_count < len(cells)


def _dedupe_headers(row: list[str], width: int) -> list[str]:
    headers = []
    seen: dict[str, int] = {}
    for index in range(width):
        raw = row[index].strip() if index < len(row) else ""
        base = raw or f"column_{index + 1}"
        key = re.sub(r"\s+", " ", base)
        count = seen.get(key, 0) + 1
        seen[key] = count
        headers.append(key if count == 1 else f"{key}_{count}")
    return headers


def _table_layout(rows: list[list[str]]) -> tuple[list[str], list[tuple[int, list[str]]]]:
    indexed_rows = [(index, row) for index, row in enumerate(rows, start=1) if not _is_blank_row(row)]
    if not indexed_rows:
        return [], []
    width = max(len(row) for _, row in indexed_rows)
    first_index, first_row = indexed_rows[0]
    if _looks_like_header(first_row):
        headers = _dedupe_headers(first_row, width)
        data_rows = indexed_rows[1:]
    else:
        headers = [f"column_{index + 1}" for index in range(width)]
        data_rows = indexed_rows
    return headers, data_rows


def _row_values(headers: list[str], row: list[str]) -> dict[str, str]:
    values = {}
    for index, header in enumerate(headers):
        value = row[index].strip() if index < len(row) else ""
        if value:
            values[header] = value
    return values


def _format_row_values(values: dict[str, str], *, max_columns: int = 16) -> str:
    parts = []
    for index, (key, value) in enumerate(values.items()):
        if index >= max_columns:
            parts.append("...")
            break
        clean_value = re.sub(r"\s+", " ", value).strip()
        if len(clean_value) > 120:
            clean_value = f"{clean_value[:117]}..."
        parts.append(f"{key}: {clean_value}")
    return "; ".join(parts)


def _dataset_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot_url: str,
    folders_url: str,
    snapshot: dict[str, object],
    raw_path: Path,
    folder_count: int,
    file_count: int,
    media_file_count: int,
    retrieved_at: str,
) -> EvidenceRecord:
    title = _clean_text(snapshot.get("name")) or f"Mendeley Aedes aegypti behavior dataset {spec.dataset_id}"
    description = _clean_text(snapshot.get("description"))
    labels = ", ".join(spec.behavior_labels)
    contributors = _contributors(snapshot)
    categories = ", ".join(_category_labels(snapshot))
    text_parts = [
        f"Mendeley Data dataset for Aedes aegypti behavior/media evidence: {title}.",
        f"Behavior labels: {labels}.",
        f"Manifest: {folder_count} folder(s), {file_count} file(s), including {media_file_count} video/audio/archive file(s).",
    ]
    if contributors:
        text_parts.append(f"Contributors: {contributors}.")
    if categories:
        text_parts.append(f"Categories: {categories}.")
    if description:
        text_parts.append(f"Description: {description[:700]}")
    return EvidenceRecord(
        record_id=f"mendeley:dataset:{_safe_id(spec.dataset_id)}:v{spec.version}",
        lane="behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley behavior dataset {title}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#snapshot",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=snapshot_url,
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "snapshot_api_url": snapshot_url,
            "folders_api_url": folders_url,
            "behavior_labels": list(spec.behavior_labels),
            "raw_snapshot": snapshot,
        },
    )


def _folder_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    folder: dict[str, object],
    folder_path: str,
    raw_path: Path,
    folder_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    title = _clean_text(snapshot.get("name")) or _doi(snapshot, spec)
    folder_name = str(folder.get("name") or folder.get("id") or "folder")
    labels = ", ".join(spec.behavior_labels)
    return EvidenceRecord(
        record_id=f"mendeley:folder:{_safe_id(spec.dataset_id)}:v{spec.version}:{_safe_id(str(folder.get('id') or folder_index))}",
        lane="behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley dataset folder {folder_path}",
        text=(
            f"Mendeley Data folder for Aedes aegypti behavior/media dataset {title}. "
            f"Folder: {folder_name}. Path: {folder_path}. Behavior labels: {labels}."
        ),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#folders/{folder_index}",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=_dataset_web_url(snapshot, spec),
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "folder_id": folder.get("id"),
            "folder_path": folder_path,
            "parent_id": folder.get("parent_id"),
            "behavior_labels": list(spec.behavior_labels),
            "raw_folder": folder,
        },
    )


def _file_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    file_payload: dict[str, object],
    folder_path: str,
    raw_path: Path,
    folder_id: str,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    dataset_title = _clean_text(snapshot.get("name")) or _doi(snapshot, spec)
    filename = str(file_payload.get("filename") or f"file-{file_index}")
    details = _content_details(file_payload)
    content_type = str(details.get("content_type") or "")
    media = _is_media_file(filename, content_type)
    download_url = str(details.get("download_url") or "")
    view_url = str(details.get("view_url") or "")
    source_url = download_url or view_url or _dataset_web_url(snapshot, spec)
    size = details.get("size") if details.get("size") is not None else file_payload.get("size")
    sha256_hash = str(details.get("sha256_hash") or "")
    labels = ", ".join(spec.behavior_labels)
    title_kind = "video/audio/archive file" if media else "behavior data file"
    text_parts = [
        f"Mendeley {title_kind} for Aedes aegypti behavior/media dataset {dataset_title}.",
        f"File: {filename}.",
        f"Folder path: {folder_path}.",
        f"Behavior labels: {labels}.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if content_type:
        text_parts.append(f"Content type: {content_type}.")
    if sha256_hash:
        text_parts.append(f"SHA-256: {sha256_hash}.")
    return EvidenceRecord(
        record_id=f"mendeley:file:{_safe_id(spec.dataset_id)}:v{spec.version}:{_safe_id(str(file_payload.get('id') or filename))}",
        lane="media" if media else "behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley {title_kind} {filename}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=download_url if media and download_url else None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#files/{folder_id}/{file_index}",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=source_url,
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "dataset_title": dataset_title,
            "file_id": file_payload.get("id"),
            "filename": filename,
            "folder_id": file_payload.get("folder_id"),
            "folder_path": folder_path,
            "content_type": content_type,
            "size": size,
            "sha256_hash": sha256_hash,
            "download_url": download_url,
            "view_url": view_url,
            "behavior_labels": list(spec.behavior_labels),
            "raw_file": file_payload,
        },
    )


def _table_sheet_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    file_payload: dict[str, object],
    filename: str,
    folder_path: str,
    table_path: Path,
    sheet_name: str,
    sheet_index: int,
    headers: list[str],
    data_rows: list[tuple[int, list[str]]],
    retrieved_at: str,
) -> EvidenceRecord:
    dataset_title = _clean_text(snapshot.get("name")) or _doi(snapshot, spec)
    file_id = str(file_payload.get("id") or filename)
    sample_rows = [_row_values(headers, row) for _, row in data_rows[:3]]
    labels = ", ".join(spec.behavior_labels)
    return EvidenceRecord(
        record_id=(
            f"mendeley:table:{_safe_id(spec.dataset_id)}:v{spec.version}:"
            f"{_safe_id(file_id)}:{_safe_id(sheet_name or str(sheet_index))}"
        ),
        lane="behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley parsed behavior table {filename} sheet {sheet_name}",
        text=(
            f"Parsed Mendeley behavior table for Aedes aegypti dataset {dataset_title}. "
            f"File: {filename}. Sheet: {sheet_name}. Folder path: {folder_path}. "
            f"Rows: {len(data_rows)}. Columns: {len(headers)}. Behavior labels: {labels}. "
            f"Headers: {', '.join(headers[:24])}."
        ),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{table_path.as_posix()}#sheet/{sheet_index}",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=str(_content_details(file_payload).get("download_url") or _dataset_web_url(snapshot, spec)),
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "dataset_title": dataset_title,
            "file_id": file_payload.get("id"),
            "filename": filename,
            "folder_path": folder_path,
            "sheet_name": sheet_name,
            "sheet_index": sheet_index,
            "row_count": len(data_rows),
            "column_count": len(headers),
            "headers": headers,
            "sample_rows": sample_rows,
            "behavior_labels": list(spec.behavior_labels),
            "download_url": str(_content_details(file_payload).get("download_url") or ""),
        },
    )


def _table_row_record(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    file_payload: dict[str, object],
    filename: str,
    table_path: Path,
    sheet_name: str,
    sheet_index: int,
    row_number: int,
    row_values: dict[str, str],
    retrieved_at: str,
) -> EvidenceRecord:
    dataset_title = _clean_text(snapshot.get("name")) or _doi(snapshot, spec)
    file_id = str(file_payload.get("id") or filename)
    formatted_values = _format_row_values(row_values)
    return EvidenceRecord(
        record_id=(
            f"mendeley:table-row:{_safe_id(spec.dataset_id)}:v{spec.version}:"
            f"{_safe_id(file_id)}:{_safe_id(sheet_name or str(sheet_index))}:r{row_number}"
        ),
        lane="behavior",
        source=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        title=f"Aedes aegypti Mendeley behavior table row {filename} {sheet_name} row {row_number}",
        text=(
            f"Parsed Mendeley Aedes aegypti behavior table row from dataset {dataset_title}. "
            f"File: {filename}. Sheet: {sheet_name}. Row: {row_number}. Values: {formatted_values}."
        ),
        species="Aedes aegypti",
        url=_dataset_web_url(snapshot, spec),
        media_url=None,
        provenance=Provenance(
            source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
            locator=f"{table_path.as_posix()}#sheet/{sheet_index}/row/{row_number}",
            retrieved_at=retrieved_at,
            license=_license(snapshot),
            source_url=str(_content_details(file_payload).get("download_url") or _dataset_web_url(snapshot, spec)),
        ),
        payload={
            "dataset_id": spec.dataset_id,
            "version": spec.version,
            "doi": _doi(snapshot, spec),
            "dataset_title": dataset_title,
            "file_id": file_payload.get("id"),
            "filename": filename,
            "sheet_name": sheet_name,
            "sheet_index": sheet_index,
            "row_number": row_number,
            "values": row_values,
            "download_url": str(_content_details(file_payload).get("download_url") or ""),
        },
    )


def _table_records(
    *,
    spec: MendeleyDatasetSpec,
    snapshot: dict[str, object],
    file_payload: dict[str, object],
    folder_path: str,
    table_path: Path,
    filename: str,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], int, int]:
    records: list[EvidenceRecord] = []
    sheets = _parse_table(table_path, filename)
    sheet_count = 0
    row_count = 0
    for sheet_index, sheet in enumerate(sheets, start=1):
        headers, data_rows = _table_layout(sheet.rows)
        if not headers:
            continue
        sheet_count += 1
        row_count += len(data_rows)
        records.append(
            _table_sheet_record(
                spec=spec,
                snapshot=snapshot,
                file_payload=file_payload,
                filename=filename,
                folder_path=folder_path,
                table_path=table_path,
                sheet_name=sheet.name,
                sheet_index=sheet_index,
                headers=headers,
                data_rows=data_rows,
                retrieved_at=retrieved_at,
            )
        )
        for row_number, row in data_rows:
            values = _row_values(headers, row)
            if not values:
                continue
            records.append(
                _table_row_record(
                    spec=spec,
                    snapshot=snapshot,
                    file_payload=file_payload,
                    filename=filename,
                    table_path=table_path,
                    sheet_name=sheet.name,
                    sheet_index=sheet_index,
                    row_number=row_number,
                    row_values=values,
                    retrieved_at=retrieved_at,
                )
            )
    return records, sheet_count, row_count


def fetch_mendeley_behavior_media_records(
    dataset_specs: list[MendeleyDatasetSpec] | tuple[MendeleyDatasetSpec, ...] = DEFAULT_MENDELEY_DATASETS,
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], object] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
    retrieved_at: str | None = None,
) -> MendeleyBehaviorMediaResult:
    retrieved = retrieved_at or utc_now()
    client = MendeleyClient(fetch_json, fetch_bytes)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    total_folders = 0
    total_files = 0
    total_media_files = 0
    total_table_files = 0
    total_parsed_table_files = 0
    total_skipped_table_files = 0
    total_table_sheets = 0
    total_table_rows = 0

    for spec in dataset_specs:
        safe_dataset = f"{_safe_id(spec.dataset_id)}_v{spec.version}"
        try:
            snapshot_url, snapshot = client.snapshot(spec.dataset_id, spec.version)
            snapshot_raw_path = write_raw_json(raw_dir, f"{safe_dataset}_snapshot.json", snapshot)
            raw_artifacts.append(snapshot_raw_path.as_posix())
            folders_url, folders = client.folders(spec.dataset_id, spec.version)
            folders_raw_path = write_raw_json(raw_dir, f"{safe_dataset}_folders.json", folders)
            raw_artifacts.append(folders_raw_path.as_posix())
        except Exception as exc:
            gaps.append(
                {
                    "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
                    "lane": "behavior",
                    "dataset_id": spec.dataset_id,
                    "version": spec.version,
                    "reason": "mendeley_dataset_fetch_failed",
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
            continue

        folder_by_id = {str(folder.get("id")): folder for folder in folders if folder.get("id")}
        folder_paths = {folder_id: _folder_path(folder, folder_by_id) for folder_id, folder in folder_by_id.items()}
        files_payloads: list[dict[str, object]] = []
        for folder_id in ("root", *folder_by_id):
            try:
                files_url, files = client.files(spec.dataset_id, spec.version, folder_id)
            except Exception as exc:
                gaps.append(
                    {
                        "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
                        "lane": "media",
                        "dataset_id": spec.dataset_id,
                        "version": spec.version,
                        "folder_id": folder_id,
                        "reason": "mendeley_file_manifest_fetch_failed",
                        "error": str(exc),
                        "retrieved_at": retrieved,
                    }
                )
                files = []
                files_url = f"{MENDELEY_PUBLIC_API_BASE}/datasets/{spec.dataset_id}/files?folder_id={folder_id}&version={spec.version}"
            files_payloads.append({"folder_id": folder_id, "url": files_url, "files": files})

        files_raw_path = write_raw_json(raw_dir, f"{safe_dataset}_files.json", files_payloads)
        raw_artifacts.append(files_raw_path.as_posix())
        files_flat = [
            (str(item["folder_id"]), index, file_payload)
            for item in files_payloads
            for index, file_payload in enumerate(item["files"], start=1)
            if isinstance(file_payload, dict)
        ]
        media_file_count = sum(
            1
            for _, _, file_payload in files_flat
            if _is_media_file(str(file_payload.get("filename") or ""), str(_content_details(file_payload).get("content_type") or ""))
        )
        total_folders += len(folders)
        total_files += len(files_flat)
        total_media_files += media_file_count
        records.append(
            _dataset_record(
                spec=spec,
                snapshot_url=snapshot_url,
                folders_url=folders_url,
                snapshot=snapshot,
                raw_path=snapshot_raw_path,
                folder_count=len(folders),
                file_count=len(files_flat),
                media_file_count=media_file_count,
                retrieved_at=retrieved,
            )
        )
        for index, folder in enumerate(folders, start=1):
            folder_id = str(folder.get("id") or index)
            records.append(
                _folder_record(
                    spec=spec,
                    snapshot=snapshot,
                    folder=folder,
                    folder_path=folder_paths.get(folder_id, str(folder.get("name") or folder_id)),
                    raw_path=folders_raw_path,
                    folder_index=index,
                    retrieved_at=retrieved,
                )
            )
        for folder_id, file_index, file_payload in files_flat:
            filename = str(file_payload.get("filename") or f"file-{file_index}")
            details = _content_details(file_payload)
            folder_path = _file_folder_path(file_payload, folder_paths) if folder_id == "root" else folder_paths.get(folder_id, folder_id)
            records.append(
                _file_record(
                    spec=spec,
                    snapshot=snapshot,
                    file_payload=file_payload,
                    folder_path=folder_path,
                    raw_path=files_raw_path,
                    folder_id=folder_id,
                    file_index=file_index,
                    retrieved_at=retrieved,
                )
            )
            if not _is_table_file(filename, str(details.get("content_type") or "")):
                continue
            total_table_files += 1
            if not _is_aedes_aegypti_table_file(spec, filename):
                total_skipped_table_files += 1
                continue
            download_url = str(details.get("download_url") or "")
            if not download_url:
                gaps.append(
                    {
                        "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
                        "lane": "behavior",
                        "dataset_id": spec.dataset_id,
                        "version": spec.version,
                        "file_id": file_payload.get("id"),
                        "filename": filename,
                        "reason": "mendeley_table_file_missing_download_url",
                        "retrieved_at": retrieved,
                    }
                )
                continue
            table_path = _table_file_path(raw_dir, spec, file_payload, filename)
            table_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                table_path.write_bytes(client.download_file(download_url))
                raw_artifacts.append(table_path.as_posix())
                table_records, sheet_count, row_count = _table_records(
                    spec=spec,
                    snapshot=snapshot,
                    file_payload=file_payload,
                    folder_path=folder_path,
                    table_path=table_path,
                    filename=filename,
                    retrieved_at=retrieved,
                )
            except Exception as exc:
                gaps.append(
                    {
                        "source": MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
                        "lane": "behavior",
                        "dataset_id": spec.dataset_id,
                        "version": spec.version,
                        "file_id": file_payload.get("id"),
                        "filename": filename,
                        "reason": "mendeley_table_file_parse_failed",
                        "error": str(exc),
                        "retrieved_at": retrieved,
                    }
                )
                continue
            records.extend(table_records)
            total_parsed_table_files += 1
            total_table_sheets += sheet_count
            total_table_rows += row_count

    return MendeleyBehaviorMediaResult(
        source_id=MENDELEY_BEHAVIOR_MEDIA_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_datasets=[_dataset_label(spec) for spec in dataset_specs],
        dataset_count=len([record for record in records if record.record_id.startswith("mendeley:dataset:")]),
        folder_count=total_folders,
        file_count=total_files,
        media_file_count=total_media_files,
        table_file_count=total_table_files,
        parsed_table_file_count=total_parsed_table_files,
        skipped_table_file_count=total_skipped_table_files,
        table_sheet_count=total_table_sheets,
        table_row_count=total_table_rows,
    )
