from __future__ import annotations

import csv
from dataclasses import dataclass
from html import unescape
from io import StringIO
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


CDC_DENGUE_SURVEILLANCE_SOURCE_ID = "aedes_cdc_dengue_surveillance"
USER_AGENT = "AskInsects/0.1 source-plane"
CDC_BASE_URL = "https://www.cdc.gov"

DEFAULT_CDC_DENGUE_PAGES: tuple[dict[str, str], ...] = (
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html",
        "page_kind": "current_year",
        "topic": "current year U.S. dengue ArboNET surveillance",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/dengue/data-research/facts-stats/historic-data.html",
        "page_kind": "historic",
        "topic": "historic U.S. dengue ArboNET surveillance",
    },
)


@dataclass(frozen=True)
class CdcDengueSurveillanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    page_count: int
    config_count: int
    dataset_count: int
    dataset_row_count: int
    limitation_count: int


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8-sig", "replace")


def _clean_text(value: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|li|h\d|div)>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _tag_text(html: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, flags=re.IGNORECASE | re.DOTALL)
    return _clean_text(match.group(1)) if match else ""


def _meta(html: str, name: str) -> str:
    patterns = (
        rf"<meta\s+[^>]*(?:name|property)=[\"']{re.escape(name)}[\"'][^>]*content=[\"']([^\"']+)[\"'][^>]*>",
        rf"<meta\s+[^>]*content=[\"']([^\"']+)[\"'][^>]*(?:name|property)=[\"']{re.escape(name)}[\"'][^>]*>",
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1))
    return ""


def _safe_filename(value: str) -> str:
    parsed = urlparse(value)
    name = Path(parsed.path).name or value
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return safe[:140] or "cdc_dengue"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


def _sha(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _int_value(value: object) -> int | None:
    text = str(value or "").strip().replace(",", "")
    if not re.fullmatch(r"-?\d+", text):
        return None
    return int(text)


def _numeric_value(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if not text or not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    return float(text)


def _write_raw_text(raw_dir: Path, name: str, text: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def _write_raw_json(raw_dir: Path, name: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _config_urls(html: str, page_url: str) -> list[str]:
    urls = []
    for match in re.finditer(r"data-config-url=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE):
        url = urljoin(page_url, unescape(match.group(1)))
        if url not in urls:
            urls.append(url)
    return urls


def _limitation_texts(html: str) -> list[str]:
    anchor = re.search(r"<h2[^>]*>\s*Limitations of ArboNET(?: data)?\s*</h2>(.*?)(?:<h2\b|</main>|<aside\b|$)", html, flags=re.IGNORECASE | re.DOTALL)
    if not anchor:
        return []
    section = anchor.group(1)
    paragraphs = []
    for match in re.finditer(r"<p[^>]*>(.*?)</p>", section, flags=re.IGNORECASE | re.DOTALL):
        text = _clean_text(match.group(1))
        if text:
            paragraphs.append(text)
    return paragraphs


def _page_record(
    *,
    source: dict[str, str],
    raw_path: Path,
    html: str,
    config_urls: list[str],
    retrieved_at: str,
) -> EvidenceRecord:
    url = source["url"]
    title = _meta(html, "citation_title") or _meta(html, "og:title") or _tag_text(html, "h1") or _tag_text(html, "title") or url
    description = _meta(html, "description") or _meta(html, "og:description")
    summary = ""
    match = re.search(r"<span\s+class=[\"']dfe-field[\"'][^>]*>(.*?)</span>", html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        summary = _clean_text(match.group(1))
    text = " ".join(
        part
        for part in (
            "CDC dengue ArboNET surveillance page relevant to Aedes aegypti public-health intelligence.",
            f"Topic: {source.get('topic', '')}.",
            f"Title: {title}.",
            f"Summary: {summary or description}." if summary or description else "",
            f"Visualization config URLs discovered: {len(config_urls)}.",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"public_health:surveillance:cdc_dengue:page:{source.get('page_kind', _sha(url))}",
        lane="public_health",
        source=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"CDC dengue surveillance page: {title}",
        text=text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="CDC public web data; source page terms apply",
            source_url=url,
        ),
        payload={
            "organization": "CDC",
            "disease": "dengue",
            "aedes_relevance": "Dengue surveillance is indexed as Aedes aegypti-relevant public-health intelligence",
            "aggregation_type": "cdc_surveillance_page",
            "page_kind": source.get("page_kind"),
            "topic": source.get("topic"),
            "title": title,
            "description": description,
            "summary": summary,
            "config_urls": config_urls,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _limitation_record(
    *,
    source: dict[str, str],
    raw_path: Path,
    text: str,
    index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    page_kind = source.get("page_kind", "unknown")
    url = source["url"]
    record_text = (
        "CDC ArboNET dengue surveillance limitation for Aedes aegypti-relevant public-health intelligence. "
        f"Limitation: {text}"
    )
    return EvidenceRecord(
        record_id=f"public_health:surveillance:cdc_dengue:limitation:{page_kind}:{index:02d}",
        lane="public_health",
        source=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"CDC ArboNET dengue surveillance limitation {index}: {page_kind}",
        text=record_text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#limitations/{index}",
            retrieved_at=retrieved_at,
            license="CDC public web data; source page terms apply",
            source_url=url,
        ),
        payload={
            "organization": "CDC",
            "disease": "dengue",
            "aggregation_type": "arbonet_limitation",
            "page_kind": page_kind,
            "limitation_index": index,
            "limitation_text": text,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _walk_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            strings.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_walk_strings(item))
    elif isinstance(value, str):
        strings.append(value)
    return strings


def _dataset_records_from_config(config: object, config_url: str) -> list[dict[str, object]]:
    datasets: dict[str, dict[str, object]] = {}
    dataset_map = config.get("datasets") if isinstance(config, dict) else None
    if not isinstance(dataset_map, dict):
        dataset_map = {}

    def resolved_dataset_url(candidate: str) -> str:
        mapped = dataset_map.get(candidate)
        if isinstance(mapped, dict):
            mapped_url = str(mapped.get("dataUrl") or mapped.get("dataFileName") or "")
            if mapped_url:
                return mapped_url
        return candidate

    def add(url: str, *, label: str = "", visualization_type: str = "", widget_id: str = "") -> None:
        url = resolved_dataset_url(url)
        if not url.lower().endswith(".csv"):
            return
        full_url = urljoin(config_url, url)
        entry = datasets.setdefault(
            full_url,
            {
                "url": full_url,
                "labels": [],
                "visualization_types": [],
                "widget_ids": [],
            },
        )
        if label and label not in entry["labels"]:
            entry["labels"].append(label)
        if visualization_type and visualization_type not in entry["visualization_types"]:
            entry["visualization_types"].append(visualization_type)
        if widget_id and widget_id not in entry["widget_ids"]:
            entry["widget_ids"].append(widget_id)

    if isinstance(config, dict):
        top_url = str(config.get("dataUrl") or config.get("dataFileName") or "")
        top_label = ""
        if isinstance(config.get("table"), dict):
            top_label = str(config["table"].get("label") or config["table"].get("table-label") or "")
        add(top_url, label=top_label, visualization_type=str(config.get("type") or ""), widget_id=str(config.get("uid") or ""))

        visualizations: list[tuple[str, dict[str, object]]] = []
        for dashboard in config.get("multiDashboards", []) if isinstance(config.get("multiDashboards"), list) else []:
            if isinstance(dashboard, dict) and isinstance(dashboard.get("visualizations"), dict):
                visualizations.extend((str(key), value) for key, value in dashboard["visualizations"].items() if isinstance(value, dict))
        if isinstance(config.get("visualizations"), dict):
            visualizations.extend((str(key), value) for key, value in config["visualizations"].items() if isinstance(value, dict))
        for widget_id, visualization in visualizations:
            label = ""
            if isinstance(visualization.get("table"), dict):
                label = str(visualization["table"].get("label") or visualization["table"].get("table-label") or "")
            add(
                str(visualization.get("dataUrl") or visualization.get("dataKey") or visualization.get("dataFileName") or ""),
                label=label,
                visualization_type=str(visualization.get("visualizationType") or visualization.get("type") or ""),
                widget_id=widget_id,
            )

        for key, value in dataset_map.items():
            if isinstance(value, dict):
                add(str(value.get("dataUrl") or value.get("dataFileName") or key), label=str(value.get("label") or key))

    for candidate in _walk_strings(config):
        add(candidate)
    return list(datasets.values())


def _csv_rows(text: str) -> list[dict[str, str]]:
    return [dict(row) for row in csv.DictReader(StringIO(text)) if any(str(value or "").strip() for value in row.values())]


def _measure_fields(row: dict[str, str]) -> dict[str, object]:
    measures: dict[str, object] = {}
    for key, value in row.items():
        if key in {"Year", "Travel status", "Jurisdiction", "County", "Week", "Age group", "Case status", "Clinical Syndrome", "Serotype", "Hospitalization", "Legend", "Notes"}:
            continue
        if value is None or str(value).strip() == "":
            continue
        number = _numeric_value(value)
        measures[key] = number if number is not None else str(value).strip()
    return measures


def _row_title(dataset_name: str, row: dict[str, str]) -> str:
    dimensions = []
    for key in ("Year", "Travel status", "Jurisdiction", "County", "Week", "Age group", "Case status", "Clinical Syndrome", "Serotype", "Hospitalization"):
        value = str(row.get(key) or "").strip()
        if value:
            dimensions.append(f"{key}: {value}")
    suffix = "; ".join(dimensions[:4])
    return f"CDC dengue surveillance CSV row: {dataset_name}" + (f" ({suffix})" if suffix else "")


def _csv_record(
    *,
    row: dict[str, str],
    row_index: int,
    dataset: dict[str, object],
    csv_path: Path,
    dataset_url: str,
    page_kind: str,
    config_url: str,
    retrieved_at: str,
) -> EvidenceRecord:
    dataset_name = Path(urlparse(dataset_url).path).name or "cdc_dengue_dataset.csv"
    labels = [str(label) for label in dataset.get("labels", []) if str(label)]
    measures = _measure_fields(row)
    dimensions = {
        key: value
        for key, value in row.items()
        if key in {"Year", "Travel status", "Jurisdiction", "County", "Week", "Age group", "Case status", "Clinical Syndrome", "Serotype", "Hospitalization", "Legend", "Notes"}
        and str(value or "").strip()
    }
    pieces = [
        f"CDC ArboNET dengue surveillance CSV row from {dataset_name}.",
        f"Dataset label: {labels[0]}." if labels else "",
        f"Page kind: {page_kind}.",
        "Dimensions: " + "; ".join(f"{key}: {value}" for key, value in dimensions.items()) + "." if dimensions else "",
        "Measures: " + "; ".join(f"{key}: {value}" for key, value in measures.items()) + "." if measures else "",
        "Aedes aegypti relevance: dengue surveillance is indexed as public-health intelligence for the primary dengue vector.",
    ]
    row_identity = json.dumps(row, sort_keys=True)
    return EvidenceRecord(
        record_id=f"public_health:surveillance:cdc_dengue:csv:{_safe_id(dataset_name)}:row:{row_index:06d}:{_sha(row_identity)}",
        lane="public_health",
        source=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=_row_title(dataset_name, row),
        text=" ".join(part for part in pieces if part),
        species="Aedes aegypti",
        url=dataset_url,
        media_url=None,
        provenance=Provenance(
            source_id=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{csv_path.as_posix()}#row/{row_index}",
            retrieved_at=retrieved_at,
            license="CDC public CSV data; source page terms apply",
            source_url=dataset_url,
        ),
        payload={
            "organization": "CDC",
            "disease": "dengue",
            "aggregation_type": "cdc_dengue_csv_row",
            "dataset_name": dataset_name,
            "dataset_labels": labels,
            "dataset_url": dataset_url,
            "config_url": config_url,
            "page_kind": page_kind,
            "row_number": row_index,
            "dimensions": dimensions,
            "measures": measures,
            "row": row,
            "raw_csv_path": csv_path.as_posix(),
        },
    )


def _config_record(
    *,
    config: object,
    config_path: Path,
    config_url: str,
    page_kind: str,
    datasets: list[dict[str, object]],
    retrieved_at: str,
) -> EvidenceRecord:
    title = "CDC dengue visualization config"
    if isinstance(config, dict) and config.get("title"):
        title = str(config["title"])
    labels = []
    for dataset in datasets:
        labels.extend(str(label) for label in dataset.get("labels", []) if str(label))
    text = (
        f"CDC dengue surveillance visualization config for {page_kind}. "
        f"Discovered {len(datasets)} CSV dataset locator(s). "
        f"Dataset labels: {'; '.join(labels[:8])}."
    )
    return EvidenceRecord(
        record_id=f"public_health:surveillance:cdc_dengue:config:{page_kind}:{_sha(config_url)}",
        lane="public_health",
        source=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=config_url,
        media_url=None,
        provenance=Provenance(
            source_id=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{config_path.as_posix()}#config",
            retrieved_at=retrieved_at,
            license="CDC public visualization config; source page terms apply",
            source_url=config_url,
        ),
        payload={
            "organization": "CDC",
            "disease": "dengue",
            "aggregation_type": "cdc_visualization_config",
            "page_kind": page_kind,
            "config_url": config_url,
            "dataset_urls": [str(dataset["url"]) for dataset in datasets],
            "dataset_labels": labels,
            "raw_config_path": config_path.as_posix(),
        },
    )


def fetch_cdc_dengue_surveillance_records(
    sources: list[dict[str, str]] | tuple[dict[str, str], ...] = DEFAULT_CDC_DENGUE_PAGES,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> CdcDengueSurveillanceResult:
    fetch = fetch_text or _default_fetch_text
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    seen_dataset_urls: set[str] = set()
    page_count = 0
    config_count = 0
    dataset_count = 0
    dataset_row_count = 0
    limitation_count = 0

    for source in sources:
        url = str(source.get("url") or "")
        page_kind = str(source.get("page_kind") or _sha(url))
        if not url:
            gaps.append(
                {
                    "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "cdc_dengue_page_url_missing",
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        requested_urls.append(url)
        try:
            html = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "cdc_dengue_page_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        page_path = _write_raw_text(raw_dir, f"{page_kind}_{_safe_filename(url)}", html)
        raw_artifacts.append(page_path.as_posix())
        config_urls = _config_urls(html, url)
        page_count += 1
        records.append(_page_record(source=source, raw_path=page_path, html=html, config_urls=config_urls, retrieved_at=retrieved_at))
        limitations = _limitation_texts(html)
        for limitation_index, limitation_text in enumerate(limitations, start=1):
            records.append(
                _limitation_record(
                    source=source,
                    raw_path=page_path,
                    text=limitation_text,
                    index=limitation_index,
                    retrieved_at=retrieved_at,
                )
            )
            limitation_count += 1
        if not config_urls:
            gaps.append(
                {
                    "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "cdc_dengue_visualization_config_not_discovered",
                    "url": url,
                    "raw_html_path": page_path.as_posix(),
                    "retrieved_at": retrieved_at,
                }
            )

        for config_url in config_urls:
            if config_url not in requested_urls:
                requested_urls.append(config_url)
            try:
                config_text = fetch(config_url)
                config = json.loads(config_text)
            except Exception as exc:
                gaps.append(
                    {
                        "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                        "lane": "public_health",
                        "reason": "cdc_dengue_visualization_config_fetch_failed",
                        "url": config_url,
                        "page_url": url,
                        "error": str(exc),
                        "retrieved_at": retrieved_at,
                    }
                )
                continue
            config_path = _write_raw_json(raw_dir, f"{page_kind}_{_safe_filename(config_url)}", config)
            raw_artifacts.append(config_path.as_posix())
            config_count += 1
            datasets = _dataset_records_from_config(config, config_url)
            records.append(
                _config_record(
                    config=config,
                    config_path=config_path,
                    config_url=config_url,
                    page_kind=page_kind,
                    datasets=datasets,
                    retrieved_at=retrieved_at,
                )
            )
            if not datasets:
                gaps.append(
                    {
                        "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                        "lane": "public_health",
                        "reason": "cdc_dengue_config_csv_dataset_not_discovered",
                        "url": config_url,
                        "raw_config_path": config_path.as_posix(),
                        "retrieved_at": retrieved_at,
                    }
                )
                continue
            for dataset in datasets:
                dataset_url = str(dataset["url"])
                if dataset_url in seen_dataset_urls:
                    continue
                seen_dataset_urls.add(dataset_url)
                if dataset_url not in requested_urls:
                    requested_urls.append(dataset_url)
                try:
                    csv_text = fetch(dataset_url)
                except Exception as exc:
                    gaps.append(
                        {
                            "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                            "lane": "public_health",
                            "reason": "cdc_dengue_csv_fetch_failed",
                            "url": dataset_url,
                            "config_url": config_url,
                            "error": str(exc),
                            "retrieved_at": retrieved_at,
                        }
                    )
                    continue
                csv_path = _write_raw_text(raw_dir, f"{_safe_filename(dataset_url)}", csv_text)
                raw_artifacts.append(csv_path.as_posix())
                rows = _csv_rows(csv_text)
                if not rows:
                    gaps.append(
                        {
                            "source": CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                            "lane": "public_health",
                            "reason": "cdc_dengue_csv_no_rows",
                            "url": dataset_url,
                            "raw_csv_path": csv_path.as_posix(),
                            "retrieved_at": retrieved_at,
                        }
                    )
                    continue
                dataset_count += 1
                for row_index, row in enumerate(rows, start=1):
                    records.append(
                        _csv_record(
                            row=row,
                            row_index=row_index,
                            dataset=dataset,
                            csv_path=csv_path,
                            dataset_url=dataset_url,
                            page_kind=page_kind,
                            config_url=config_url,
                            retrieved_at=retrieved_at,
                        )
                    )
                    dataset_row_count += 1

    return CdcDengueSurveillanceResult(
        source_id=CDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        page_count=page_count,
        config_count=config_count,
        dataset_count=dataset_count,
        dataset_row_count=dataset_row_count,
        limitation_count=limitation_count,
    )
