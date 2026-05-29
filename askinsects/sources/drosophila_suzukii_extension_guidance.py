from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import hashlib
import re
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID = "drosophila_suzukii_extension_guidance"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
USER_AGENT = "AskInsects/0.1 source-plane"


DEFAULT_EXTENSION_GUIDANCE_SOURCES: tuple[dict[str, object], ...] = (
    {
        "organization": "UC IPM",
        "url": "https://ipm.ucanr.edu/PMG/PESTNOTES/pn74158.html",
        "topic": "spotted wing drosophila pest note, monitoring, sanitation, exclusion, and chemical control",
        "region": "California",
    },
    {
        "organization": "UC IPM",
        "url": "https://ipm.ucanr.edu/agriculture/cherry/spotted-wing-drosophila/",
        "topic": "spotted wing drosophila in cherry, monitoring and management",
        "region": "California",
    },
    {
        "organization": "Cornell Fruit Resources",
        "url": "https://fruit.cornell.edu/spottedwing/",
        "topic": "spotted wing drosophila regional management resources",
        "region": "Northeastern United States",
    },
    {
        "organization": "Michigan State University Extension",
        "url": "https://www.canr.msu.edu/ipm/Invasive_species/spotted_wing_drosophila/",
        "topic": "spotted wing drosophila integrated pest management",
        "region": "Michigan",
    },
    {
        "organization": "Penn State Extension",
        "url": "https://extension.psu.edu/spotted-wing-drosophila-part-1-overview-and-identification",
        "topic": "spotted wing drosophila overview, identification, and management context",
        "region": "Pennsylvania",
    },
    {
        "organization": "University of Minnesota Extension",
        "url": "https://extension.umn.edu/yard-and-garden-insects/spotted-wing-drosophila",
        "topic": "spotted wing drosophila garden and small fruit management",
        "region": "Minnesota",
    },
    {
        "organization": "Washington State University Tree Fruit",
        "url": "https://treefruit.wsu.edu/crop-protection/opm/spotted-wing-drosophila/",
        "topic": "spotted wing drosophila tree fruit pest management",
        "region": "Washington",
    },
    {
        "organization": "SWD Management",
        "url": "https://swdmanagement.org/",
        "topic": "multi-institution spotted wing drosophila management clearinghouse",
        "region": "United States",
    },
)


@dataclass(frozen=True)
class DrosophilaSuzukiiExtensionGuidanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
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


def _safe_filename(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_")[:120] or "swd_extension"


def _safe_id(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_") or "unknown"


def _record_id(url: str) -> str:
    return f"swd_extension_guidance:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def _topic_terms(text: str, declared_topic: str) -> list[str]:
    terms = [declared_topic] if declared_topic else []
    lower = text.lower()
    for term in (
        "Drosophila suzukii",
        "spotted wing drosophila",
        "SWD",
        "integrated pest management",
        "monitoring",
        "trapping",
        "sanitation",
        "harvest",
        "exclusion",
        "netting",
        "insecticide",
        "chemical control",
        "biological control",
        "parasitoid",
        "resistance",
        "fruit damage",
        "berries",
        "cherry",
        "grape",
    ):
        if term.lower() in lower and term not in terms:
            terms.append(term)
    return terms


def _guidance_type(topics: list[str]) -> str:
    lower = " ".join(topics).lower()
    if any(term in lower for term in ("insecticide", "chemical control", "resistance")):
        return "chemical_management"
    if any(term in lower for term in ("biological control", "parasitoid")):
        return "biocontrol_context"
    if any(term in lower for term in ("monitoring", "trapping")):
        return "monitoring_and_detection"
    return "integrated_pest_management"


def _excerpt(text: str) -> str:
    lower = text.lower()
    anchors = [
        lower.find(term)
        for term in (
            "spotted wing drosophila",
            "drosophila suzukii",
            "monitor",
            "management",
            "insecticide",
            "sanitation",
            "exclusion",
        )
        if lower.find(term) >= 0
    ]
    start = max(0, min(anchors) - 180) if anchors else 0
    excerpt = text[start : start + 800].strip()
    if start > 0:
        excerpt = f"... {excerpt}"
    if start + 800 < len(text):
        excerpt = f"{excerpt} ..."
    return excerpt


def _guidance_record(
    *,
    source: dict[str, object],
    raw_path: Path,
    html: str,
    retrieved_at: str,
) -> EvidenceRecord:
    url = str(source["url"])
    organization = str(source.get("organization") or "extension source")
    declared_topic = str(source.get("topic") or "")
    region = str(source.get("region") or "")
    text = _clean_text(html)
    title = _meta(html, "citation_title") or _meta(html, "og:title") or _tag_text(html, "h1") or _tag_text(html, "title") or url
    description = _meta(html, "description") or _meta(html, "og:description")
    topics = _topic_terms(f"{title} {description} {text}", declared_topic)
    guidance_type = _guidance_type(topics)
    record_text = " ".join(
        part
        for part in (
            f"Extension/IPM guidance for {SPECIES} ({COMMON_NAME}) from {organization}.",
            f"Region: {region}." if region else "",
            f"Topic: {', '.join(topics)}." if topics else "",
            f"Summary: {description}." if description else "",
            f"Page excerpt: {_excerpt(text)}" if text else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=_record_id(url),
        lane="management",
        source=DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID,
        title=f"{organization} SWD guidance: {title}",
        text=record_text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="Public extension/IPM web guidance; source page terms apply",
            source_url=url,
        ),
        payload={
            "atom_type": "extension_guidance_page",
            "organization": organization,
            "url": url,
            "declared_topic": declared_topic,
            "region": region,
            "title": title,
            "description": description,
            "topics": topics,
            "guidance_type": guidance_type,
            "primary_taxon": SPECIES,
            "common_name": COMMON_NAME,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def fetch_drosophila_suzukii_extension_guidance_records(
    sources: list[dict[str, object]] | tuple[dict[str, object], ...] = DEFAULT_EXTENSION_GUIDANCE_SOURCES,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> DrosophilaSuzukiiExtensionGuidanceResult:
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
                    "source": DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID,
                    "lane": "management",
                    "species": SPECIES,
                    "reason": "swd_extension_guidance_url_missing",
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
                    "source": DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID,
                    "lane": "management",
                    "species": SPECIES,
                    "reason": "swd_extension_guidance_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path = raw_dir / f"{_safe_filename(source.get('organization', 'source'))}_{_safe_id(source.get('region', 'region'))}_{_record_id(url).rsplit(':', 1)[-1]}.html"
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        records.append(_guidance_record(source=source, raw_path=raw_path, html=html, retrieved_at=retrieved_at))

    return DrosophilaSuzukiiExtensionGuidanceResult(
        source_id=DROSOPHILA_SUZUKII_EXTENSION_GUIDANCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
    )
