from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import html
import json
import re
import subprocess
import time
from pathlib import Path
import tempfile
from typing import Callable, Iterable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit, normalize_doi, safe_name


AEDES_OLFACTION_LITERATURE_SOURCE_ID = "aedes_olfaction_literature"
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_QUERY = (
    '("Aedes aegypti"[Title/Abstract] OR "Ae. aegypti"[Title/Abstract]) AND '
    "(olfaction[Title/Abstract] OR olfactory[Title/Abstract] OR odor[Title/Abstract] OR "
    "odour[Title/Abstract] OR odorant[Title/Abstract] OR chemosensory[Title/Abstract] OR "
    "antenna[Title/Abstract] OR antennal[Title/Abstract] OR Orco[Title/Abstract] OR "
    '"odorant receptor"[Title/Abstract] OR "ionotropic receptor"[Title/Abstract]) AND '
    '("2020/01/01"[Date - Publication] : "3000"[Date - Publication])'
)
PUBMED_LICENSE = "NCBI PubMed metadata; source terms apply"
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"
OPEN_FULLTEXT_USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"
DEFAULT_MAX_FULLTEXT_BYTES = 60_000_000


@dataclass(frozen=True)
class AedesOlfactionLiteratureResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    query: str
    reported_total_count: int
    candidate_count: int
    canonical_literature_row_count: int
    already_indexed_count: int
    pubmed_metadata_ingested_count: int
    fulltext_units: list[FullTextUnit]
    unpaywall_queried_count: int
    open_fulltext_count: int
    fulltext_unit_count: int
    figure_caption_unit_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_raw_bytes(raw_dir: Path, filename: str, payload: bytes) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_bytes(payload)
    return path


def fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": OPEN_FULLTEXT_USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"URL returned non-object JSON for {url}")
            return payload
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_bytes_url(url: str, *, max_bytes: int = DEFAULT_MAX_FULLTEXT_BYTES) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": OPEN_FULLTEXT_USER_AGENT})
    with urlopen(request, timeout=90) as response:
        content_type = response.headers.get("content-type", "")
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"full-text artifact exceeds max_bytes={max_bytes}")
    return payload, content_type


def pdf_to_text(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", "-layout", path.as_posix(), "-"],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "pdftotext failed")
    return completed.stdout


def _eutils_url(endpoint: str, **params: object) -> str:
    values = {key: str(value) for key, value in params.items() if value is not None}
    values.setdefault("retmode", "json")
    values.setdefault("tool", "ask_insects")
    return f"{PUBMED_API_BASE}/{endpoint}.fcgi?{urlencode(values)}"


def _as_string(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _title_key(title: str | None) -> str | None:
    if not title:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", title.lower())
    key = re.sub(r"\b(the|a|an)\b", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return key or None


def _doi_from_article(article: dict[str, object]) -> str | None:
    articleids = article.get("articleids")
    if isinstance(articleids, list):
        for item in articleids:
            if not isinstance(item, dict):
                continue
            if str(item.get("idtype", "")).lower() == "doi":
                doi = normalize_doi(_as_string(item.get("value")))
                if doi:
                    return doi
    elocationid = _as_string(article.get("elocationid"))
    return normalize_doi(elocationid)


def _unpaywall_url(doi: str, email: str) -> str:
    return f"{UNPAYWALL_API_BASE}/{quote(doi, safe='')}?{urlencode({'email': email})}"


def _best_open_fulltext_location(payload: dict[str, object]) -> tuple[str | None, str | None, str | None]:
    locations: list[dict[str, object]] = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    oa_locations = payload.get("oa_locations")
    if isinstance(oa_locations, list):
        locations.extend(item for item in oa_locations if isinstance(item, dict))
    for key in ("url_for_xml", "url_for_pdf", "url"):
        for location in locations:
            url = _as_string(location.get(key))
            if not url:
                continue
            if key == "url" and not _looks_like_direct_fulltext_url(url):
                continue
            license_value = _as_string(location.get("license")) or _as_string(payload.get("license")) or None
            return url, license_value, key
    return None, None, None


def _looks_like_direct_fulltext_url(url: str) -> bool:
    lower = url.lower().split("?", 1)[0]
    return lower.endswith((".pdf", ".xml", ".nxml", ".txt", ".html", ".htm"))


def _extension_for_fulltext(url: str, content_type: str) -> str:
    lowered = (content_type or "").lower()
    path = url.lower().split("?", 1)[0]
    if "xml" in lowered or path.endswith((".xml", ".nxml")):
        return "xml"
    if "html" in lowered or path.endswith((".html", ".htm")):
        return "html"
    if "pdf" in lowered or path.endswith(".pdf"):
        return "pdf"
    return "txt"


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _strip_markup(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_figure_captions(markup: str) -> list[str]:
    captions: list[str] = []
    patterns = (
        r"(?is)<fig\b[^>]*>.*?<caption\b[^>]*>(.*?)</caption>.*?</fig>",
        r"(?is)<figure\b[^>]*>.*?<figcaption\b[^>]*>(.*?)</figcaption>.*?</figure>",
        r"(?is)<figcaption\b[^>]*>(.*?)</figcaption>",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, markup):
            caption = _strip_markup(match.group(1))
            if caption and caption not in captions:
                captions.append(caption)
    return captions


def _extract_text_figure_captions(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    captions: list[str] = []
    pattern = re.compile(
        r"(?is)\b((?:fig(?:ure)?\.?)\s*\d+[a-z]?(?:[.:)\-\s]+).{30,1600}?)(?=\bfig(?:ure)?\.?\s*\d+[a-z]?(?:[.:)\-\s]+)|\breferences\b|\backnowledg|$)"
    )
    for match in pattern.finditer(cleaned):
        caption = match.group(1).strip(" .;")
        caption = re.sub(r"\s+", " ", caption)
        if len(caption) < 40:
            continue
        if caption.lower() in {existing.lower() for existing in captions}:
            continue
        captions.append(caption)
    return captions


def _chunk_text(text: str, *, max_chars: int = 3600) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    while cleaned:
        if len(cleaned) <= max_chars:
            chunks.append(cleaned)
            break
        split_at = cleaned.rfind(". ", 0, max_chars)
        if split_at < 1200:
            split_at = cleaned.rfind(" ", 0, max_chars)
        if split_at < 1200:
            split_at = max_chars
        chunks.append(cleaned[:split_at].strip())
        cleaned = cleaned[split_at:].strip()
    return chunks


def _looks_like_access_challenge(text: str) -> bool:
    lowered = text.lower()
    challenge_terms = (
        "checking your browser",
        "recaptcha",
        "enable javascript",
        "cloudflare",
        "access denied",
        "robot check",
    )
    return any(term in lowered for term in challenge_terms)


def _text_from_fulltext_bytes(
    *,
    payload: bytes,
    content_type: str,
    url: str,
    pdf_parser: Callable[[Path], str],
) -> tuple[str, list[str], str]:
    extension = _extension_for_fulltext(url, content_type)
    sniff = payload.lstrip()[:20].lower()
    if extension == "pdf" and sniff.startswith((b"<html", b"<!doctype", b"<?xml")):
        extension = "html" if sniff.startswith((b"<html", b"<!doctype")) else "xml"
    if extension == "pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            handle.write(payload)
            handle.flush()
            parsed = pdf_parser(Path(handle.name))
            if _looks_like_access_challenge(parsed):
                raise RuntimeError("direct full-text URL returned an access challenge page")
            return parsed, _extract_text_figure_captions(parsed), extension
    markup_or_text = _decode_text(payload)
    figure_captions = _extract_figure_captions(markup_or_text)
    if extension in {"xml", "html"}:
        cleaned = _strip_markup(markup_or_text)
        if _looks_like_access_challenge(cleaned):
            raise RuntimeError("direct full-text URL returned an access challenge page")
        return cleaned, figure_captions, extension
    decoded = _decode_text(payload)
    if _looks_like_access_challenge(decoded):
        raise RuntimeError("direct full-text URL returned an access challenge page")
    return decoded, figure_captions + _extract_text_figure_captions(decoded), extension


def _fulltext_units_for_record(
    *,
    record: EvidenceRecord,
    text: str,
    figure_captions: list[str],
    url: str,
    license_value: str | None,
    retrieved_at: str,
    raw_path: Path,
) -> list[FullTextUnit]:
    units: list[FullTextUnit] = []
    chunks = _chunk_text(text)
    for index, chunk in enumerate(chunks):
        units.append(
            FullTextUnit(
                unit_id=f"{record.record_id}:fulltext:{index}",
                record_id=record.record_id,
                source=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                unit_index=index,
                text=chunk,
                url=url,
                license=license_value,
                provenance=Provenance(
                    source_id=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#fulltext-chunk/{index}",
                    retrieved_at=retrieved_at,
                    license=license_value,
                    source_url=url,
                ),
            )
        )
    offset = len(units)
    for index, caption in enumerate(figure_captions):
        units.append(
            FullTextUnit(
                unit_id=f"{record.record_id}:figure-caption:{index}",
                record_id=record.record_id,
                source=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                unit_index=offset + index,
                text=f"Figure caption: {caption}",
                url=url,
                license=license_value,
                provenance=Provenance(
                    source_id=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#figure-caption/{index}",
                    retrieved_at=retrieved_at,
                    license=license_value,
                    source_url=url,
                ),
            )
        )
    return units


def _authors(article: dict[str, object], limit: int = 8) -> list[str]:
    authors = article.get("authors")
    if not isinstance(authors, list):
        return []
    names: list[str] = []
    for item in authors[:limit]:
        if isinstance(item, dict):
            name = _as_string(item.get("name"))
            if name:
                names.append(name)
    return names


def _pub_year(date_value: str) -> int | None:
    match = re.search(r"\b(20[2-9][0-9]|30[0-9][0-9])\b", date_value)
    return int(match.group(1)) if match else None


def _candidate_ids(search_payload: dict[str, object]) -> tuple[list[str], int]:
    result = search_payload.get("esearchresult")
    if not isinstance(result, dict):
        return [], 0
    raw_ids = result.get("idlist")
    ids = [str(value) for value in raw_ids if value] if isinstance(raw_ids, list) else []
    return ids, _int_value(result.get("count"))


def _summary_articles(summary_payload: dict[str, object]) -> Iterable[tuple[str, dict[str, object]]]:
    result = summary_payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    ids = [str(uid) for uid in uids if uid] if isinstance(uids, list) else []
    return [(pmid, result[pmid]) for pmid in ids if isinstance(result.get(pmid), dict)]


def _existing_index(existing_literature_rows: list[dict[str, object]]) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    by_doi: dict[str, list[dict[str, object]]] = {}
    by_title: dict[str, list[dict[str, object]]] = {}
    for row in existing_literature_rows:
        payload = row.get("payload")
        payload_text = json.dumps(payload, sort_keys=True) if isinstance(payload, dict) else _as_string(row.get("payload_json"))
        text = " ".join(_as_string(row.get(key)) for key in ("record_id", "title", "url"))
        for doi in {normalize_doi(text), normalize_doi(payload_text)}:
            if doi:
                by_doi.setdefault(doi, []).append(row)
        key = _title_key(_as_string(row.get("title")))
        if key:
            by_title.setdefault(key, []).append(row)
    return by_doi, by_title


def _canonical_literature_row_count(existing_literature_rows: list[dict[str, object]]) -> int:
    return sum(1 for row in existing_literature_rows if row.get("source") == "aedes_literature_openalex")


def _coverage_status(
    *,
    doi: str | None,
    title: str,
    by_doi: dict[str, list[dict[str, object]]],
    by_title: dict[str, list[dict[str, object]]],
) -> tuple[str, list[str], list[str]]:
    matches: list[dict[str, object]] = []
    if doi and doi in by_doi:
        matches.extend(by_doi[doi])
    key = _title_key(title)
    if key and key in by_title:
        matches.extend(row for row in by_title[key] if row not in matches)
    if matches:
        return (
            "already_indexed",
            sorted({_as_string(row.get("record_id")) for row in matches if row.get("record_id")}),
            sorted({_as_string(row.get("source")) for row in matches if row.get("source")}),
        )
    return "pubmed_metadata_ingested", [], []


def _record_for_article(
    *,
    pmid: str,
    article: dict[str, object],
    raw_path: Path,
    retrieved_at: str,
    by_doi: dict[str, list[dict[str, object]]],
    by_title: dict[str, list[dict[str, object]]],
) -> EvidenceRecord:
    title = _as_string(article.get("title")) or f"PubMed PMID {pmid}"
    doi = _doi_from_article(article)
    journal = _as_string(article.get("fulljournalname")) or _as_string(article.get("source")) or None
    publication_date = _as_string(article.get("pubdate")) or _as_string(article.get("epubdate"))
    publication_year = _pub_year(publication_date)
    authors = _authors(article)
    status, matched_record_ids, matched_sources = _coverage_status(doi=doi, title=title, by_doi=by_doi, by_title=by_title)
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    payload = {
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "authors": authors,
        "journal": journal,
        "publication_date": publication_date or None,
        "publication_year": publication_year,
        "coverage_status": status,
        "matched_record_ids": matched_record_ids,
        "matched_sources": matched_sources,
        "candidate_source": "pubmed_esearch_esummary",
        "query": PUBMED_QUERY,
        "scope": "Aedes aegypti olfaction, odor, odorant, chemosensory, antenna, Orco, and receptor papers from 2020 onward",
    }
    text_parts = [
        title,
        "Aedes aegypti olfaction literature audit candidate from PubMed since 2020.",
        f"coverage_status={status}",
        f"pmid={pmid}",
    ]
    if doi:
        text_parts.append(f"doi={doi}")
    if journal:
        text_parts.append(f"journal={journal}")
    if publication_date:
        text_parts.append(f"publication_date={publication_date}")
    if authors:
        text_parts.append("authors=" + "; ".join(authors))
    if matched_record_ids:
        text_parts.append("matched_record_ids=" + "; ".join(matched_record_ids[:10]))
    return EvidenceRecord(
        record_id=f"aedes_olfaction_literature:pubmed:{pmid}",
        lane="literature",
        source=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
        title=title,
        text=" ".join(part for part in text_parts if part),
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#result/{pmid}",
            retrieved_at=retrieved_at,
            license=PUBMED_LICENSE,
            source_url=url,
        ),
        payload=payload,
    )


def _record_with_fulltext_payload(
    record: EvidenceRecord,
    *,
    fulltext_status: str,
    fulltext_url: str | None = None,
    fulltext_license: str | None = None,
    fulltext_unit_count: int = 0,
    figure_caption_unit_count: int = 0,
    fulltext_error: str | None = None,
) -> EvidenceRecord:
    payload = dict(record.payload or {})
    payload["fulltext_status"] = fulltext_status
    payload["open_fulltext_url"] = fulltext_url
    payload["open_fulltext_license"] = fulltext_license
    payload["fulltext_unit_count"] = fulltext_unit_count
    payload["figure_caption_unit_count"] = figure_caption_unit_count
    if fulltext_error:
        payload["fulltext_error"] = fulltext_error
    text_parts = [record.text, f"fulltext_status={fulltext_status}"]
    if fulltext_unit_count:
        text_parts.append(f"fulltext_unit_count={fulltext_unit_count}")
    if figure_caption_unit_count:
        text_parts.append(f"figure_caption_unit_count={figure_caption_unit_count}")
    return replace(record, text=" ".join(text_parts), payload=payload)


def _enrich_record_with_open_fulltext(
    *,
    record: EvidenceRecord,
    raw_dir: Path,
    fetch_json: Callable[[str], dict[str, object]],
    fetch_bytes: Callable[[str], tuple[bytes, str]],
    pdf_parser: Callable[[Path], str],
    retrieved_at: str,
    unpaywall_email: str,
    max_fulltext_bytes: int,
) -> tuple[EvidenceRecord, list[FullTextUnit], list[dict[str, object]], list[str], list[str], int, int]:
    doi = _as_string((record.payload or {}).get("doi"))
    if not doi:
        return (
            _record_with_fulltext_payload(record, fulltext_status="unpaywall_missing_doi"),
            [],
            [
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_fulltext_missing_doi",
                    "locator": record.record_id,
                    "retrieved_at": retrieved_at,
                }
            ],
            [],
            [],
            0,
            0,
        )

    gaps: list[dict[str, object]] = []
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    unpaywall_url = _unpaywall_url(doi, unpaywall_email)
    requested_urls.append(unpaywall_url)
    try:
        unpaywall_payload = fetch_json(unpaywall_url)
    except Exception as exc:
        return (
            _record_with_fulltext_payload(record, fulltext_status="unpaywall_fetch_failed", fulltext_error=str(exc)),
            [],
            [
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_unpaywall_fetch_failed",
                    "locator": unpaywall_url,
                    "retrieved_at": retrieved_at,
                    "record_id": record.record_id,
                    "doi": doi,
                    "error": str(exc),
                }
            ],
            raw_artifacts,
            requested_urls,
            1,
            0,
        )
    unpaywall_path = write_raw_json(raw_dir / "unpaywall", f"{safe_name(doi)}.json", unpaywall_payload)
    raw_artifacts.append(unpaywall_path.as_posix())
    fulltext_url, license_value, location_key = _best_open_fulltext_location(unpaywall_payload)
    if not fulltext_url:
        status = "unpaywall_landing_page_only" if _as_string(unpaywall_payload.get("best_oa_location")) else "unpaywall_no_direct_fulltext"
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_no_legal_direct_fulltext",
                "locator": unpaywall_path.as_posix(),
                "retrieved_at": retrieved_at,
                "record_id": record.record_id,
                "doi": doi,
            }
        )
        return (
            _record_with_fulltext_payload(record, fulltext_status=status),
            [],
            gaps,
            raw_artifacts,
            requested_urls,
            1,
            0,
        )

    try:
        payload, content_type = fetch_bytes(fulltext_url)
        if len(payload) > max_fulltext_bytes:
            raise ValueError(f"full-text artifact exceeds max_bytes={max_fulltext_bytes}")
        text, figure_captions, extension = _text_from_fulltext_bytes(
            payload=payload,
            content_type=content_type,
            url=fulltext_url,
            pdf_parser=pdf_parser,
        )
    except Exception as exc:
        return (
            _record_with_fulltext_payload(
                record,
                fulltext_status="open_fulltext_fetch_or_parse_failed",
                fulltext_url=fulltext_url,
                fulltext_license=license_value,
                fulltext_error=str(exc),
            ),
            [],
            [
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_open_fulltext_fetch_or_parse_failed",
                    "locator": fulltext_url,
                    "retrieved_at": retrieved_at,
                    "record_id": record.record_id,
                    "doi": doi,
                    "error": str(exc),
                }
            ],
            raw_artifacts,
            requested_urls,
            1,
            0,
        )

    raw_path = write_raw_bytes(
        raw_dir / "fulltext",
        f"{safe_name(doi)}.{extension}",
        payload,
    )
    raw_artifacts.append(raw_path.as_posix())
    units = _fulltext_units_for_record(
        record=record,
        text=text,
        figure_captions=figure_captions,
        url=fulltext_url,
        license_value=license_value,
        retrieved_at=retrieved_at,
        raw_path=raw_path,
    )
    if not units:
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_open_fulltext_empty_after_parse",
                "locator": raw_path.as_posix(),
                "retrieved_at": retrieved_at,
                "record_id": record.record_id,
                "doi": doi,
            }
        )
        return (
            _record_with_fulltext_payload(
                record,
                fulltext_status="open_fulltext_empty_after_parse",
                fulltext_url=fulltext_url,
                fulltext_license=license_value,
            ),
            [],
            gaps,
            raw_artifacts,
            requested_urls,
            1,
            0,
        )
    figure_unit_count = sum(1 for unit in units if ":figure-caption:" in unit.unit_id)
    enriched = _record_with_fulltext_payload(
        record,
        fulltext_status="open_fulltext_ingested",
        fulltext_url=fulltext_url,
        fulltext_license=license_value,
        fulltext_unit_count=len(units),
        figure_caption_unit_count=figure_unit_count,
    )
    if location_key:
        payload = dict(enriched.payload or {})
        payload["unpaywall_location_key"] = location_key
        enriched = replace(enriched, payload=payload)
    return enriched, units, gaps, raw_artifacts, requested_urls, 1, 1


def fetch_aedes_olfaction_literature_records(
    *,
    raw_dir: Path,
    existing_literature_rows: list[dict[str, object]] | None = None,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    fetch_bytes: Callable[[str], tuple[bytes, str]] | None = None,
    pdf_parser: Callable[[Path], str] | None = None,
    retrieved_at: str | None = None,
    max_results: int = 500,
    page_size: int = 100,
    include_fulltext: bool = True,
    unpaywall_email: str | None = None,
    fulltext_limit: int | None = None,
    delay_seconds: float = 1.0,
    max_fulltext_bytes: int = DEFAULT_MAX_FULLTEXT_BYTES,
) -> AedesOlfactionLiteratureResult:
    retrieved = retrieved_at or utc_now()
    fetch = fetch_json or fetch_json_url
    fetch_fulltext_bytes = fetch_bytes or (lambda url: fetch_bytes_url(url, max_bytes=max_fulltext_bytes))
    parse_pdf = pdf_parser or pdf_to_text
    existing_rows = existing_literature_rows or []
    by_doi, by_title = _existing_index(existing_rows)
    canonical_literature_row_count = _canonical_literature_row_count(existing_rows)
    requested_urls: list[str] = []
    raw_artifacts: list[str] = []
    gaps: list[dict[str, object]] = []
    all_ids: list[str] = []
    reported_total_count = 0
    page = 0

    bounded_page_size = max(1, min(page_size, 200))
    bounded_max_results = max(1, max_results)
    for retstart in range(0, bounded_max_results, bounded_page_size):
        url = _eutils_url(
            "esearch",
            db="pubmed",
            term=PUBMED_QUERY,
            retstart=retstart,
            retmax=bounded_page_size,
            sort="pub+date",
        )
        requested_urls.append(url)
        try:
            search_payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_pubmed_search_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                }
            )
            break
        raw_path = write_raw_json(raw_dir, f"pubmed_esearch_{page + 1:04d}.json", search_payload)
        raw_artifacts.append(raw_path.as_posix())
        ids, reported_count = _candidate_ids(search_payload)
        reported_total_count = max(reported_total_count, reported_count)
        all_ids.extend(uid for uid in ids if uid not in all_ids)
        page += 1
        if len(all_ids) >= min(reported_total_count, bounded_max_results) or not ids:
            break

    if reported_total_count > len(all_ids):
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_result_limit_applied",
                "locator": f"pubmed query; max_results={bounded_max_results}",
                "retrieved_at": retrieved,
                "reported_total_count": reported_total_count,
                "fetched_candidate_count": len(all_ids),
            }
        )
    if canonical_literature_row_count == 0:
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_no_canonical_literature_rows",
                "locator": "records where lane='literature' and source='aedes_literature_openalex'",
                "retrieved_at": retrieved,
                "detail": "Coverage comparison could not check the canonical OpenAlex literature lane in this artifact.",
            }
        )

    records: list[EvidenceRecord] = []
    fulltext_units: list[FullTextUnit] = []
    unpaywall_queried_count = 0
    open_fulltext_count = 0
    fulltext_attempt_count = 0
    missing_email_gap_added = False
    for chunk_index, start in enumerate(range(0, len(all_ids), 100), start=1):
        ids = all_ids[start : start + 100]
        url = _eutils_url("esummary", db="pubmed", id=",".join(ids))
        requested_urls.append(url)
        try:
            summary_payload = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "aedes_olfaction_pubmed_summary_failed",
                    "locator": url,
                    "retrieved_at": retrieved,
                    "error": str(exc),
                    "pmids": ids,
                }
            )
            continue
        raw_path = write_raw_json(raw_dir, f"pubmed_esummary_{chunk_index:04d}.json", summary_payload)
        raw_artifacts.append(raw_path.as_posix())
        for pmid, article in _summary_articles(summary_payload):
            record = _record_for_article(
                pmid=pmid,
                article=article,
                raw_path=raw_path,
                retrieved_at=retrieved,
                by_doi=by_doi,
                by_title=by_title,
            )
            if not include_fulltext:
                record = _record_with_fulltext_payload(record, fulltext_status="fulltext_not_requested")
            elif not unpaywall_email:
                record = _record_with_fulltext_payload(record, fulltext_status="unpaywall_email_not_configured")
                if not missing_email_gap_added:
                    gaps.append(
                        {
                            "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                            "lane": "literature",
                            "reason": "aedes_olfaction_fulltext_email_not_configured",
                            "locator": "unpaywall email",
                            "retrieved_at": retrieved,
                            "detail": "Legal full-text lookup requires a Unpaywall email.",
                        }
                    )
                    missing_email_gap_added = True
            elif fulltext_limit is not None and fulltext_attempt_count >= fulltext_limit:
                record = _record_with_fulltext_payload(record, fulltext_status="fulltext_limit_not_attempted")
            else:
                fulltext_attempt_count += 1
                (
                    record,
                    units,
                    fulltext_gaps,
                    fulltext_artifacts,
                    fulltext_urls,
                    queried,
                    open_count,
                ) = _enrich_record_with_open_fulltext(
                    record=record,
                    raw_dir=raw_dir,
                    fetch_json=fetch,
                    fetch_bytes=fetch_fulltext_bytes,
                    pdf_parser=parse_pdf,
                    retrieved_at=retrieved,
                    unpaywall_email=unpaywall_email,
                    max_fulltext_bytes=max_fulltext_bytes,
                )
                fulltext_units.extend(units)
                gaps.extend(fulltext_gaps)
                raw_artifacts.extend(fulltext_artifacts)
                requested_urls.extend(fulltext_urls)
                unpaywall_queried_count += queried
                open_fulltext_count += open_count
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
            records.append(record)

    if not all_ids and not any(gap.get("reason") == "aedes_olfaction_pubmed_search_failed" for gap in gaps):
        gaps.append(
            {
                "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "aedes_olfaction_no_pubmed_results",
                "locator": "pubmed query",
                "retrieved_at": retrieved,
                "query": PUBMED_QUERY,
            }
        )

    already_indexed_count = sum(1 for record in records if record.payload and record.payload.get("coverage_status") == "already_indexed")
    pubmed_metadata_ingested_count = sum(
        1 for record in records if record.payload and record.payload.get("coverage_status") == "pubmed_metadata_ingested"
    )
    audit_payload = {
        "source": AEDES_OLFACTION_LITERATURE_SOURCE_ID,
        "query": PUBMED_QUERY,
        "reported_total_count": reported_total_count,
        "candidate_count": len(all_ids),
        "canonical_literature_row_count": canonical_literature_row_count,
        "record_count": len(records),
        "already_indexed_count": already_indexed_count,
        "pubmed_metadata_ingested_count": pubmed_metadata_ingested_count,
        "unpaywall_queried_count": unpaywall_queried_count,
        "open_fulltext_count": open_fulltext_count,
        "fulltext_unit_count": len(fulltext_units),
        "figure_caption_unit_count": sum(1 for unit in fulltext_units if ":figure-caption:" in unit.unit_id),
        "gap_count": len(gaps),
        "retrieved_at": retrieved,
    }
    raw_artifacts.append(write_raw_json(raw_dir, "coverage_audit.json", audit_payload).as_posix())
    return AedesOlfactionLiteratureResult(
        source_id=AEDES_OLFACTION_LITERATURE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        query=PUBMED_QUERY,
        reported_total_count=reported_total_count,
        candidate_count=len(all_ids),
        canonical_literature_row_count=canonical_literature_row_count,
        already_indexed_count=already_indexed_count,
        pubmed_metadata_ingested_count=pubmed_metadata_ingested_count,
        fulltext_units=fulltext_units,
        unpaywall_queried_count=unpaywall_queried_count,
        open_fulltext_count=open_fulltext_count,
        fulltext_unit_count=len(fulltext_units),
        figure_caption_unit_count=sum(1 for unit in fulltext_units if ":figure-caption:" in unit.unit_id),
    )
