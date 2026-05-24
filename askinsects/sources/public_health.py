from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import hashlib
import re
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


PUBLIC_HEALTH_SOURCE_ID = "aedes_public_health_guidance"
USER_AGENT = "AskInsects/0.1 source-plane"

DEFAULT_PUBLIC_HEALTH_SOURCES: tuple[dict[str, object], ...] = (
    {
        "organization": "WHO",
        "url": "https://www.who.int/publications/i/item/9789240111110",
        "topic": "arboviral clinical management",
    },
    {
        "organization": "WHO",
        "url": "https://www.who.int/publications/i/item/9789241547871",
        "topic": "dengue diagnosis treatment prevention control",
    },
    {
        "organization": "WHO",
        "url": "https://www.who.int/health-topics/zika-virus-disease/how-to-prevent-mosquito-breeding",
        "topic": "mosquito breeding prevention",
    },
    {
        "organization": "PAHO",
        "url": "https://www.paho.org/en/documents/key-messages-individuals-families-and-communities-actions-prevent-and-control-aedes",
        "topic": "Aedes aegypti community prevention and control",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/zika/php/mosquito-control/index.html",
        "topic": "Zika mosquito control",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/mosquitoes/php/toolkit/integrated-mosquito-management-1.html",
        "topic": "integrated mosquito management",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/dengue/transmission/index.html",
        "topic": "dengue transmission",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/mosquitoes/mosquito-control/mosquitoes-with-wolbachia.html",
        "topic": "Wolbachia Aedes aegypti mosquito control",
    },
    {
        "organization": "WHO",
        "url": "https://www.who.int/en/news-room/fact-sheets/detail/dengue-and-severe-dengue",
        "topic": "dengue fact sheet transmission vector control",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/dengue/prevention/index.html",
        "topic": "dengue prevention mosquito bite prevention",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/mosquitoes/about/life-cycle-of-aedes-mosquitoes.html",
        "topic": "Aedes mosquito life cycle breeding sites",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/zika/php/transmission/index.html",
        "topic": "Zika transmission Aedes aegypti",
    },
    {
        "organization": "CDC",
        "url": "https://www.cdc.gov/yellow-book/hcp/travel-associated-infections-diseases/dengue.html",
        "topic": "travel-associated dengue prevention and transmission",
    },
    {
        "organization": "ECDC",
        "url": "https://www.ecdc.europa.eu/en/disease-vectors/facts/mosquito-factsheets/aedes-aegypti",
        "topic": "Aedes aegypti vector factsheet control ecology",
    },
)


@dataclass(frozen=True)
class PublicHealthGuidanceResult:
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


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "public_health"


def _record_id(url: str) -> str:
    return f"public_health:guidance:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def _topic_terms(text: str, declared_topic: str) -> list[str]:
    terms = [declared_topic]
    lower = text.lower()
    for term in (
        "Aedes aegypti",
        "dengue",
        "Zika",
        "chikungunya",
        "yellow fever",
        "vector control",
        "integrated mosquito management",
        "surveillance",
        "outbreak",
        "Wolbachia",
        "source reduction",
        "mosquito breeding",
    ):
        if term.lower() in lower and term not in terms:
            terms.append(term)
    return terms


def _excerpt(text: str) -> str:
    lower = text.lower()
    anchors = [
        lower.find(term)
        for term in (
            "aedes aegypti",
            "aedes",
            "dengue",
            "vector control",
            "mosquito control",
            "mosquito breeding",
        )
        if lower.find(term) >= 0
    ]
    start = max(0, min(anchors) - 180) if anchors else 0
    excerpt = text[start : start + 700].strip()
    if start > 0:
        excerpt = f"... {excerpt}"
    if start + 700 < len(text):
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
    organization = str(source.get("organization") or "public health source")
    declared_topic = str(source.get("topic") or "")
    text = _clean_text(html)
    title = _meta(html, "citation_title") or _meta(html, "og:title") or _tag_text(html, "h1") or _tag_text(html, "title") or url
    description = _meta(html, "description") or _meta(html, "og:description")
    topics = _topic_terms(f"{title} {description} {text}", declared_topic)
    record_text = " ".join(
        part
        for part in (
            f"Official {organization} operational public-health guidance relevant to Aedes aegypti.",
            f"Topic: {', '.join(topics)}." if topics else "",
            f"Summary: {description}." if description else "",
            f"Page excerpt: {_excerpt(text)}" if text else "",
        )
        if part
    )
    return EvidenceRecord(
        record_id=_record_id(url),
        lane="public_health",
        source=PUBLIC_HEALTH_SOURCE_ID,
        title=f"{organization} guidance: {title}",
        text=record_text,
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=PUBLIC_HEALTH_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="Public health web guidance; source page terms apply",
            source_url=url,
        ),
        payload={
            "organization": organization,
            "url": url,
            "declared_topic": declared_topic,
            "title": title,
            "description": description,
            "topics": topics,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def fetch_public_health_guidance_records(
    sources: list[dict[str, object]] | tuple[dict[str, object], ...] = DEFAULT_PUBLIC_HEALTH_SOURCES,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> PublicHealthGuidanceResult:
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
                    "source": PUBLIC_HEALTH_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "public_health_guidance_url_missing",
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
                    "source": PUBLIC_HEALTH_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "public_health_guidance_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path = raw_dir / f"{_safe_filename(source.get('organization', 'source'))}_{_record_id(url).rsplit(':', 1)[-1]}.html"
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        records.append(_guidance_record(source=source, raw_path=raw_path, html=html, retrieved_at=retrieved_at))

    return PublicHealthGuidanceResult(
        source_id=PUBLIC_HEALTH_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
    )
