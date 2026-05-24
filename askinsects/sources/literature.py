from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


LITERATURE_SOURCE_ID = "aedes_literature_openalex"
OPENALEX_API_BASE = "https://api.openalex.org"
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"


@dataclass(frozen=True)
class FullTextUnit:
    unit_id: str
    record_id: str
    source: str
    unit_index: int
    text: str
    url: str | None
    license: str | None
    provenance: Provenance


@dataclass(frozen=True)
class LiteratureBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    fulltext_units: list[FullTextUnit]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    topic_search_results: list[dict[str, object]]
    accepted_topic_ids: list[str]
    inclusion_path_counts: dict[str, int]
    reported_total_count: int
    page_count: int
    doi_count: int
    unpaywall_queried_count: int
    open_fulltext_count: int
    pubmed_skipped_count: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str | None) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "unknown"


def write_raw_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def abstract_from_inverted_index(index: dict[str, object] | None) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    positions: dict[int, str] = {}
    for term, offsets in index.items():
        if not isinstance(offsets, list):
            continue
        for offset in offsets:
            if isinstance(offset, int):
                positions[offset] = str(term)
    return " ".join(positions[position] for position in sorted(positions))


def openalex_work_key(work: dict[str, object]) -> str:
    work_id = work.get("id")
    if isinstance(work_id, str) and work_id:
        return work_id.rstrip("/").split("/")[-1]
    ids = work.get("ids")
    if isinstance(ids, dict):
        openalex_id = ids.get("openalex")
        if isinstance(openalex_id, str) and openalex_id:
            return openalex_id.rstrip("/").split("/")[-1]
    raise ValueError("OpenAlex work is missing an id")


def fetch_json_url(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"URL returned non-object JSON for {url}")
    return payload


def fetch_text_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("content-type", "")
        if "pdf" in content_type.lower():
            return ""
        return response.read().decode("utf-8", errors="replace")


def normalize_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    match = re.search(r"10\.\S+?/\S+", value, flags=re.IGNORECASE)
    if match:
        value = match.group(0)
    value = value.strip().rstrip(".,;)")
    return value.lower() or None


def unpaywall_url(doi: str, email: str) -> str:
    return f"{UNPAYWALL_API_BASE}/{doi}?{urlencode({'email': email})}"


def best_open_fulltext(unpaywall_payload: dict[str, object]) -> tuple[str, str | None] | None:
    if not unpaywall_payload.get("is_oa"):
        return None
    location = unpaywall_payload.get("best_oa_location")
    if not isinstance(location, dict):
        return None
    url = location.get("url_for_pdf")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        license_value = location.get("license")
        return url, str(license_value) if license_value else None
    return None


def fulltext_units_for_record(
    record_id: str,
    text: str,
    url: str | None,
    license: str | None,
    retrieved_at: str,
) -> list[FullTextUnit]:
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return []
    units: list[FullTextUnit] = []
    for unit_index, start in enumerate(range(0, len(clean_text), 4000)):
        unit_text = clean_text[start : start + 4000]
        units.append(
            FullTextUnit(
                unit_id=f"{record_id}:fulltext:{unit_index}",
                record_id=record_id,
                source=LITERATURE_SOURCE_ID,
                unit_index=unit_index,
                text=unit_text,
                url=url,
                license=license,
                provenance=Provenance(
                    source_id=LITERATURE_SOURCE_ID,
                    locator=f"{record_id}#fulltext/{unit_index}",
                    retrieved_at=retrieved_at,
                    license=license,
                    source_url=url,
                ),
            )
        )
    return units


def _topic_text(topic: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("display_name", "description"):
        value = topic.get(key)
        if isinstance(value, str):
            parts.append(value)
    keywords = topic.get("keywords")
    if isinstance(keywords, list):
        parts.extend(str(keyword) for keyword in keywords)
    return " ".join(parts).lower()


def topic_materially_matches_species(topic: dict[str, object], species: str) -> bool:
    topic_text = _topic_text(topic)
    species_lower = species.lower()
    if species_lower in topic_text:
        return True
    species_parts = [part for part in re.split(r"\s+", species_lower) if part]
    return bool(species_parts) and all(part in topic_text for part in species_parts)


def discover_topic_ids(
    species: str,
    fetch_json: Callable[[str], dict[str, object]],
    raw_dir: Path,
    retrieved_at: str,
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]], list[str]]:
    url = f"{OPENALEX_API_BASE}/topics?{urlencode({'search': species, 'per-page': 25})}"
    payload = fetch_json(url)
    raw_path = write_raw_json(raw_dir, f"{safe_name(species)}_topics.json", payload)
    raw_artifacts = [raw_path.as_posix()]
    results = payload.get("results")
    topic_results = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
    accepted_topic_ids: list[str] = []
    gaps: list[dict[str, object]] = []

    for topic in topic_results:
        topic_id = topic.get("id")
        if topic_materially_matches_species(topic, species) and isinstance(topic_id, str):
            accepted_topic_ids.append(topic_id.rstrip("/").split("/")[-1])
        else:
            external_id = str(topic_id) if topic_id else None
            gaps.append(
                {
                    "source": LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "openalex_topic_candidate_rejected",
                    "locator": f"{raw_path.as_posix()}#topics/{external_id or 'candidate'}",
                    "retrieved_at": retrieved_at,
                    "external_id": external_id,
                    "species": species,
                    "topic": topic,
                }
            )

    if not accepted_topic_ids:
        gaps.append(
            {
                "source": LITERATURE_SOURCE_ID,
                "lane": "literature",
                "reason": "openalex_topic_search_empty",
                "locator": f"{raw_path.as_posix()}#topics",
                "retrieved_at": retrieved_at,
                "external_id": url,
                "species": species,
            }
        )

    return accepted_topic_ids, topic_results, gaps, raw_artifacts


def _doi(work: dict[str, object]) -> str | None:
    doi = work.get("doi")
    if isinstance(doi, str) and doi:
        return normalize_doi(doi)
    ids = work.get("ids")
    if isinstance(ids, dict):
        doi = ids.get("doi")
        if isinstance(doi, str) and doi:
            return normalize_doi(doi)
    return None


def _pubmed_esearch_url(doi: str | None, title: str) -> str:
    term = f"{doi}[AID]" if doi else f"{title}[Title]"
    return f"{PUBMED_API_BASE}/esearch.fcgi?{urlencode({'db': 'pubmed', 'retmode': 'json', 'retmax': 5, 'term': term})}"


def _pubmed_esummary_url(pubmed_ids: list[str]) -> str:
    return f"{PUBMED_API_BASE}/esummary.fcgi?{urlencode({'db': 'pubmed', 'retmode': 'json', 'id': ','.join(pubmed_ids)})}"


def _pubmed_entries(payload: dict[str, object]) -> list[dict[str, object]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    if not isinstance(uids, list):
        return []
    entries: list[dict[str, object]] = []
    for uid in uids:
        entry = result.get(str(uid))
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _pubmed_entry_matches(entry: dict[str, object], doi: str | None, title: str) -> bool:
    if doi:
        elocationid = entry.get("elocationid")
        if isinstance(elocationid, str) and normalize_doi(elocationid) == doi:
            return True
    entry_title = entry.get("title")
    return isinstance(entry_title, str) and normalize_title(entry_title) == normalize_title(title)


def normalize_title(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()


def _pubmed_entry_doi_matches(entry: dict[str, object], doi: str | None) -> bool:
    if not doi:
        return False
    elocationid = entry.get("elocationid")
    return isinstance(elocationid, str) and normalize_doi(elocationid) == doi


def _pubmed_entry_title_matches(entry: dict[str, object], title: str) -> bool:
    entry_title = entry.get("title")
    return isinstance(entry_title, str) and normalize_title(entry_title) == normalize_title(title)


def lookup_pubmed_summary(
    *,
    doi: str | None,
    title: str,
    fetch_json: Callable[[str], dict[str, object]],
    raw_dir: Path,
) -> tuple[dict[str, object] | None, list[str]]:
    if not doi and not title:
        return None, []
    raw_artifacts: list[str] = []
    esearch_payload = fetch_json(_pubmed_esearch_url(doi, title))
    search_key = safe_name(doi or title)
    search_path = write_raw_json(raw_dir / "pubmed", f"{search_key}_esearch.json", esearch_payload)
    raw_artifacts.append(search_path.as_posix())
    esearch_result = esearch_payload.get("esearchresult")
    if not isinstance(esearch_result, dict):
        return None, raw_artifacts
    idlist = esearch_result.get("idlist")
    if not isinstance(idlist, list) or not idlist:
        return None, raw_artifacts
    pubmed_ids = [str(pubmed_id) for pubmed_id in idlist[:5]]
    esummary_payload = fetch_json(_pubmed_esummary_url(pubmed_ids))
    summary_path = write_raw_json(raw_dir / "pubmed", f"{safe_name('_'.join(pubmed_ids))}_esummary.json", esummary_payload)
    raw_artifacts.append(summary_path.as_posix())
    entries = _pubmed_entries(esummary_payload)
    for entry in entries:
        if _pubmed_entry_doi_matches(entry, doi):
            return {"esearch": esearch_payload, "esummary": esummary_payload, "match": entry}, raw_artifacts
    for entry in entries:
        if _pubmed_entry_title_matches(entry, title):
            return {"esearch": esearch_payload, "esummary": esummary_payload, "match": entry}, raw_artifacts
    return None, raw_artifacts


def _venue(work: dict[str, object]) -> str | None:
    primary_location = work.get("primary_location")
    if not isinstance(primary_location, dict):
        return None
    source = primary_location.get("source")
    if isinstance(source, dict) and source.get("display_name"):
        return str(source["display_name"])
    return None


def _topic_ids(work: dict[str, object]) -> set[str]:
    topic_ids: set[str] = set()
    for key in ("primary_topic",):
        topic = work.get(key)
        if isinstance(topic, dict) and isinstance(topic.get("id"), str):
            topic_ids.add(str(topic["id"]).rstrip("/").split("/")[-1])
    topics = work.get("topics")
    if isinstance(topics, list):
        for topic in topics:
            if isinstance(topic, dict) and isinstance(topic.get("id"), str):
                topic_ids.add(str(topic["id"]).rstrip("/").split("/")[-1])
    return topic_ids


def _infer_inclusion_paths(work: dict[str, object], species: str, accepted_topic_ids: list[str]) -> list[str]:
    paths: list[str] = []
    title = str(work.get("display_name") or "")
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))  # type: ignore[arg-type]
    if species.lower() in title.lower():
        paths.append("title")
    if species.lower() in abstract.lower():
        paths.append("abstract")
    if set(accepted_topic_ids).intersection(_topic_ids(work)):
        paths.append("topic")
    return paths or ["openalex_search"]


def literature_record(
    work: dict[str, object],
    raw_path: Path,
    retrieved_at: str,
    inclusion_paths: list[str],
    species: str,
    unpaywall_payload: dict[str, object] | None = None,
    pubmed_payload: dict[str, object] | None = None,
    skip_pubmed: bool = False,
) -> EvidenceRecord:
    work_key = openalex_work_key(work)
    doi = _doi(work)
    title = str(work.get("display_name") or f"OpenAlex work {work_key}")
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))  # type: ignore[arg-type]
    venue = _venue(work) or "unknown venue"
    work_url = str(work.get("id") or f"https://openalex.org/{work_key}")
    parts = [
        f"Title: {title}",
        f"Abstract: {abstract or 'missing'}",
        f"DOI: {doi or 'missing'}",
        f"Venue: {venue}",
        f"Inclusion paths: {', '.join(inclusion_paths)}",
    ]
    payload: dict[str, object] = {
        "raw_openalex_work": work,
        "inclusion_paths": inclusion_paths,
        "unpaywall": unpaywall_payload,
        "pubmed": pubmed_payload,
    }
    if skip_pubmed:
        payload["skip_pubmed"] = True
    return EvidenceRecord(
        record_id=f"openalex:{work_key}",
        lane="literature",
        source=LITERATURE_SOURCE_ID,
        title=title,
        text="\n".join(parts),
        species=species,
        url=doi or work_url,
        media_url=None,
        provenance=Provenance(
            source_id=LITERATURE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#works/{work_key}",
            retrieved_at=retrieved_at,
            license="OpenAlex metadata",
            source_url=work_url,
        ),
        payload=payload,
    )


def _works_url(
    *,
    species: str,
    from_date: str,
    to_date: str,
    work_type: str,
    page_size: int,
    cursor: str,
) -> str:
    filters = [
        ("title_and_abstract.search", f'"{species}"'),
        ("from_publication_date", from_date),
        ("to_publication_date", to_date),
        ("type", work_type),
    ]
    params = {
        "filter": ",".join(f"{key}:{value}" for key, value in filters if value),
        "sort": "publication_date:desc",
        "per-page": page_size,
        "cursor": cursor,
    }
    return f"{OPENALEX_API_BASE}/works?{urlencode(params)}"


def fetch_literature_records(
    *,
    species: str,
    from_date: str,
    to_date: str,
    work_type: str,
    include_topic_discovery: bool,
    raw_dir: Path,
    page_size: int = 200,
    delay_seconds: float = 1.0,
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    fetch_text: Callable[[str], str] | None = None,
    unpaywall_email: str | None = None,
    retrieved_at: str | None = None,
    max_works: int | None = None,
    skip_pubmed: bool = False,
) -> LiteratureBuildResult:
    retrieved = retrieved_at or utc_now()
    json_fetcher = fetch_json or fetch_json_url
    text_fetcher = fetch_text or fetch_text_url
    records: list[EvidenceRecord] = []
    fulltext_units: list[FullTextUnit] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    topic_search_results: list[dict[str, object]] = []
    accepted_topic_ids: list[str] = []
    inclusion_path_counts: dict[str, int] = {}
    reported_total_count = 0
    doi_count = 0
    unpaywall_queried_count = 0
    open_fulltext_count = 0
    pubmed_skipped_count = 0
    page_count = 0
    seen_work_keys: set[str] = set()
    seen_cursors: set[str] = set()
    page_size = max(1, min(int(page_size), 200))
    max_records = None if max_works is None else max(0, int(max_works))

    if include_topic_discovery:
        accepted_topic_ids, topic_search_results, topic_gaps, topic_artifacts = discover_topic_ids(
            species,
            json_fetcher,
            raw_dir,
            retrieved,
        )
        gaps.extend(topic_gaps)
        raw_artifacts.extend(topic_artifacts)

    cursor = "*"
    while cursor:
        seen_cursors.add(cursor)
        if page_count > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)
        url = _works_url(
            species=species,
            from_date=from_date,
            to_date=to_date,
            work_type=work_type,
            page_size=page_size,
            cursor=cursor,
        )
        payload = json_fetcher(url)
        page_count += 1
        raw_path = write_raw_json(raw_dir, f"{safe_name(species)}_openalex_page_{page_count:03d}.json", payload)
        raw_artifacts.append(raw_path.as_posix())

        meta = payload.get("meta")
        if isinstance(meta, dict):
            reported_total_count = int(meta.get("count") or reported_total_count)
            next_cursor = meta.get("next_cursor")
        else:
            next_cursor = None

        results = payload.get("results")
        works = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
        for work in works:
            if max_records is not None and len(records) >= max_records:
                break
            work_key = openalex_work_key(work)
            if work_key in seen_work_keys:
                continue
            seen_work_keys.add(work_key)
            inclusion_paths = _infer_inclusion_paths(work, species, accepted_topic_ids)
            for path in inclusion_paths:
                inclusion_path_counts[path] = inclusion_path_counts.get(path, 0) + 1
            doi = _doi(work)
            unpaywall_payload: dict[str, object] | None = None
            pubmed_payload: dict[str, object] | None = None
            if skip_pubmed:
                pubmed_skipped_count += 1
                gaps.append(
                    {
                        "source": LITERATURE_SOURCE_ID,
                        "lane": "literature",
                        "reason": "pubmed_skipped",
                        "locator": f"{raw_path.as_posix()}#works/{work_key}",
                        "retrieved_at": retrieved,
                        "record_id": f"openalex:{work_key}",
                        "species": species,
                    }
                )
            else:
                try:
                    pubmed_payload, pubmed_artifacts = lookup_pubmed_summary(
                        doi=doi,
                        title=str(work.get("display_name") or ""),
                        fetch_json=json_fetcher,
                        raw_dir=raw_dir,
                    )
                except Exception as exc:
                    gaps.append(
                        {
                            "source": LITERATURE_SOURCE_ID,
                            "lane": "literature",
                            "reason": "pubmed_fetch_failed",
                            "locator": f"{raw_path.as_posix()}#works/{work_key}",
                            "retrieved_at": retrieved,
                            "record_id": f"openalex:{work_key}",
                            "species": species,
                            "error": str(exc),
                        }
                    )
                else:
                    raw_artifacts.extend(pubmed_artifacts)
            if doi:
                doi_count += 1
                if unpaywall_email:
                    unpaywall_payload = json_fetcher(unpaywall_url(doi, unpaywall_email))
                    unpaywall_queried_count += 1
                    unpaywall_path = write_raw_json(
                        raw_dir / "unpaywall",
                        f"{safe_name(doi)}.json",
                        unpaywall_payload,
                    )
                    raw_artifacts.append(unpaywall_path.as_posix())
                    fulltext_target = best_open_fulltext(unpaywall_payload)
                    if fulltext_target:
                        fulltext_url, fulltext_license = fulltext_target
                        try:
                            fulltext = text_fetcher(fulltext_url)
                        except Exception as exc:
                            gaps.append(
                                {
                                    "source": LITERATURE_SOURCE_ID,
                                    "lane": "literature",
                                    "reason": "fulltext_fetch_failed",
                                    "locator": unpaywall_path.as_posix(),
                                    "retrieved_at": retrieved,
                                    "record_id": f"openalex:{work_key}",
                                    "species": species,
                                    "external_id": fulltext_url,
                                    "error": str(exc),
                                }
                            )
                        else:
                            units = fulltext_units_for_record(
                                record_id=f"openalex:{work_key}",
                                text=fulltext,
                                url=fulltext_url,
                                license=fulltext_license,
                                retrieved_at=retrieved,
                            )
                            if units:
                                fulltext_units.extend(units)
                                open_fulltext_count += 1
                            else:
                                gaps.append(
                                    {
                                        "source": LITERATURE_SOURCE_ID,
                                        "lane": "literature",
                                        "reason": "fulltext_parse_failed",
                                        "locator": unpaywall_path.as_posix(),
                                        "retrieved_at": retrieved,
                                        "record_id": f"openalex:{work_key}",
                                        "species": species,
                                        "external_id": fulltext_url,
                                    }
                                )
                    else:
                        unpaywall_location = unpaywall_payload.get("best_oa_location")
                        landing_page = (
                            unpaywall_location.get("url_for_landing_page")
                            if isinstance(unpaywall_location, dict)
                            else None
                        )
                        reason = (
                            "fulltext_landing_page_only"
                            if isinstance(landing_page, str) and landing_page
                            else "unpaywall_no_fulltext_url"
                        )
                        gaps.append(
                            {
                                "source": LITERATURE_SOURCE_ID,
                                "lane": "literature",
                                "reason": reason,
                                "locator": unpaywall_path.as_posix(),
                                "retrieved_at": retrieved,
                                "record_id": f"openalex:{work_key}",
                                "species": species,
                                "external_id": landing_page if isinstance(landing_page, str) else doi,
                            }
                        )
            else:
                locator = f"{raw_path.as_posix()}#works/{work_key}"
                gaps.append(
                    {
                        "source": LITERATURE_SOURCE_ID,
                        "lane": "literature",
                        "reason": "missing_doi",
                        "locator": locator,
                        "retrieved_at": retrieved,
                        "record_id": f"openalex:{work_key}",
                        "species": species,
                    }
                )
            if not abstract_from_inverted_index(work.get("abstract_inverted_index")):  # type: ignore[arg-type]
                locator = f"{raw_path.as_posix()}#works/{work_key}"
                gaps.append(
                    {
                        "source": LITERATURE_SOURCE_ID,
                        "lane": "literature",
                        "reason": "openalex_missing_abstract",
                        "locator": locator,
                        "retrieved_at": retrieved,
                        "record_id": f"openalex:{work_key}",
                        "species": species,
                    }
                )
            records.append(
                literature_record(
                    work,
                    raw_path,
                    retrieved,
                    inclusion_paths,
                    species,
                    unpaywall_payload=unpaywall_payload,
                    pubmed_payload=pubmed_payload,
                    skip_pubmed=skip_pubmed,
                )
            )

        if max_records is not None and len(records) >= max_records:
            break
        if not next_cursor:
            break
        next_cursor_value = str(next_cursor)
        if next_cursor_value in seen_cursors:
            gaps.append(
                {
                    "source": LITERATURE_SOURCE_ID,
                    "lane": "literature",
                    "reason": "openalex_repeated_cursor",
                    "locator": f"{raw_path.as_posix()}#meta/next_cursor",
                    "retrieved_at": retrieved,
                    "external_id": next_cursor_value,
                    "cursor": next_cursor_value,
                }
            )
            break
        cursor = next_cursor_value

    return LiteratureBuildResult(
        source_id=LITERATURE_SOURCE_ID,
        records=records,
        fulltext_units=fulltext_units,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        topic_search_results=topic_search_results,
        accepted_topic_ids=accepted_topic_ids,
        inclusion_path_counts=inclusion_path_counts,
        reported_total_count=reported_total_count,
        page_count=page_count,
        doi_count=doi_count,
        unpaywall_queried_count=unpaywall_queried_count,
        open_fulltext_count=open_fulltext_count,
        pubmed_skipped_count=pubmed_skipped_count,
    )
