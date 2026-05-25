from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import csv
import hashlib
import io
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID = "aedes_taxonomy_authorities"
AEDES_WORLDCLIM_SOURCE_ID = "aedes_worldclim_climate"
AEDES_GLOBAL_COMPENDIUM_SOURCE_ID = "aedes_global_compendium_occurrence"
AEDES_POPULATION_GENOMICS_SOURCE_ID = "aedes_population_genomics"
AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID = "aedes_who_resistance_guidance"
AEDES_DEEP_SOURCE_IDS = (
    AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
    AEDES_WORLDCLIM_SOURCE_ID,
    AEDES_GLOBAL_COMPENDIUM_SOURCE_ID,
    AEDES_POPULATION_GENOMICS_SOURCE_ID,
    AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID,
)

USER_AGENT = "AskInsects/0.1 source-plane"
DEFAULT_COMPENDIUM_API_URL = "https://zenodo.org/api/records/4946792"
DEFAULT_NCBI_BIOPROJECT_SEARCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
    + urlencode({"db": "bioproject", "term": "Aedes aegypti population genomics", "retmode": "json", "retmax": "20"})
)

DEFAULT_TAXONOMY_SOURCES: tuple[dict[str, str], ...] = (
    {
        "name": "ECDC Aedes aegypti factsheet",
        "url": "https://www.ecdc.europa.eu/en/disease-vectors/facts/mosquito-factsheets/aedes-aegypti",
        "authority": "ECDC",
    },
    {
        "name": "OECD Aedes aegypti biology consensus",
        "url": "https://www.oecd.org/en/publications/safety-assessment-of-transgenic-organisms-in-the-environment-volume-8_9789264302235-en/full-report/component-7.html",
        "authority": "OECD",
    },
    {
        "name": "Mosquito Taxonomic Inventory Stegomyia page",
        "url": "https://mosquito-taxonomic-inventory.myspecies.info/subgenus-stegomyia-theobald-1901",
        "authority": "Mosquito Taxonomic Inventory",
    },
)

DEFAULT_WORLDCLIM_SOURCES: tuple[dict[str, str], ...] = (
    {
        "name": "WorldClim v2.1 historical climate",
        "url": "https://www.worldclim.org/data/worldclim21.html",
        "authority": "WorldClim",
    },
    {
        "name": "WorldClim historical monthly weather",
        "url": "https://www.worldclim.org/data/monthlywth.html",
        "authority": "WorldClim",
    },
)

DEFAULT_WHO_RESISTANCE_SOURCES: tuple[dict[str, str], ...] = (
    {
        "name": "WHO Aedes insecticide resistance interim guidance",
        "url": "https://www.who.int/publications-detail-redirect/monitoring-and-managing-insecticide-resistance-in-aedes-mosquito-populations",
        "authority": "WHO",
    },
    {
        "name": "WHO discriminating concentrations for mosquito insecticides",
        "url": "https://www.who.int/publications/i/item/9789240045200",
        "authority": "WHO",
    },
)


@dataclass(frozen=True)
class AedesDeepSourcesResult:
    source_ids: tuple[str, ...]
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    source_record_counts: dict[str, int]


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", "replace")


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _default_fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _write_text(raw_dir: Path, filename: str, text: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_bytes(raw_dir: Path, filename: str, payload: bytes) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_bytes(payload)
    return path


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "source"


def _clean_html(value: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</(?:p|li|h\d|div|section)>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _title(html: str, fallback: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        match = re.search(r"<title\b[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return _clean_html(match.group(1)) if match else fallback


def _digest(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _taxonomy_record(source: dict[str, str], raw_path: Path, html: str, retrieved_at: str) -> EvidenceRecord:
    text = _clean_html(html)
    title = _title(html, source["name"])
    synonym_bits = "; ".join(re.findall(r"(?i)(?:synonyms?[^.]{0,180}|Stegomyia aegypti|Culex aegypti)", text)[:5])
    classification_terms = [
        term
        for term in ("Diptera", "Culicidae", "Culicinae", "Aedini", "Aedes", "Stegomyia", "Aedes aegypti")
        if term.lower() in text.lower()
    ]
    record_text = " ".join(
        part
        for part in (
            f"{source['authority']} taxonomy authority page for Aedes aegypti.",
            f"Title: {title}.",
            f"Classification terms: {', '.join(classification_terms)}." if classification_terms else "",
            f"Synonym/name evidence: {synonym_bits}." if synonym_bits else "",
            f"Excerpt: {text[:900]}.",
        )
        if part
    )
    return EvidenceRecord(
        record_id=f"taxonomy:authority:aedes_aegypti:{_digest(source['url'])}",
        lane="taxonomy",
        source=AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
        title=f"Aedes aegypti taxonomy authority: {title}",
        text=record_text,
        species="Aedes aegypti",
        url=source["url"],
        media_url=None,
        provenance=Provenance(
            source_id=AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license=f"{source['authority']} public web page; source terms apply",
            source_url=source["url"],
        ),
        payload={
            "authority": source["authority"],
            "title": title,
            "classification_terms": classification_terms,
            "synonym_evidence": synonym_bits,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _worldclim_record(source: dict[str, str], raw_path: Path, html: str, retrieved_at: str) -> EvidenceRecord:
    text = _clean_html(html)
    title = _title(html, source["name"])
    variables = [term for term in ("tavg", "tmin", "tmax", "prec", "bio", "GeoTiff", "temperature", "precipitation") if term.lower() in text.lower()]
    record_text = (
        f"WorldClim climate source for Aedes aegypti ecology joins. Title: {title}. "
        f"Variables mentioned: {', '.join(variables)}. "
        "This record makes the climate source boundary queryable; raster sampling is represented separately as a source gap unless local GeoTIFFs are supplied. "
        f"Excerpt: {text[:900]}."
    )
    return EvidenceRecord(
        record_id=f"ecology:worldclim:source:{_digest(source['url'])}",
        lane="ecology",
        source=AEDES_WORLDCLIM_SOURCE_ID,
        title=f"WorldClim climate source: {title}",
        text=record_text,
        species="Aedes aegypti",
        url=source["url"],
        media_url=None,
        provenance=Provenance(
            source_id=AEDES_WORLDCLIM_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="WorldClim public climate data; source terms apply",
            source_url=source["url"],
        ),
        payload={"authority": "WorldClim", "title": title, "variables": variables, "raw_html_path": raw_path.as_posix()},
    )


def _compendium_csv_url(payload: dict[str, object]) -> str | None:
    files = payload.get("files")
    if not isinstance(files, list):
        return None
    for item in files:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("filename") or "")
        links = item.get("links")
        if "aegypti" in key.lower() and "csv" in key.lower() and isinstance(links, dict):
            return str(links.get("self") or links.get("download") or links.get("content") or "") or None
    return None


def _row_get(row: dict[str, str], *names: str) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value.strip()
    return ""


def _is_aegypti_row(row: dict[str, str]) -> bool:
    text = " ".join(row.values()).lower()
    return "aegypti" in text and ("aedes" in text or "ae." in text)


def _compendium_records(csv_bytes: bytes, raw_path: Path, retrieved_at: str, source_url: str, limit: int) -> list[EvidenceRecord]:
    decoded = csv_bytes.decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    records: list[EvidenceRecord] = []
    for index, row in enumerate(reader, start=1):
        if not _is_aegypti_row(row):
            continue
        country = _row_get(row, "country", "COUNTRY", "Country")
        lat = _row_get(row, "latitude", "lat", "Latitude", "Y")
        lon = _row_get(row, "longitude", "lon", "Long", "X")
        year = _row_get(row, "year", "YEAR", "Year")
        status = _row_get(row, "status", "presence", "Occurrence")
        species = _row_get(row, "species", "SPECIES", "ScientificName", "VECTOR") or "Aedes aegypti"
        text = (
            f"Global Aedes occurrence compendium row for {species}. "
            f"Country: {country or 'unknown'}. Coordinates: {lat or 'unknown'}, {lon or 'unknown'}. "
            f"Year: {year or 'unknown'}. Status: {status or 'occurrence record'}. "
            "Source is the Kraemer et al. global compendium of Aedes aegypti and Ae. albopictus occurrence."
        )
        records.append(
            EvidenceRecord(
                record_id=f"occurrence:global_compendium:aedes_aegypti:{index}",
                lane="observations",
                source=AEDES_GLOBAL_COMPENDIUM_SOURCE_ID,
                title=f"Global compendium Aedes aegypti occurrence row {index}",
                text=text,
                species="Aedes aegypti",
                url=source_url,
                media_url=None,
                provenance=Provenance(
                    source_id=AEDES_GLOBAL_COMPENDIUM_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#row/{index}",
                    retrieved_at=retrieved_at,
                    license="Dryad/Zenodo dataset; source terms apply",
                    source_url=source_url,
                ),
                payload={"row_index": index, "row": row, "country": country, "latitude": lat, "longitude": lon, "year": year, "status": status},
            )
        )
        if len(records) >= limit:
            break
    return records


def _bioproject_summary_url(ids: list[str]) -> str:
    return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode({"db": "bioproject", "id": ",".join(ids), "retmode": "json"})


def _population_genomics_records(payload: dict[str, object], raw_path: Path, retrieved_at: str, source_url: str) -> list[EvidenceRecord]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    uids = result.get("uids")
    if not isinstance(uids, list):
        return []
    records: list[EvidenceRecord] = []
    for uid in uids:
        item = result.get(str(uid))
        if not isinstance(item, dict):
            continue
        acc = str(item.get("project_acc") or uid)
        title = str(item.get("project_title") or item.get("project_name") or acc)
        desc = str(item.get("project_description") or "")
        data_type = str(item.get("project_data_type") or "")
        scope = str(item.get("project_target_scope") or "")
        org = str(item.get("submitter_organization") or "")
        date = str(item.get("registration_date") or "")
        text = (
            f"NCBI BioProject population-genomics record {acc} for Aedes aegypti. "
            f"Title: {title}. Data type: {data_type}. Target scope: {scope}. Submitter: {org}. Registration date: {date}. "
            f"Description: {desc}."
        )
        records.append(
            EvidenceRecord(
                record_id=f"population_genomics:bioproject:{acc}",
                lane="genome_features",
                source=AEDES_POPULATION_GENOMICS_SOURCE_ID,
                title=f"Aedes population genomics BioProject {acc}: {title}",
                text=text,
                species="Aedes aegypti",
                url=f"https://www.ncbi.nlm.nih.gov/bioproject/{acc}",
                media_url=None,
                provenance=Provenance(
                    source_id=AEDES_POPULATION_GENOMICS_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#result/{acc}",
                    retrieved_at=retrieved_at,
                    license="NCBI E-utilities public metadata; source terms apply",
                    source_url=source_url,
                ),
                payload={"uid": uid, "accession": acc, "title": title, "description": desc, "data_type": data_type, "target_scope": scope, "submitter": org, "registration_date": date},
            )
        )
    return records


def _who_resistance_record(source: dict[str, str], raw_path: Path, html: str, retrieved_at: str) -> EvidenceRecord:
    text = _clean_html(html)
    title = _title(html, source["name"])
    method_terms = [
        term
        for term in ("test procedures", "discriminating concentrations", "bioassays", "filter paper", "bottle bioassays", "larvae", "adults", "pyriproxyfen", "Bti")
        if term.lower() in text.lower()
    ]
    record_text = (
        f"WHO Aedes insecticide-resistance method source. Title: {title}. "
        f"Method terms: {', '.join(method_terms)}. "
        f"Excerpt: {text[:900]}."
    )
    return EvidenceRecord(
        record_id=f"resistance:who_guidance:{_digest(source['url'])}",
        lane="resistance",
        source=AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID,
        title=f"WHO Aedes resistance guidance: {title}",
        text=record_text,
        species="Aedes aegypti",
        url=source["url"],
        media_url=None,
        provenance=Provenance(
            source_id=AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="WHO public web page; source terms apply",
            source_url=source["url"],
        ),
        payload={"authority": "WHO", "title": title, "method_terms": method_terms, "raw_html_path": raw_path.as_posix()},
    )


def fetch_aedes_deep_source_records(
    *,
    raw_dir: Path,
    fetch_text=None,
    fetch_json=None,
    fetch_bytes=None,
    retrieved_at: str,
    compendium_row_limit: int = 5000,
    bioproject_limit: int = 20,
) -> AedesDeepSourcesResult:
    get_text = fetch_text or _default_fetch_text
    get_json = fetch_json or _default_fetch_json
    get_bytes = fetch_bytes or _default_fetch_bytes
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    for source in DEFAULT_TAXONOMY_SOURCES:
        requested_urls.append(source["url"])
        try:
            html = get_text(source["url"])
            raw_path = _write_text(raw_dir / "taxonomy_authorities", f"{_safe_filename(source['name'])}.html", html)
            raw_artifacts.append(raw_path.as_posix())
            records.append(_taxonomy_record(source, raw_path, html, retrieved_at))
        except Exception as exc:  # noqa: BLE001
            gaps.append({"source": AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID, "reason": "taxonomy_authority_fetch_failed", "url": source["url"], "error": str(exc), "retrieved_at": retrieved_at})

    for source in DEFAULT_WORLDCLIM_SOURCES:
        requested_urls.append(source["url"])
        try:
            html = get_text(source["url"])
            raw_path = _write_text(raw_dir / "worldclim", f"{_safe_filename(source['name'])}.html", html)
            raw_artifacts.append(raw_path.as_posix())
            records.append(_worldclim_record(source, raw_path, html, retrieved_at))
        except Exception as exc:  # noqa: BLE001
            gaps.append({"source": AEDES_WORLDCLIM_SOURCE_ID, "reason": "worldclim_source_fetch_failed", "url": source["url"], "error": str(exc), "retrieved_at": retrieved_at})
    gaps.append({"source": AEDES_WORLDCLIM_SOURCE_ID, "reason": "worldclim_raster_sampling_not_enabled", "retrieved_at": retrieved_at, "detail": "WorldClim source pages are indexed; per-observation raster value joins require mirrored GeoTIFFs or a bounded raster-sampling job."})

    requested_urls.append(DEFAULT_COMPENDIUM_API_URL)
    try:
        compendium_payload = get_json(DEFAULT_COMPENDIUM_API_URL)
        api_path = _write_json(raw_dir / "global_compendium_occurrence", "zenodo_record_4946792.json", compendium_payload)
        raw_artifacts.append(api_path.as_posix())
        csv_url = _compendium_csv_url(compendium_payload)
        if not csv_url:
            gaps.append({"source": AEDES_GLOBAL_COMPENDIUM_SOURCE_ID, "reason": "global_compendium_csv_not_found", "url": DEFAULT_COMPENDIUM_API_URL, "retrieved_at": retrieved_at})
        else:
            requested_urls.append(csv_url)
            csv_bytes = get_bytes(csv_url)
            csv_path = _write_bytes(raw_dir / "global_compendium_occurrence", "aegypti_albopictus.csv", csv_bytes)
            raw_artifacts.append(csv_path.as_posix())
            records.extend(_compendium_records(csv_bytes, csv_path, retrieved_at, csv_url, compendium_row_limit))
    except Exception as exc:  # noqa: BLE001
        gaps.append({"source": AEDES_GLOBAL_COMPENDIUM_SOURCE_ID, "reason": "global_compendium_fetch_failed", "url": DEFAULT_COMPENDIUM_API_URL, "error": str(exc), "retrieved_at": retrieved_at})

    requested_urls.append(DEFAULT_NCBI_BIOPROJECT_SEARCH_URL)
    try:
        search_payload = get_json(DEFAULT_NCBI_BIOPROJECT_SEARCH_URL)
        search_path = _write_json(raw_dir / "population_genomics", "ncbi_bioproject_population_genomics_search.json", search_payload)
        raw_artifacts.append(search_path.as_posix())
        result = search_payload.get("esearchresult") if isinstance(search_payload, dict) else {}
        ids = result.get("idlist") if isinstance(result, dict) else []
        ids = [str(item) for item in ids[:bioproject_limit]] if isinstance(ids, list) else []
        if not ids:
            gaps.append({"source": AEDES_POPULATION_GENOMICS_SOURCE_ID, "reason": "population_genomics_bioproject_search_empty", "url": DEFAULT_NCBI_BIOPROJECT_SEARCH_URL, "retrieved_at": retrieved_at})
        else:
            summary_url = _bioproject_summary_url(ids)
            requested_urls.append(summary_url)
            summary_payload = get_json(summary_url)
            summary_path = _write_json(raw_dir / "population_genomics", "ncbi_bioproject_population_genomics_summary.json", summary_payload)
            raw_artifacts.append(summary_path.as_posix())
            records.extend(_population_genomics_records(summary_payload, summary_path, retrieved_at, summary_url))
    except Exception as exc:  # noqa: BLE001
        gaps.append({"source": AEDES_POPULATION_GENOMICS_SOURCE_ID, "reason": "population_genomics_bioproject_fetch_failed", "url": DEFAULT_NCBI_BIOPROJECT_SEARCH_URL, "error": str(exc), "retrieved_at": retrieved_at})

    for source in DEFAULT_WHO_RESISTANCE_SOURCES:
        requested_urls.append(source["url"])
        try:
            html = get_text(source["url"])
            raw_path = _write_text(raw_dir / "who_resistance_guidance", f"{_safe_filename(source['name'])}.html", html)
            raw_artifacts.append(raw_path.as_posix())
            records.append(_who_resistance_record(source, raw_path, html, retrieved_at))
        except Exception as exc:  # noqa: BLE001
            gaps.append({"source": AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID, "reason": "who_resistance_guidance_fetch_failed", "url": source["url"], "error": str(exc), "retrieved_at": retrieved_at})

    counts = {source_id: 0 for source_id in AEDES_DEEP_SOURCE_IDS}
    for record in records:
        counts[record.source] = counts.get(record.source, 0) + 1
    return AedesDeepSourcesResult(
        source_ids=AEDES_DEEP_SOURCE_IDS,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        source_record_counts=counts,
    )
