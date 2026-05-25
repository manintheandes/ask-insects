from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import hashlib
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


WHO_DENGUE_SURVEILLANCE_SOURCE_ID = "aedes_who_dengue_surveillance"
USER_AGENT = "AskInsects/0.1 source-plane"

DEFAULT_WHO_DENGUE_SURVEILLANCE_PAGES: tuple[dict[str, str], ...] = (
    {
        "organization": "WHO Western Pacific",
        "url": "https://www.who.int/westernpacific/wpro-emergencies/surveillance/dengue",
        "page_kind": "wpro_situation_updates",
        "topic": "Western Pacific dengue situation updates",
    },
    {
        "organization": "WHO",
        "url": "https://www.who.int/publications/i/item/who-wer10052-665-678",
        "page_kind": "wer_global_update",
        "topic": "global dengue situation surveillance progress 2024 update",
    },
    {
        "organization": "WHO Western Pacific Health Data Platform",
        "url": "https://data.wpro.who.int/topic/dengue",
        "page_kind": "wpro_health_data_topic",
        "topic": "Western Pacific dengue health data platform topic",
    },
    {
        "organization": "WHO Western Pacific Health Data Platform",
        "url": "https://data.wpro.who.int/dengue-surveillance-2021",
        "page_kind": "wpro_dashboard_locator",
        "topic": "Western Pacific dengue surveillance dashboard locator",
    },
)


def who_dengue_source_spec(url: str, *, index: int = 1) -> dict[str, str]:
    lower = url.lower()
    if "who-wer" in lower or "/wer" in lower:
        return {
            "organization": "WHO",
            "url": url,
            "page_kind": "wer_global_update",
            "topic": "global dengue situation surveillance progress update",
        }
    if "data.wpro.who.int" in lower and "topic/dengue" in lower:
        return {
            "organization": "WHO Western Pacific Health Data Platform",
            "url": url,
            "page_kind": "wpro_health_data_topic",
            "topic": "Western Pacific dengue health data platform topic",
        }
    if "data.wpro.who.int" in lower or "dashboard" in lower:
        return {
            "organization": "WHO Western Pacific Health Data Platform",
            "url": url,
            "page_kind": "wpro_dashboard_locator",
            "topic": "Western Pacific dengue surveillance dashboard locator",
        }
    if "westernpacific" in lower and "surveillance/dengue" in lower:
        return {
            "organization": "WHO Western Pacific",
            "url": url,
            "page_kind": "wpro_situation_updates",
            "topic": "Western Pacific dengue situation updates",
        }
    return {
        "organization": "WHO",
        "url": url,
        "page_kind": f"custom_{index}",
        "topic": "custom WHO dengue surveillance page",
    }


@dataclass(frozen=True)
class WhoDengueSurveillanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    page_count: int
    situation_report_count: int
    archive_count: int
    publication_count: int
    dashboard_locator_count: int
    export_locator_count: int


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _clean_text(value: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|li|h\d|div|section)>", ". ", text, flags=re.IGNORECASE)
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
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "who_dengue"


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


def _record_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"public_health:surveillance:who_dengue:{prefix}:{digest}"


def _links(html: str, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    pattern = re.compile(
        r"<a\b[^>]*href=(?:[\"']([^\"']+)[\"']|([^\s>]+))[^>]*>(.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        href = (match.group(1) or match.group(2) or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        links.append({"url": urljoin(base_url, href), "label": _clean_text(match.group(3)) or href})
    return links


def _first(pattern: str, text: str, flags: int = re.IGNORECASE | re.DOTALL) -> str | None:
    match = re.search(pattern, text, flags=flags)
    return match.group(1).strip() if match else None


def _number(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace(",", "").replace(" ", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _global_metrics(text: str) -> dict[str, float | None]:
    return {
        "reported_cases": _number(_first(r"reports? of\s+([\d,\s]+)\s+cases", text)),
        "laboratory_confirmed_cases": _number(_first(r"including\s+([\d,\s]+)\s+laboratory-confirmed", text)),
        "severe_cases": _number(_first(r"laboratory-confirmed,\s+([\d,\s]+)\s+severe", text)),
        "deaths": _number(_first(r"severe and\s+([\d,\s]+)\s+deaths", text)),
        "brazil_cases": _number(_first(r"Brazil alone reported over\s+([\d,\s]+)\s+cases", text)),
        "brazil_deaths": _number(_first(r"Brazil alone reported over\s+[\d,\s]+ cases and\s+([\d,\s]+)\s+deaths", text)),
    }


def _page_record(
    *,
    source: dict[str, str],
    raw_path: Path,
    html: str,
    retrieved_at: str,
) -> EvidenceRecord:
    url = source["url"]
    text = _clean_text(html)
    title = _meta(html, "citation_title") or _meta(html, "og:title") or _tag_text(html, "h1") or _tag_text(html, "title") or url
    description = _meta(html, "description") or _meta(html, "og:description")
    page_kind = source.get("page_kind", "page")
    metrics = _global_metrics(text) if page_kind == "wer_global_update" else {}
    metric_text = ", ".join(f"{key}={value:g}" for key, value in metrics.items() if value is not None)
    record_text = " ".join(
        part
        for part in (
            f"Official WHO dengue surveillance page for Aedes aegypti public-health intelligence.",
            f"Organization: {source.get('organization', 'WHO')}.",
            f"Topic: {source.get('topic', 'dengue surveillance')}.",
            f"Summary: {description}." if description else "",
            f"Parsed metrics: {metric_text}." if metric_text else "",
            f"Page excerpt: {text[:800]}." if text else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=_record_id(page_kind, url),
        lane="public_health",
        source=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"WHO dengue surveillance: {title}",
        text=record_text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="WHO public web page; source page terms apply",
            source_url=url,
        ),
        payload={
            "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
            "organization": source.get("organization", "WHO"),
            "page_kind": page_kind,
            "topic": source.get("topic", "dengue surveillance"),
            "title": title,
            "description": description,
            "metrics": metrics,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _linked_record(
    *,
    link: dict[str, str],
    raw_path: Path,
    source_url: str,
    retrieved_at: str,
    aggregation_type: str,
    prefix: str,
    title_prefix: str,
) -> EvidenceRecord:
    url = link["url"]
    label = link["label"] or url
    return EvidenceRecord(
        record_id=_record_id(prefix, f"{source_url}:{url}:{label}"),
        lane="public_health",
        source=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"{title_prefix}: {label}",
        text=(
            f"Official WHO dengue surveillance linked artifact: {label}. "
            "This is indexed as Aedes aegypti-relevant dengue public-health surveillance evidence. "
            f"Source page: {source_url}."
        ),
        species="Aedes aegypti",
        url=source_url,
        media_url=url,
        provenance=Provenance(
            source_id=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#link-{_normalize_id(label)}",
            retrieved_at=retrieved_at,
            license="WHO linked public surveillance artifact; source page terms apply",
            source_url=source_url,
        ),
        payload={
            "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": aggregation_type,
            "label": label,
            "linked_url": url,
            "source_page_url": source_url,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _records_from_links(
    *,
    links: list[dict[str, str]],
    raw_path: Path,
    source_url: str,
    page_kind: str,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        label = link["label"]
        url = link["url"]
        lower = f"{label} {url}".lower()
        if (label, url) in seen:
            continue
        seen.add((label, url))
        if "dengue situation updates 20" in lower:
            records.append(
                _linked_record(
                    link=link,
                    raw_path=raw_path,
                    source_url=source_url,
                    retrieved_at=retrieved_at,
                    aggregation_type="who_dengue_archive_locator",
                    prefix="archive",
                    title_prefix="WHO dengue situation update archive",
                )
            )
        elif "dengue situation update" in lower or re.search(r"dengue[_-].*\.pdf", lower):
            records.append(
                _linked_record(
                    link=link,
                    raw_path=raw_path,
                    source_url=source_url,
                    retrieved_at=retrieved_at,
                    aggregation_type="who_dengue_situation_report_locator",
                    prefix="situation_report",
                    title_prefix="WHO dengue situation report",
                )
            )
        elif "download" in lower and any(ext in lower for ext in (".pdf", "iris.who.int", "apps.who.int")) and page_kind == "wer_global_update":
            records.append(
                _linked_record(
                    link=link,
                    raw_path=raw_path,
                    source_url=source_url,
                    retrieved_at=retrieved_at,
                    aggregation_type="who_dengue_publication_download_locator",
                    prefix="publication_download",
                    title_prefix="WHO WER dengue publication download",
                )
            )
        elif any(ext in lower for ext in (".csv", ".zip", ".xlsx", ".json")):
            records.append(
                _linked_record(
                    link=link,
                    raw_path=raw_path,
                    source_url=source_url,
                    retrieved_at=retrieved_at,
                    aggregation_type="who_dengue_export_locator",
                    prefix="export",
                    title_prefix="WHO dengue dashboard export locator",
                )
            )
    return records


def _dashboard_record(
    *,
    source: dict[str, str],
    raw_path: Path,
    html: str,
    retrieved_at: str,
) -> EvidenceRecord:
    url = source["url"]
    title = _meta(html, "og:title") or _tag_text(html, "h1") or source.get("topic", "WHO dengue dashboard")
    return EvidenceRecord(
        record_id=_record_id("dashboard_locator", url),
        lane="public_health",
        source=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"WHO dengue dashboard locator: {title}",
        text=(
            "Official WHO Western Pacific dengue dashboard or health data platform locator. "
            "Ask Insects stores this page and any direct export links it exposes. "
            "Country/time dashboard cells are not claimed until a stable machine-readable export or API is proven."
        ),
        species="Aedes aegypti",
        url=url,
        media_url=url,
        provenance=Provenance(
            source_id=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#dashboard-locator",
            retrieved_at=retrieved_at,
            license="WHO Western Pacific Health Data Platform public page; source page terms apply",
            source_url=url,
        ),
        payload={
            "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": "who_dengue_dashboard_locator",
            "organization": source.get("organization", "WHO Western Pacific Health Data Platform"),
            "page_kind": source.get("page_kind", "dashboard_locator"),
            "dashboard_url": url,
            "machine_readable_cell_status": "not_proven",
            "raw_html_path": raw_path.as_posix(),
        },
    )


def fetch_who_dengue_surveillance_records(
    sources: list[dict[str, str]] | tuple[dict[str, str], ...] = DEFAULT_WHO_DENGUE_SURVEILLANCE_PAGES,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> WhoDengueSurveillanceResult:
    fetch = fetch_text or _default_fetch_text
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    for source in sources:
        url = str(source.get("url") or "")
        if not url:
            gaps.append(
                {
                    "source": WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "who_dengue_source_url_missing",
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        requested_urls.append(url)
        page_kind = source.get("page_kind", "page")
        raw_path = raw_dir / f"{_safe_filename(page_kind)}_{_safe_filename(url)}.html"
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001 - source gaps should preserve fetch failures
            gaps.append(
                {
                    "source": WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "who_dengue_page_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        records.append(_page_record(source=source, raw_path=raw_path, html=html, retrieved_at=retrieved_at))
        if "dashboard" in page_kind or "data" in page_kind:
            records.append(_dashboard_record(source=source, raw_path=raw_path, html=html, retrieved_at=retrieved_at))
        linked_records = _records_from_links(
            links=_links(html, url),
            raw_path=raw_path,
            source_url=url,
            page_kind=page_kind,
            retrieved_at=retrieved_at,
        )
        records.extend(linked_records)
        if ("dashboard" in page_kind or "data" in page_kind) and not any(
            record.payload and record.payload.get("aggregation_type") == "who_dengue_export_locator"
            for record in linked_records
        ):
            gaps.append(
                {
                    "source": WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "who_dengue_dashboard_export_not_machine_readable",
                    "url": url,
                    "retrieved_at": retrieved_at,
                    "note": "Dashboard or data-platform page fetched, but no stable direct CSV, ZIP, XLSX, or JSON export link was exposed in saved HTML.",
                }
            )

    page_count = sum(1 for record in records if record.payload and "aggregation_type" not in record.payload)
    situation_report_count = sum(
        1 for record in records if record.payload and record.payload.get("aggregation_type") == "who_dengue_situation_report_locator"
    )
    archive_count = sum(1 for record in records if record.payload and record.payload.get("aggregation_type") == "who_dengue_archive_locator")
    publication_count = sum(
        1 for record in records if record.payload and record.payload.get("aggregation_type") == "who_dengue_publication_download_locator"
    )
    dashboard_locator_count = sum(
        1 for record in records if record.payload and record.payload.get("aggregation_type") == "who_dengue_dashboard_locator"
    )
    export_locator_count = sum(1 for record in records if record.payload and record.payload.get("aggregation_type") == "who_dengue_export_locator")
    return WhoDengueSurveillanceResult(
        source_id=WHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        page_count=page_count,
        situation_report_count=situation_report_count,
        archive_count=archive_count,
        publication_count=publication_count,
        dashboard_locator_count=dashboard_locator_count,
        export_locator_count=export_locator_count,
    )
