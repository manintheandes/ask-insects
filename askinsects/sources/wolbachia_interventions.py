from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import hashlib
import re
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


WOLBACHIA_INTERVENTION_SOURCE_ID = "aedes_wolbachia_interventions"
USER_AGENT = "AskInsects/0.1 source-plane"

DEFAULT_WOLBACHIA_SOURCES: tuple[dict[str, object], ...] = (
    {
        "organization": "World Mosquito Program",
        "url": "https://www.worldmosquitoprogram.org/en/work/wolbachia-method",
        "topic": "World Mosquito Program Wolbachia method for Aedes aegypti",
        "intervention_type": "wMel Wolbachia replacement",
    },
    {
        "organization": "World Mosquito Program",
        "url": "https://www.worldmosquitoprogram.org/en/work/wolbachia-method/how-it-works",
        "topic": "mechanism of Wolbachia blocking arbovirus transmission",
        "intervention_type": "wMel Wolbachia replacement",
    },
    {
        "organization": "World Mosquito Program",
        "url": "https://www.worldmosquitoprogram.com/en/news-stories/media-releases/world-mosquito-programs-wolbachia-method-dramatically-reduces-dengue",
        "topic": "Yogyakarta randomized controlled trial first results",
        "intervention_type": "wMel Wolbachia replacement",
    },
    {
        "organization": "World Mosquito Program",
        "url": "https://www.worldmosquitoprogram.org/en/news-stories/media-releases/wolbachia-dramatically-reduces-dengue-cases-peer-reviewed-and",
        "topic": "Yogyakarta randomized controlled trial peer-reviewed result",
        "intervention_type": "wMel Wolbachia replacement",
    },
    {
        "organization": "World Mosquito Program",
        "url": "https://www.worldmosquitoprogram.org/en/global-progress",
        "topic": "Wolbachia program global progress and deployment footprint",
        "intervention_type": "wMel Wolbachia replacement",
    },
)


@dataclass(frozen=True)
class WolbachiaInterventionResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", "replace")


def _clean_text(value: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
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
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "wolbachia"


def _record_id(url: str) -> str:
    return f"wolbachia:intervention:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def _metrics(text: str) -> list[str]:
    values = re.findall(r"\b\d+(?:\.\d+)?\s?%", text)
    count_pattern = r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?|\b\d+(?:\.\d+)?"
    unit_pattern = r"(?:countries|people|million|billion|sites|communities)"
    values.extend(
        f"{match.group(1).replace(',', '')} {match.group(2)}"
        for match in re.finditer(rf"({count_pattern})\s+({unit_pattern})\b", text, flags=re.IGNORECASE)
    )
    return list(dict.fromkeys(value.strip() for value in values))


def _excerpt(text: str) -> str:
    lower = text.lower()
    anchors = [
        lower.find(term)
        for term in ("wolbachia", "aedes aegypti", "yogyakarta", "dengue", "reduction", "global progress")
        if lower.find(term) >= 0
    ]
    start = max(0, min(anchors) - 160) if anchors else 0
    excerpt = text[start : start + 800].strip()
    if start > 0:
        excerpt = f"... {excerpt}"
    if start + 800 < len(text):
        excerpt = f"{excerpt} ..."
    return excerpt


def _intervention_record(*, source: dict[str, object], raw_path: Path, html: str, retrieved_at: str) -> EvidenceRecord:
    url = str(source["url"])
    organization = str(source.get("organization") or "World Mosquito Program")
    topic = str(source.get("topic") or "Wolbachia intervention evidence")
    intervention_type = str(source.get("intervention_type") or "Wolbachia intervention")
    text = _clean_text(html)
    title = _meta(html, "citation_title") or _meta(html, "og:title") or _tag_text(html, "h1") or _tag_text(html, "title") or url
    description = _meta(html, "description") or _meta(html, "og:description")
    metrics = _metrics(text)
    record_text = " ".join(
        part
        for part in (
            f"{organization} Wolbachia intervention evidence for Aedes aegypti.",
            f"Topic: {topic}.",
            f"Intervention type: {intervention_type}.",
            f"Metrics mentioned: {', '.join(metrics)}." if metrics else "",
            f"Summary: {description}." if description else "",
            f"Page excerpt: {_excerpt(text)}" if text else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=_record_id(url),
        lane="public_health",
        source=WOLBACHIA_INTERVENTION_SOURCE_ID,
        title=f"Wolbachia intervention evidence: {title}",
        text=record_text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=WOLBACHIA_INTERVENTION_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="World Mosquito Program public web evidence; source page terms apply",
            source_url=url,
        ),
        payload={
            "organization": organization,
            "url": url,
            "topic": topic,
            "intervention_type": intervention_type,
            "title": title,
            "description": description,
            "metrics": metrics,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def fetch_wolbachia_intervention_records(
    sources: list[dict[str, object]] | tuple[dict[str, object], ...] = DEFAULT_WOLBACHIA_SOURCES,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> WolbachiaInterventionResult:
    fetch = fetch_text or _default_fetch_text
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    for source in sources:
        url = str(source.get("url") or "")
        if not url:
            gaps.append({"source": WOLBACHIA_INTERVENTION_SOURCE_ID, "lane": "public_health", "reason": "wolbachia_intervention_url_missing", "retrieved_at": retrieved_at})
            continue
        requested_urls.append(url)
        try:
            html = fetch(url)
        except Exception as exc:
            gaps.append({"source": WOLBACHIA_INTERVENTION_SOURCE_ID, "lane": "public_health", "reason": "wolbachia_intervention_fetch_failed", "url": url, "error": str(exc), "retrieved_at": retrieved_at})
            continue
        raw_path = raw_dir / f"{_safe_filename(source.get('organization', 'wmp'))}_{_record_id(url).rsplit(':', 1)[-1]}.html"
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        records.append(_intervention_record(source=source, raw_path=raw_path, html=html, retrieved_at=retrieved_at))

    return WolbachiaInterventionResult(
        source_id=WOLBACHIA_INTERVENTION_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
    )
