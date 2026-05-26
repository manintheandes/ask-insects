from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import re
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID = "aedes_ncvbdc_dengue_surveillance"
USER_AGENT = "AskInsects/0.1 source-plane"
DEFAULT_NCVBDC_DENGUE_PAGE = {
    "organization": "NCVBDC",
    "url": "https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green",
    "page_kind": "india_dengue_cases_deaths",
    "topic": "India national dengue cases and deaths by state and year",
}
YEAR_SPECS: tuple[tuple[int, bool], ...] = (
    (2021, False),
    (2022, False),
    (2023, False),
    (2024, False),
    (2025, False),
    (2026, True),
)


@dataclass(frozen=True)
class NcvbdcDengueSurveillanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    page_count: int
    table_row_count: int
    state_year_record_count: int
    national_year_record_count: int
    recent_summary_count: int


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_td = False
        self._cell_parts: list[str] = []
        self._row: list[str] = []
        self._colspan = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        if tag.lower() in {"td", "th"}:
            self._in_td = True
            self._cell_parts = []
            self._colspan = 1
            for key, value in attrs:
                if key.lower() == "colspan" and value and value.isdigit():
                    self._colspan = max(1, int(value))

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"td", "th"} and self._in_td:
            text = _clean_cell(" ".join(self._cell_parts))
            self._row.extend([text] * self._colspan)
            self._in_td = False
            self._cell_parts = []
            self._colspan = 1
        if lower == "tr" and self._row:
            self.rows.append(self._row)
            self._row = []


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _clean_cell(value: str) -> str:
    text = unescape(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_text(value: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|li|h\d|div|tr)>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_cell(text)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "ncvbdc_dengue"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_").lower() or "unknown"


def _sha(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _int_value(value: str | None) -> int | None:
    if value is None:
        return None
    text = _clean_cell(value).replace(",", "")
    if text in {"", "-", "NR"}:
        return None
    if not re.fullmatch(r"\d+", text):
        return None
    return int(text)


def _provisional_note(html: str) -> str | None:
    text = _clean_text(html)
    match = re.search(r"\*Provisional\s+till\s+(.+?)(?:\s+C=Cases|\s+D=Deaths|\s+NR=Not Reported|$)", text, flags=re.IGNORECASE)
    if not match:
        return None
    note = match.group(1).strip().rstrip(".")
    return f"Provisional till {note}" if note else None


def _table_rows(html: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(html)
    return parser.rows


def _data_rows(rows: list[list[str]]) -> list[dict[str, object]]:
    parsed: list[dict[str, object]] = []
    for row in rows:
        if len(row) < 4:
            continue
        place = row[1].strip() if len(row) > 1 else ""
        if not place or place.lower() == "affected states/uts":
            continue
        if row[0].strip().lower() in {"c", "d"} or place.lower() in {"c", "d"}:
            continue
        if place.lower() == "daman & diu":
            # The source table visually wraps this under the D&N Haveli serial row.
            serial = "34b"
        else:
            serial = row[0].strip()
        if not serial and place.lower() != "total":
            continue
        values = row[2:]
        year_values: dict[int, dict[str, int | None]] = {}
        for index, (year, _) in enumerate(YEAR_SPECS):
            cases = _int_value(values[index * 2] if index * 2 < len(values) else None)
            deaths = _int_value(values[index * 2 + 1] if index * 2 + 1 < len(values) else None)
            year_values[year] = {"cases": cases, "deaths": deaths}
        parsed.append({"serial": serial, "place": place, "years": year_values})
    return parsed


def _page_record(*, source: dict[str, str], raw_path: Path, html: str, retrieved_at: str) -> EvidenceRecord:
    url = source["url"]
    excerpt = _clean_text(html)[:900]
    return EvidenceRecord(
        record_id=f"public_health:surveillance:ncvbdc_dengue:page:{_sha(url)}",
        lane="public_health",
        source=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title="NCVBDC dengue situation in India source page",
        text=(
            "Official Government of India NCVBDC dengue surveillance page for Aedes aegypti public-health intelligence. "
            "The source table reports dengue cases and deaths in India by affected state or union territory and year. "
            f"Page excerpt: {excerpt}."
        ),
        species="Aedes aegypti",
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#page",
            retrieved_at=retrieved_at,
            license="NCVBDC Government of India public web page; source page terms apply",
            source_url=url,
        ),
        payload={
            "organization": source.get("organization", "NCVBDC"),
            "country": "India",
            "disease": "dengue",
            "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": "ncvbdc_dengue_source_page",
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _year_record(
    *,
    source: dict[str, str],
    raw_path: Path,
    place: str,
    serial: str,
    year: int,
    cases: int,
    deaths: int,
    is_provisional: bool,
    provisional_note: str | None,
    retrieved_at: str,
) -> EvidenceRecord:
    is_country = place.lower() == "total"
    geography = "India" if is_country else place
    aggregation_type = "ncvbdc_dengue_country_year" if is_country else "ncvbdc_dengue_state_ut_year"
    record_id = (
        f"public_health:surveillance:ncvbdc_dengue:"
        f"{'country' if is_country else 'state_ut'}:{_safe_id(geography)}:{year}"
    )
    provisional_text = f" {provisional_note}." if is_provisional and provisional_note else ""
    text = (
        f"Official NCVBDC dengue surveillance row for {geography}, {year}. "
        f"Dengue cases: {cases}. Dengue deaths: {deaths}.{provisional_text} "
        "Aedes aegypti relevance: dengue surveillance is indexed as public-health intelligence for the primary dengue vector in India. "
        "This is a human dengue surveillance row, not a mosquito occurrence record."
    )
    return EvidenceRecord(
        record_id=record_id,
        lane="public_health",
        source=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"NCVBDC India dengue surveillance: {geography} {year}",
        text=text,
        species="Aedes aegypti",
        url=source["url"],
        media_url=None,
        provenance=Provenance(
            source_id=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#table-row-{_safe_id(geography)}-{year}",
            retrieved_at=retrieved_at,
            license="NCVBDC Government of India public web page; source page terms apply",
            source_url=source["url"],
        ),
        payload={
            "organization": "NCVBDC",
            "country": "India",
            "state_or_ut": None if is_country else geography,
            "geography": geography,
            "serial": serial,
            "year": year,
            "cases": cases,
            "deaths": deaths,
            "disease": "dengue",
            "is_provisional": is_provisional,
            "provisional_note": provisional_note if is_provisional else None,
            "aedes_relevance": "Dengue surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": aggregation_type,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _recent_summary_record(
    *,
    source: dict[str, str],
    raw_path: Path,
    country_records: list[EvidenceRecord],
    retrieved_at: str,
) -> EvidenceRecord | None:
    complete_records = [
        record
        for record in country_records
        if record.payload and isinstance(record.payload.get("year"), int) and not record.payload.get("is_provisional")
    ]
    complete_records.sort(key=lambda record: int(record.payload["year"]))  # type: ignore[index]
    recent = complete_records[-2:]
    if len(recent) < 2:
        return None
    years = [int(record.payload["year"]) for record in recent]  # type: ignore[index]
    cases_by_year = {int(record.payload["year"]): int(record.payload["cases"]) for record in recent}  # type: ignore[index]
    deaths_by_year = {int(record.payload["year"]): int(record.payload["deaths"]) for record in recent}  # type: ignore[index]
    total_cases = sum(cases_by_year.values())
    total_deaths = sum(deaths_by_year.values())
    years_label = f"{years[0]}-{years[-1]}"
    year_parts = "; ".join(f"{year}: {cases_by_year[year]} cases, {deaths_by_year[year]} deaths" for year in years)
    return EvidenceRecord(
        record_id=f"public_health:surveillance:ncvbdc_dengue:country:last_two_complete_years:{years_label}",
        lane="public_health",
        source=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"NCVBDC India dengue deaths in the two latest complete years ({years_label})",
        text=(
            f"Official NCVBDC India dengue surveillance summary for the two latest complete calendar years in the table, {years_label}. "
            f"Year details: {year_parts}. Total dengue cases: {total_cases}. Total dengue deaths: {total_deaths}. "
            "Aedes aegypti relevance: dengue surveillance is indexed as public-health intelligence for the primary dengue vector in India."
        ),
        species="Aedes aegypti",
        url=source["url"],
        media_url=None,
        provenance=Provenance(
            source_id=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#table-total-{years_label}",
            retrieved_at=retrieved_at,
            license="NCVBDC Government of India public web page; source page terms apply",
            source_url=source["url"],
        ),
        payload={
            "organization": "NCVBDC",
            "country": "India",
            "geography": "India",
            "years": years,
            "cases_by_year": cases_by_year,
            "deaths_by_year": deaths_by_year,
            "total_cases": total_cases,
            "total_deaths": total_deaths,
            "disease": "dengue",
            "is_provisional": False,
            "aedes_relevance": "Dengue surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": "ncvbdc_dengue_country_recent_complete_years",
            "raw_html_path": raw_path.as_posix(),
        },
    )


def fetch_ncvbdc_dengue_surveillance_records(
    sources: list[dict[str, str]] | None = None,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
) -> NcvbdcDengueSurveillanceResult:
    fetcher = fetch_text or _default_fetch_text
    source_list = sources or [DEFAULT_NCVBDC_DENGUE_PAGE]
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    table_row_count = 0
    state_year_record_count = 0
    national_year_record_count = 0
    recent_summary_count = 0
    requested_urls = [source["url"] for source in source_list]

    for source in source_list:
        url = source["url"]
        try:
            html = fetcher(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "ncvbdc_dengue_page_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path = raw_dir / f"{_safe_filename(url)}.html"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        rows = _data_rows(_table_rows(html))
        table_row_count += len(rows)
        if not rows:
            gaps.append(
                {
                    "source": NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "ncvbdc_dengue_table_parse_failed",
                    "url": url,
                    "raw_artifact": raw_path.as_posix(),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        records.append(_page_record(source=source, raw_path=raw_path, html=html, retrieved_at=retrieved_at))
        provisional_note = _provisional_note(html)
        country_records: list[EvidenceRecord] = []
        for row in rows:
            place = str(row["place"])
            serial = str(row["serial"])
            years = row["years"]
            if not isinstance(years, dict):
                continue
            for year, is_provisional in YEAR_SPECS:
                values = years.get(year)
                if not isinstance(values, dict):
                    continue
                cases = values.get("cases")
                deaths = values.get("deaths")
                if not isinstance(cases, int) or not isinstance(deaths, int):
                    continue
                record = _year_record(
                    source=source,
                    raw_path=raw_path,
                    place=place,
                    serial=serial,
                    year=year,
                    cases=cases,
                    deaths=deaths,
                    is_provisional=is_provisional,
                    provisional_note=provisional_note,
                    retrieved_at=retrieved_at,
                )
                records.append(record)
                if place.lower() == "total":
                    country_records.append(record)
                    national_year_record_count += 1
                else:
                    state_year_record_count += 1
        recent = _recent_summary_record(source=source, raw_path=raw_path, country_records=country_records, retrieved_at=retrieved_at)
        if recent:
            records.append(recent)
            recent_summary_count += 1
        else:
            gaps.append(
                {
                    "source": NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "ncvbdc_dengue_recent_complete_year_summary_unavailable",
                    "url": url,
                    "raw_artifact": raw_path.as_posix(),
                    "retrieved_at": retrieved_at,
                }
            )

    return NcvbdcDengueSurveillanceResult(
        source_id=NCVBDC_DENGUE_SURVEILLANCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        page_count=len(raw_artifacts),
        table_row_count=table_row_count,
        state_year_record_count=state_year_record_count,
        national_year_record_count=national_year_record_count,
        recent_summary_count=recent_summary_count,
    )
