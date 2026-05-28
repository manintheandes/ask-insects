from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
from html import unescape
import io
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from askinsects.records import EvidenceRecord, Provenance


DRYAD_BEHAVIOR_VIDEO_SOURCE_ID = "dryad_aedes_behavior_videos"
DRYAD_API_BASE = "https://datadryad.org"
USER_AGENT = "AskInsects/0.1 source-plane"
MEDIA_EXTENSIONS = (".zip", ".mp4", ".mov", ".avi", ".webm", ".m4v")
TABLE_EXTENSIONS = (".csv", ".tsv", ".xlsx")
DEFAULT_MAX_TABLE_BYTES = 10_000_000
DEFAULT_MAX_TABLE_ROWS_PER_FILE = 5000
DEFAULT_LIVE_REQUEST_DELAY_SECONDS = 2.1
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class DryadDatasetSpec:
    doi: str
    behavior_labels: tuple[str, ...]


DEFAULT_DRYAD_DATASETS = (
    DryadDatasetSpec(
        doi="10.5061/dryad.547d7wmh3",
        behavior_labels=("host seeking", "thermal infrared", "human odor", "CO2", "navigation"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.j6q573nr3",
        behavior_labels=("host seeking", "visual threat avoidance", "shadow response", "escape"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.ttdz08m09",
        behavior_labels=("flight", "looming threat escape", "light condition", "evasive maneuver"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.qz612jmrb",
        behavior_labels=("mating", "courtship", "hearing", "wingbeat", "flight"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.tb2rbp04x",
        behavior_labels=("male host attraction", "female host attraction", "landing", "human preference", "repellent response"),
    ),
    DryadDatasetSpec(
        doi="10.5061/dryad.z8w9ghxfv",
        behavior_labels=("tethered flight", "visual tracking", "CO2", "blood feeding", "oviposition state"),
    ),
)


@dataclass(frozen=True)
class DryadBehaviorVideoResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_dois: list[str]
    dataset_count: int
    file_count: int
    media_file_count: int
    table_file_count: int = 0
    parsed_table_file_count: int = 0
    skipped_table_file_count: int = 0
    table_sheet_count: int = 0
    table_row_count: int = 0
    landing_page_count: int = 0
    assay_method_count: int = 0


@dataclass(frozen=True)
class ParsedTableSheet:
    name: str
    rows: list[list[str]]


class DryadClient:
    def __init__(
        self,
        fetch_json: Callable[[str], dict[str, object]] | None = None,
        fetch_bytes: Callable[[str], bytes] | None = None,
        fetch_text: Callable[[str], str] | None = None,
        request_delay_seconds: float = 0.0,
    ):
        self.fetch_json = fetch_json or self._fetch_json
        self.fetch_bytes = fetch_bytes or self._fetch_bytes
        self.fetch_text = fetch_text or self._fetch_text
        self.request_delay_seconds = request_delay_seconds

    def dataset(self, doi: str) -> tuple[str, dict[str, object]]:
        url = f"{DRYAD_API_BASE}/api/v2/datasets/{quote(f'doi:{doi}', safe='')}"
        self._throttle()
        return url, self.fetch_json(url)

    def linked(self, href: str) -> tuple[str, dict[str, object]]:
        url = urljoin(DRYAD_API_BASE, href)
        self._throttle()
        return url, self.fetch_json(url)

    def download_file(self, url: str) -> bytes:
        self._throttle()
        return self.fetch_bytes(url)

    def landing_page(self, doi: str) -> tuple[str, str]:
        url = _dataset_web_url(doi)
        self._throttle()
        return url, self.fetch_text(url)

    def _throttle(self) -> None:
        if self.request_delay_seconds > 0:
            time.sleep(self.request_delay_seconds)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, object]:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Dryad endpoint returned non-object JSON for {url}")
        return payload

    @staticmethod
    def _fetch_bytes(url: str) -> bytes:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read()

    @staticmethod
    def _fetch_text(url: str) -> str:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_raw_text(raw_dir: Path, filename: str, payload: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(payload, encoding="utf-8")
    return path


def read_raw_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"cached raw JSON is not an object: {path}")
    return payload


def _clean_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "dryad"


def _link(payload: dict[str, object], rel: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, dict):
        return None
    link = links.get(rel)
    if not isinstance(link, dict):
        return None
    href = link.get("href")
    return str(href) if href else None


def _file_rows(files_payload: dict[str, object]) -> list[dict[str, object]]:
    embedded = files_payload.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    files = embedded.get("stash:files")
    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, dict)]


def _is_media_file(path: str, mime_type: str) -> bool:
    lower = path.lower()
    return lower.endswith(MEDIA_EXTENSIONS) or "zip" in mime_type.lower() or mime_type.lower().startswith("video/")


def _is_table_file(path: str, mime_type: str) -> bool:
    lower = path.lower()
    mime = mime_type.lower()
    return lower.endswith(TABLE_EXTENSIONS) or "csv" in mime or "tab-separated-values" in mime or "spreadsheetml" in mime


def _is_aedes_aegypti_table_file(path: str) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", path.lower())
    comparison_species = ("notoscriptus", "vigilax", "albopictus")
    return not any(species in compact for species in comparison_species) or "aegypti" in compact


def _authors(dataset_payload: dict[str, object]) -> str:
    authors = dataset_payload.get("authors")
    if not isinstance(authors, list):
        return ""
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in (author.get("firstName"), author.get("lastName")) if part)
        if name:
            names.append(name)
    return ", ".join(names[:8])


def _doi_from_identifier(dataset_payload: dict[str, object], fallback: str) -> str:
    identifier = str(dataset_payload.get("identifier") or "")
    if identifier.startswith("doi:"):
        return identifier.removeprefix("doi:")
    return fallback


def _dataset_web_url(doi: str) -> str:
    return f"{DRYAD_API_BASE}/dataset/{quote(f'doi:{doi}', safe='')}"


def _file_id(file_payload: dict[str, object]) -> str | None:
    for rel in ("self", "stash:download"):
        href = _link(file_payload, rel)
        if not href:
            continue
        match = re.search(r"/files/(?P<file_id>\d+)(?:/download)?$", href)
        if match:
            return match.group("file_id")
    return None


def _file_stream_url(file_payload: dict[str, object]) -> str | None:
    file_id = _file_id(file_payload)
    if not file_id:
        return None
    return f"{DRYAD_API_BASE}/downloads/file_stream/{file_id}"


class _DryadLandingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture_tag: str | None = None
        self._capture_parts: list[str] = []
        self.blocks: list[tuple[str, str]] = []
        self.file_stream_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        href = attrs_dict.get("href")
        if href and "/downloads/file_stream/" in href:
            self.file_stream_links.append(urljoin(DRYAD_API_BASE, href))
        if tag in {"h3", "h4", "h5", "p", "li"}:
            self._flush()
            self._capture_tag = tag
            self._capture_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._capture_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._capture_tag:
            self._flush()

    def _flush(self) -> None:
        if not self._capture_tag:
            return
        text = re.sub(r"\s+", " ", " ".join(self._capture_parts)).strip()
        if text:
            self.blocks.append((self._capture_tag, text))
        self._capture_tag = None
        self._capture_parts = []


def _parse_landing_page(html: str) -> tuple[list[dict[str, str]], list[str]]:
    parser = _DryadLandingParser()
    parser.feed(html)
    parser.close()
    parser._flush()
    sections: list[dict[str, str]] = []
    current_heading = ""
    section_parts: list[str] = []
    for tag, text in parser.blocks:
        if tag in {"h3", "h4", "h5"}:
            if current_heading and section_parts:
                sections.append({"heading": current_heading, "text": " ".join(section_parts)})
            current_heading = text
            section_parts = []
            continue
        if current_heading and _is_behavior_method_text(text):
            section_parts.append(text)
    if current_heading and section_parts:
        sections.append({"heading": current_heading, "text": " ".join(section_parts)})
    return sections, sorted(set(parser.file_stream_links))


def _is_behavior_method_text(text: str) -> bool:
    lower = text.lower()
    method_terms = (
        "aedes",
        "mosquito",
        "assay",
        "experiment",
        "trial",
        "host",
        "repellent",
        "olfactometer",
        "tent",
        "landing",
        "flight",
        "visual",
        "tracking",
        "co2",
        "blood",
        "filmed",
        "recorded",
        "observation",
    )
    return any(term in lower for term in method_terms)


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
    delimiter = "\t" if filename.lower().endswith(".tsv") else ","
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        pass
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [ParsedTableSheet(name="table", rows=[[cell.strip() for cell in row] for row in reader])]


def _parse_table(path: Path, filename: str) -> list[ParsedTableSheet]:
    if filename.lower().endswith(".xlsx"):
        return _parse_xlsx(path)
    return _parse_delimited(path, filename)


def _is_blank_row(row: list[str]) -> bool:
    return not any(value.strip() for value in row)


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
    _, first_row = indexed_rows[0]
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


def _table_file_path(raw_dir: Path, doi: str, file_payload: dict[str, object], filename: str) -> Path:
    suffix = Path(filename).suffix.lower() or ".table"
    file_token = str(file_payload.get("id") or file_payload.get("path") or filename)
    return raw_dir / "table_files" / f"{_safe_id(doi)}_{_safe_id(file_token)}{suffix}"


def _dataset_record(
    *,
    spec: DryadDatasetSpec,
    dataset_url: str,
    dataset_payload: dict[str, object],
    version_url: str,
    files_url: str,
    raw_path: Path,
    file_count: int,
    media_file_count: int,
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    title = _clean_text(dataset_payload.get("title")) or f"Dryad Aedes aegypti behavior dataset {doi}"
    labels = ", ".join(spec.behavior_labels)
    authors = _authors(dataset_payload)
    abstract = _clean_text(dataset_payload.get("abstract"))
    text_parts = [
        f"Dryad dataset for Aedes aegypti behavior/video evidence: {title}.",
        f"Behavior labels: {labels}.",
        f"File manifest: {file_count} file(s), including {media_file_count} media/archive file(s).",
    ]
    if authors:
        text_parts.append(f"Authors: {authors}.")
    if abstract:
        text_parts.append(f"Abstract: {abstract[:700]}")
    return EvidenceRecord(
        record_id=f"dryad:dataset:{_safe_id(doi)}",
        lane="behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad behavior dataset {title}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#dataset",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=dataset_url,
        ),
        payload={
            "doi": doi,
            "dataset_api_url": dataset_url,
            "version_api_url": version_url,
            "files_api_url": files_url,
            "behavior_labels": list(spec.behavior_labels),
            "raw_dataset": dataset_payload,
        },
    )


def _file_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    raw_path: Path,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    file_path = str(file_payload.get("path") or f"file-{file_index}")
    mime_type = str(file_payload.get("mimeType") or "")
    media = _is_media_file(file_path, mime_type)
    download_href = _link(file_payload, "stash:download")
    api_download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else _dataset_web_url(doi)
    file_stream_url = _file_stream_url(file_payload)
    size = file_payload.get("size")
    digest = file_payload.get("digest")
    digest_type = file_payload.get("digestType")
    labels = ", ".join(spec.behavior_labels)
    title_kind = "video/archive file" if media else "behavior data file"
    text_parts = [
        f"Dryad {title_kind} for Aedes aegypti behavior dataset {dataset_title}.",
        f"File path: {file_path}.",
        f"Behavior labels: {labels}.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if mime_type:
        text_parts.append(f"MIME type: {mime_type}.")
    if digest and digest_type:
        text_parts.append(f"Checksum: {digest_type} {digest}.")
    return EvidenceRecord(
        record_id=f"dryad:file:{_safe_id(doi)}:{_safe_id(file_path)}",
        lane="media" if media else "behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad {title_kind} {file_path}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=api_download_url if media else None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#file/{file_index}",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=file_stream_url or api_download_url,
        ),
        payload={
            "doi": doi,
            "dataset_title": dataset_title,
            "behavior_labels": list(spec.behavior_labels),
            "raw_file": file_payload,
            "download_url": api_download_url,
            "api_download_url": api_download_url,
            "file_stream_url": file_stream_url,
        },
    )


def _archive_decode_gap_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    raw_path: Path,
    file_index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    file_path = str(file_payload.get("path") or f"file-{file_index}")
    mime_type = str(file_payload.get("mimeType") or "")
    download_href = _link(file_payload, "stash:download")
    download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else _dataset_web_url(doi)
    file_stream_url = _file_stream_url(file_payload)
    size = file_payload.get("size")
    digest = file_payload.get("digest")
    digest_type = file_payload.get("digestType")
    labels = ", ".join(spec.behavior_labels)
    source_video_record_id = f"dryad:file:{_safe_id(doi)}:{_safe_id(file_path)}"
    text_parts = [
        "Aedes aegypti Dryad video source gap: dryad_archive_contents_not_decoded.",
        f"Source dataset: {dataset_title}.",
        f"Source file: {file_path}.",
        f"Behavior labels: {labels}.",
        "The downloadable file is manifest-indexed, but its archive contents are not yet expanded into per-video assets, keyframes, previews, frame manifests, or motion rows.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if mime_type:
        text_parts.append(f"MIME type: {mime_type}.")
    if digest and digest_type:
        text_parts.append(f"Checksum: {digest_type} {digest}.")
    return EvidenceRecord(
        record_id=f"dryad:gap:{_safe_id(doi)}:{_safe_id(file_path)}:archive_contents_not_decoded",
        lane="media",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad video gap archive contents not decoded {file_path}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#file/{file_index}/gap/archive_contents_not_decoded",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=download_url,
        ),
        payload={
            "atom_type": "video_gap",
            "reason": "dryad_archive_contents_not_decoded",
            "repository": "dryad",
            "doi": doi,
            "dataset_title": dataset_title,
            "file_path": file_path,
            "mime_type": mime_type,
            "byte_size": size,
            "source_hash": digest,
            "source_hash_type": digest_type,
            "download_url": download_url,
            "file_stream_url": file_stream_url,
            "source_video_record_id": source_video_record_id,
            "behavior_labels": list(spec.behavior_labels),
            "required_next_artifacts": [
                "archive_member_manifest",
                "per_video_asset_rows",
                "duration_fps_resolution_codec_probe_rows",
                "thumbnail_keyframe_preview_frame_manifest_rows",
                "source_table_or_motion_tracking_rows_when_available",
            ],
        },
    )


def _table_sheet_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    filename: str,
    table_path: Path,
    sheet_name: str,
    sheet_index: int,
    headers: list[str],
    data_rows: list[tuple[int, list[str]]],
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    sample_rows = [_row_values(headers, row) for _, row in data_rows[:3]]
    labels = ", ".join(spec.behavior_labels)
    download_href = _link(file_payload, "stash:download")
    download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else _dataset_web_url(doi)
    return EvidenceRecord(
        record_id=(
            f"dryad:table:{_safe_id(doi)}:{_safe_id(filename)}:"
            f"{_safe_id(sheet_name or str(sheet_index))}"
        ),
        lane="behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad parsed behavior table {filename} sheet {sheet_name}",
        text=(
            f"Parsed Dryad behavior table for Aedes aegypti dataset {dataset_title}. "
            f"File: {filename}. Sheet: {sheet_name}. Rows: {len(data_rows)}. "
            f"Columns: {len(headers)}. Behavior labels: {labels}. Headers: {', '.join(headers[:24])}."
        ),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{table_path.as_posix()}#sheet/{sheet_index}",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=download_url,
        ),
        payload={
            "doi": doi,
            "dataset_title": dataset_title,
            "filename": filename,
            "sheet_name": sheet_name,
            "sheet_index": sheet_index,
            "row_count": len(data_rows),
            "column_count": len(headers),
            "headers": headers,
            "sample_rows": sample_rows,
            "behavior_labels": list(spec.behavior_labels),
            "download_url": download_url,
            "file_stream_url": _file_stream_url(file_payload),
        },
    )


def _table_row_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    filename: str,
    table_path: Path,
    sheet_name: str,
    sheet_index: int,
    row_number: int,
    row_values: dict[str, str],
    retrieved_at: str,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    formatted_values = _format_row_values(row_values)
    download_href = _link(file_payload, "stash:download")
    download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else _dataset_web_url(doi)
    return EvidenceRecord(
        record_id=(
            f"dryad:table-row:{_safe_id(doi)}:{_safe_id(filename)}:"
            f"{_safe_id(sheet_name or str(sheet_index))}:r{row_number}"
        ),
        lane="behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad behavior table row {filename} {sheet_name} row {row_number}",
        text=(
            f"Parsed Dryad Aedes aegypti behavior table row from dataset {dataset_title}. "
            f"File: {filename}. Sheet: {sheet_name}. Row: {row_number}. Values: {formatted_values}."
        ),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{table_path.as_posix()}#sheet/{sheet_index}/row/{row_number}",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=download_url,
        ),
        payload={
            "doi": doi,
            "dataset_title": dataset_title,
            "filename": filename,
            "sheet_name": sheet_name,
            "sheet_index": sheet_index,
            "row_number": row_number,
            "values": row_values,
            "download_url": download_url,
            "file_stream_url": _file_stream_url(file_payload),
            "behavior_labels": list(spec.behavior_labels),
        },
    )


def _landing_assay_method_records(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    landing_url: str,
    landing_path: Path,
    html: str,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    sections, file_stream_links = _parse_landing_page(html)
    records: list[EvidenceRecord] = []
    labels = ", ".join(spec.behavior_labels)
    for index, section in enumerate(sections[:40], start=1):
        heading = section.get("heading") or "Dryad landing page method"
        method_text = re.sub(r"\s+", " ", section.get("text") or "").strip()
        if not method_text:
            continue
        digest = hashlib.sha1(f"{doi}|{heading}|{method_text}".encode("utf-8")).hexdigest()[:12]
        text = (
            f"Dryad landing-page assay metadata for Aedes aegypti dataset {dataset_title}. "
            f"Section: {heading}. Behavior labels: {labels}. Method text: {method_text[:1200]}"
        )
        records.append(
            EvidenceRecord(
                record_id=f"dryad:assay-method:{_safe_id(doi)}:{digest}",
                lane="behavior",
                source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                title=f"Aedes aegypti Dryad assay metadata {heading}",
                text=text,
                species="Aedes aegypti",
                url=landing_url,
                media_url=None,
                provenance=Provenance(
                    source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                    locator=f"{landing_path.as_posix()}#assay-method/{index}",
                    retrieved_at=retrieved_at,
                    license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
                    source_url=landing_url,
                ),
                payload={
                    "record_type": "dryad_landing_assay_method",
                    "doi": doi,
                    "dataset_title": dataset_title,
                    "heading": heading,
                    "method_text": method_text,
                    "behavior_labels": list(spec.behavior_labels),
                    "landing_page_url": landing_url,
                    "file_stream_links": file_stream_links,
                },
            )
        )
    return records


def _table_records(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    table_path: Path,
    filename: str,
    retrieved_at: str,
    max_table_rows_per_file: int,
) -> tuple[list[EvidenceRecord], int, int]:
    records: list[EvidenceRecord] = []
    sheets = _parse_table(table_path, filename)
    sheet_count = 0
    row_count = 0
    rows_remaining = max_table_rows_per_file
    for sheet_index, sheet in enumerate(sheets, start=1):
        if rows_remaining <= 0:
            break
        headers, data_rows = _table_layout(sheet.rows)
        if not headers:
            continue
        bounded_rows = data_rows[:rows_remaining]
        sheet_count += 1
        row_count += len(bounded_rows)
        rows_remaining -= len(bounded_rows)
        records.append(
            _table_sheet_record(
                spec=spec,
                dataset_payload=dataset_payload,
                file_payload=file_payload,
                filename=filename,
                table_path=table_path,
                sheet_name=sheet.name,
                sheet_index=sheet_index,
                headers=headers,
                data_rows=bounded_rows,
                retrieved_at=retrieved_at,
            )
        )
        for row_number, row in bounded_rows:
            values = _row_values(headers, row)
            if not values:
                continue
            records.append(
                _table_row_record(
                    spec=spec,
                    dataset_payload=dataset_payload,
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


def _table_gap_record(
    *,
    spec: DryadDatasetSpec,
    dataset_payload: dict[str, object],
    file_payload: dict[str, object],
    files_raw_path: Path,
    file_index: int,
    filename: str,
    reason: str,
    retrieved_at: str,
    error: str | None = None,
) -> EvidenceRecord:
    doi = _doi_from_identifier(dataset_payload, spec.doi)
    dataset_title = _clean_text(dataset_payload.get("title")) or doi
    download_href = _link(file_payload, "stash:download")
    download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else ""
    size = file_payload.get("size")
    digest = file_payload.get("digest")
    digest_type = file_payload.get("digestType")
    labels = ", ".join(spec.behavior_labels)
    text_parts = [
        f"Aedes aegypti Dryad table source gap: {reason}.",
        f"Source dataset: {dataset_title}.",
        f"Source file: {filename}.",
        f"Behavior labels: {labels}.",
        "The table is present in the Dryad file manifest, but Ask Insects has not parsed it into row-level behavior records.",
    ]
    if size is not None:
        text_parts.append(f"Size bytes: {size}.")
    if digest and digest_type:
        text_parts.append(f"Checksum: {digest_type} {digest}.")
    if error:
        text_parts.append(f"Error: {error}.")
    return EvidenceRecord(
        record_id=f"dryad:table-gap:{_safe_id(doi)}:{_safe_id(filename)}:{_safe_id(reason)}",
        lane="behavior",
        source=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        title=f"Aedes aegypti Dryad behavior table gap {filename}",
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=_dataset_web_url(doi),
        media_url=None,
        provenance=Provenance(
            source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
            locator=f"{files_raw_path.as_posix()}#file/{file_index}/gap/{reason}",
            retrieved_at=retrieved_at,
            license=str(dataset_payload.get("license") or "Dryad dataset license not supplied"),
            source_url=download_url or _dataset_web_url(doi),
        ),
        payload={
            "atom_type": "table_gap",
            "reason": reason,
            "doi": doi,
            "dataset_title": dataset_title,
            "filename": filename,
            "byte_size": size,
            "source_hash": digest,
            "source_hash_type": digest_type,
            "download_url": download_url,
            "behavior_labels": list(spec.behavior_labels),
            "error": error,
        },
    )


def fetch_dryad_behavior_video_records(
    dataset_specs: list[DryadDatasetSpec] | tuple[DryadDatasetSpec, ...] = DEFAULT_DRYAD_DATASETS,
    *,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
    fetch_text: Callable[[str], str] | None = None,
    retrieved_at: str | None = None,
    max_table_bytes: int = DEFAULT_MAX_TABLE_BYTES,
    max_table_rows_per_file: int = DEFAULT_MAX_TABLE_ROWS_PER_FILE,
    request_delay_seconds: float | None = None,
) -> DryadBehaviorVideoResult:
    retrieved = retrieved_at or utc_now()
    delay = 0.0 if (fetch_json or fetch_bytes) else DEFAULT_LIVE_REQUEST_DELAY_SECONDS
    if request_delay_seconds is not None:
        delay = request_delay_seconds
    client = DryadClient(fetch_json, fetch_bytes, fetch_text, request_delay_seconds=delay)
    fetch_landing_pages = fetch_text is not None or (fetch_json is None and fetch_bytes is None)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    file_count = 0
    media_file_count = 0
    table_file_count = 0
    parsed_table_file_count = 0
    skipped_table_file_count = 0
    table_sheet_count = 0
    table_row_count = 0
    landing_page_count = 0
    assay_method_count = 0

    for spec in dataset_specs:
        safe_doi = _safe_id(spec.doi)
        dataset_raw_path = raw_dir / f"{safe_doi}_dataset.json"
        version_raw_path = raw_dir / f"{safe_doi}_version.json"
        files_raw_path = raw_dir / f"{safe_doi}_files.json"
        landing_raw_path = raw_dir / f"{safe_doi}_landing.html"
        try:
            dataset_url, dataset_payload = client.dataset(spec.doi)
            dataset_raw_path = write_raw_json(raw_dir, dataset_raw_path.name, dataset_payload)
            raw_artifacts.append(dataset_raw_path.as_posix())
            version_href = _link(dataset_payload, "stash:version")
            if not version_href:
                raise ValueError("Dryad dataset payload did not include a stash:version link")
            version_url, version_payload = client.linked(version_href)
            version_raw_path = write_raw_json(raw_dir, version_raw_path.name, version_payload)
            raw_artifacts.append(version_raw_path.as_posix())
            files_href = _link(version_payload, "stash:files")
            if not files_href:
                raise ValueError("Dryad version payload did not include a stash:files link")
            files_url, files_payload = client.linked(files_href)
            files_raw_path = write_raw_json(raw_dir, files_raw_path.name, files_payload)
            raw_artifacts.append(files_raw_path.as_posix())
            files = _file_rows(files_payload)
        except Exception as exc:
            used_cached_raw = False
            if dataset_raw_path.exists() and version_raw_path.exists() and files_raw_path.exists():
                try:
                    dataset_payload = read_raw_json(dataset_raw_path)
                    version_payload = read_raw_json(version_raw_path)
                    files_payload = read_raw_json(files_raw_path)
                    dataset_url = f"{DRYAD_API_BASE}/api/v2/datasets/{quote(f'doi:{spec.doi}', safe='')}"
                    version_href = _link(dataset_payload, "stash:version") or ""
                    files_href = _link(version_payload, "stash:files") or ""
                    version_url = urljoin(DRYAD_API_BASE, version_href) if version_href else dataset_url
                    files_url = urljoin(DRYAD_API_BASE, files_href) if files_href else version_url
                    raw_artifacts.extend([dataset_raw_path.as_posix(), version_raw_path.as_posix(), files_raw_path.as_posix()])
                    files = _file_rows(files_payload)
                    gaps.append(
                        {
                            "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                            "lane": "media",
                            "doi": spec.doi,
                            "reason": "dryad_live_fetch_failed_used_cached_raw",
                            "error": str(exc),
                            "retrieved_at": retrieved,
                        }
                    )
                    used_cached_raw = True
                except Exception:
                    used_cached_raw = False
            if not used_cached_raw:
                gaps.append(
                    {
                        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                        "lane": "media",
                        "doi": spec.doi,
                        "reason": "dryad_dataset_fetch_failed",
                        "error": str(exc),
                        "retrieved_at": retrieved,
                    }
                )
                continue

        dataset_media_count = sum(
            1 for row in files if _is_media_file(str(row.get("path") or ""), str(row.get("mimeType") or ""))
        )
        records.append(
            _dataset_record(
                spec=spec,
                dataset_url=dataset_url,
                dataset_payload=dataset_payload,
                version_url=version_url,
                files_url=files_url,
                raw_path=dataset_raw_path,
                file_count=len(files),
                media_file_count=dataset_media_count,
                retrieved_at=retrieved,
            )
        )
        if not files:
            gaps.append(
                {
                    "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                    "lane": "media",
                    "doi": spec.doi,
                    "reason": "dryad_file_manifest_empty",
                    "retrieved_at": retrieved,
                }
            )
        if fetch_landing_pages:
            try:
                landing_url, landing_html = client.landing_page(_doi_from_identifier(dataset_payload, spec.doi))
                landing_raw_path = write_raw_text(raw_dir, landing_raw_path.name, landing_html)
                raw_artifacts.append(landing_raw_path.as_posix())
                landing_page_count += 1
                landing_records = _landing_assay_method_records(
                    spec=spec,
                    dataset_payload=dataset_payload,
                    landing_url=landing_url,
                    landing_path=landing_raw_path,
                    html=landing_html,
                    retrieved_at=retrieved,
                )
                assay_method_count += len(landing_records)
                records.extend(landing_records)
            except Exception as exc:
                gaps.append(
                    {
                        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                        "lane": "behavior",
                        "doi": _doi_from_identifier(dataset_payload, spec.doi),
                        "reason": "dryad_landing_page_fetch_failed",
                        "error": str(exc),
                        "retrieved_at": retrieved,
                    }
                )
        for index, file_payload in enumerate(files, start=1):
            file_count += 1
            filename = str(file_payload.get("path") or f"file-{index}")
            mime_type = str(file_payload.get("mimeType") or "")
            is_media = _is_media_file(filename, mime_type)
            if is_media:
                media_file_count += 1
            records.append(
                _file_record(
                    spec=spec,
                    dataset_payload=dataset_payload,
                    file_payload=file_payload,
                    raw_path=files_raw_path,
                    file_index=index,
                    retrieved_at=retrieved,
                )
            )
            if is_media:
                records.append(
                    _archive_decode_gap_record(
                        spec=spec,
                        dataset_payload=dataset_payload,
                        file_payload=file_payload,
                        raw_path=files_raw_path,
                        file_index=index,
                        retrieved_at=retrieved,
                    )
                )
            if not _is_table_file(filename, mime_type):
                continue
            table_file_count += 1
            if not _is_aedes_aegypti_table_file(filename):
                skipped_table_file_count += 1
                continue
            size = file_payload.get("size")
            if isinstance(size, int) and size > max_table_bytes:
                skipped_table_file_count += 1
                records.append(
                    _table_gap_record(
                        spec=spec,
                        dataset_payload=dataset_payload,
                        file_payload=file_payload,
                        files_raw_path=files_raw_path,
                        file_index=index,
                        filename=filename,
                        reason="dryad_table_file_too_large",
                        retrieved_at=retrieved,
                    )
                )
                gaps.append(
                    {
                        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                        "lane": "behavior",
                        "doi": _doi_from_identifier(dataset_payload, spec.doi),
                        "filename": filename,
                        "reason": "dryad_table_file_too_large",
                        "byte_size": size,
                        "max_table_bytes": max_table_bytes,
                        "retrieved_at": retrieved,
                    }
                )
                continue
            download_href = _link(file_payload, "stash:download")
            download_url = urljoin(DRYAD_API_BASE, download_href) if download_href else ""
            if not download_url:
                skipped_table_file_count += 1
                records.append(
                    _table_gap_record(
                        spec=spec,
                        dataset_payload=dataset_payload,
                        file_payload=file_payload,
                        files_raw_path=files_raw_path,
                        file_index=index,
                        filename=filename,
                        reason="dryad_table_file_missing_download_url",
                        retrieved_at=retrieved,
                    )
                )
                gaps.append(
                    {
                        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                        "lane": "behavior",
                        "doi": _doi_from_identifier(dataset_payload, spec.doi),
                        "filename": filename,
                        "reason": "dryad_table_file_missing_download_url",
                        "retrieved_at": retrieved,
                    }
                )
                continue
            table_path = _table_file_path(raw_dir, _doi_from_identifier(dataset_payload, spec.doi), file_payload, filename)
            table_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                table_bytes = client.download_file(download_url)
                if len(table_bytes) > max_table_bytes:
                    raise ValueError(f"Dryad table download exceeded max_table_bytes={max_table_bytes}: {len(table_bytes)}")
                table_path.write_bytes(table_bytes)
                raw_artifacts.append(table_path.as_posix())
                table_records, sheet_count, row_count = _table_records(
                    spec=spec,
                    dataset_payload=dataset_payload,
                    file_payload=file_payload,
                    table_path=table_path,
                    filename=filename,
                    retrieved_at=retrieved,
                    max_table_rows_per_file=max_table_rows_per_file,
                )
            except Exception as exc:
                skipped_table_file_count += 1
                records.append(
                    _table_gap_record(
                        spec=spec,
                        dataset_payload=dataset_payload,
                        file_payload=file_payload,
                        files_raw_path=files_raw_path,
                        file_index=index,
                        filename=filename,
                        reason="dryad_table_file_download_or_parse_failed",
                        retrieved_at=retrieved,
                        error=str(exc),
                    )
                )
                gaps.append(
                    {
                        "source": DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
                        "lane": "behavior",
                        "doi": _doi_from_identifier(dataset_payload, spec.doi),
                        "filename": filename,
                        "reason": "dryad_table_file_download_or_parse_failed",
                        "error": str(exc),
                        "retrieved_at": retrieved,
                    }
                )
                continue
            records.extend(table_records)
            parsed_table_file_count += 1
            table_sheet_count += sheet_count
            table_row_count += row_count

    return DryadBehaviorVideoResult(
        source_id=DRYAD_BEHAVIOR_VIDEO_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_dois=[spec.doi for spec in dataset_specs],
        dataset_count=len([record for record in records if record.record_id.startswith("dryad:dataset:")]),
        file_count=file_count,
        media_file_count=media_file_count,
        table_file_count=table_file_count,
        parsed_table_file_count=parsed_table_file_count,
        skipped_table_file_count=skipped_table_file_count,
        table_sheet_count=table_sheet_count,
        table_row_count=table_row_count,
        landing_page_count=landing_page_count,
        assay_method_count=assay_method_count,
    )
