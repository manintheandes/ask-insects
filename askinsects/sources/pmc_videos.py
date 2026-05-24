from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


PMC_VIDEO_SOURCE_ID = "pmc_open_access_videos"
DEFAULT_PMC_VIDEO_ARTICLES = (
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC7535929/",
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC12077400/",
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC9103082/",
)
USER_AGENT = "AskInsects/0.1 source-plane"
VIDEO_EXTENSIONS = (".mp4", ".webm", ".avi", ".mov")


@dataclass(frozen=True)
class PMCVideosResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    article_count: int
    video_count: int


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _meta(html: str, name: str) -> str:
    pattern = rf"<meta\s+[^>]*name=[\"']{re.escape(name)}[\"'][^>]*content=[\"']([^\"']+)[\"'][^>]*>"
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return _clean_text(match.group(1))
    pattern = rf"<meta\s+[^>]*content=[\"']([^\"']+)[\"'][^>]*name=[\"']{re.escape(name)}[\"'][^>]*>"
    match = re.search(pattern, html, re.IGNORECASE)
    return _clean_text(match.group(1)) if match else ""


def _license_text(html: str) -> str:
    meta_license = _meta(html, "citation_license")
    if meta_license:
        return meta_license
    for label in (
        "Creative Commons Attribution License",
        "Creative Commons Public Domain Dedication",
        "Creative Commons Attribution-NonCommercial License",
    ):
        if label.lower() in html.lower():
            return label
    match = re.search(r"creativecommons\.org/licenses/([a-z-]+)/([0-9.]+)/", html, re.IGNORECASE)
    if match:
        return f"CC {match.group(1).upper()} {match.group(2)}"
    return ""


def _pmcid(article_url: str, html: str) -> str:
    match = re.search(r"PMC(\d+)", article_url, re.IGNORECASE) or re.search(r"/articles/instance/(\d+)/", html)
    return f"PMC{match.group(1)}" if match else "PMC_UNKNOWN"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "pmc_article"


def _video_links(article_url: str, html: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"href=[\"']([^\"']+)[\"']", html, re.IGNORECASE):
        href = unescape(match.group(1))
        bare_href = href.split("?", 1)[0].lower()
        if not bare_href.endswith(VIDEO_EXTENSIONS):
            continue
        url = urljoin(article_url, href)
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
    download_links = [url for url in links if "/articles/instance/" in url and "/bin/" in url]
    if download_links:
        return download_links
    return links


def _caption_for_link(html: str, link: str) -> str:
    position = html.find(link)
    if position < 0:
        relative = link.replace("https://pmc.ncbi.nlm.nih.gov", "")
        position = html.find(relative)
    if position < 0:
        return ""
    snippet = html[position : position + 900]
    text = _clean_text(snippet)
    match = re.search(r"((?:Additional file|Video|Movie)[^.]*(?:\.|$).{0,220})", text, re.IGNORECASE)
    return match.group(1).strip() if match else text[:260]


def _video_record(
    *,
    article_url: str,
    raw_path: Path,
    pmcid: str,
    article_title: str,
    doi: str,
    license_text: str,
    video_url: str,
    index: int,
    retrieved_at: str,
) -> EvidenceRecord:
    filename = Path(video_url.split("?", 1)[0]).name
    caption = _caption_for_link(raw_path.read_text(encoding="utf-8"), video_url)
    title = f"Aedes aegypti PMC supplementary video {filename}"
    text_parts = [
        f"PMC open-access supplementary video for Aedes aegypti from {article_title or pmcid}.",
        f"Video file: {filename}.",
    ]
    if caption:
        text_parts.append(f"Caption context: {caption}")
    if doi:
        text_parts.append(f"DOI: {doi}.")
    return EvidenceRecord(
        record_id=f"pmc:video:{pmcid}:{_safe_filename(filename)}",
        lane="media",
        source=PMC_VIDEO_SOURCE_ID,
        title=title,
        text=" ".join(text_parts),
        species="Aedes aegypti",
        url=article_url,
        media_url=video_url,
        provenance=Provenance(
            source_id=PMC_VIDEO_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#video/{index}",
            retrieved_at=retrieved_at,
            license=license_text or "PMC open access article license not parsed",
            source_url=article_url,
        ),
        payload={
            "pmcid": pmcid,
            "article_title": article_title,
            "doi": doi,
            "video_url": video_url,
            "filename": filename,
            "caption": caption,
            "raw_html": raw_path.as_posix(),
            "raw_html_path": raw_path.as_posix(),
        },
    )


def fetch_pmc_video_records(
    article_urls: list[str] | tuple[str, ...] = DEFAULT_PMC_VIDEO_ARTICLES,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> PMCVideosResult:
    fetch = fetch_text or _default_fetch_text
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []

    for article_url in article_urls:
        try:
            html = fetch(article_url)
        except Exception as exc:
            gaps.append(
                {
                    "source": PMC_VIDEO_SOURCE_ID,
                    "lane": "media",
                    "reason": "pmc_video_article_fetch_failed",
                    "url": article_url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue

        pmcid = _pmcid(article_url, html)
        raw_path = raw_dir / f"{_safe_filename(pmcid)}.html"
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        article_title = _meta(html, "citation_title") or pmcid
        doi = _meta(html, "citation_doi")
        license_text = _license_text(html)
        video_links = _video_links(article_url, html)
        if not video_links:
            gaps.append(
                {
                    "source": PMC_VIDEO_SOURCE_ID,
                    "lane": "media",
                    "reason": "pmc_video_links_missing",
                    "url": article_url,
                    "pmcid": pmcid,
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        for index, video_url in enumerate(video_links, start=1):
            records.append(
                _video_record(
                    article_url=article_url,
                    raw_path=raw_path,
                    pmcid=pmcid,
                    article_title=article_title,
                    doi=doi,
                    license_text=license_text,
                    video_url=video_url,
                    index=index,
                    retrieved_at=retrieved_at,
                )
            )

    return PMCVideosResult(
        source_id=PMC_VIDEO_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        article_count=len(article_urls),
        video_count=len(records),
    )
