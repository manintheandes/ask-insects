from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import hashlib
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance


PAHO_DENGUE_SURVEILLANCE_SOURCE_ID = "aedes_paho_dengue_surveillance"
USER_AGENT = "AskInsects/0.1 source-plane"

DEFAULT_PAHO_DENGUE_REPORTS: tuple[dict[str, str], ...] = (
    {
        "organization": "PAHO/WHO",
        "url": "https://ais.paho.org/ArboPortal/AME_DENG_Situation_Report_SP_2024.asp?env=pri",
        "landing_url": "https://www.paho.org/en/arbo-portal/dengue/situacion-epidemiologica-dengue",
        "language": "es",
        "topic": "regional dengue epidemiological situation report",
    },
)

DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES: tuple[str, ...] = (
    "https://www.paho.org/en/arbo-portal/dengue-data-and-analysis",
    "https://www.paho.org/en/arbo-portal/dengue-data-and-analysis/dengue-analysis-country",
)


@dataclass(frozen=True)
class PahoDengueSurveillanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    report_count: int
    dashboard_page_count: int


def _default_fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _clean_text(value: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|li|h\d|div)>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "paho_dengue"


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


def _int_value(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace(",", "").replace(".", "")
    try:
        return int(normalized)
    except ValueError:
        return None


def _float_value(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _first(pattern: str, text: str, flags: int = re.IGNORECASE | re.DOTALL) -> str | None:
    match = re.search(pattern, text, flags=flags)
    return match.group(1).strip() if match else None


def _metric_int(section: str, pattern: str) -> int | None:
    return _int_value(_first(pattern, section))


def _metric_percent(section: str, pattern: str) -> float | None:
    return _float_value(_first(pattern, section))


def _week_year(text: str) -> tuple[int | None, int | None]:
    week = _int_value(_first(r"semana epidemiol[oó]gica\s+(\d+)", text))
    year = _int_value(_first(r"semana epidemiol[oó]gica\s+\d+,\s*(\d{4})", text))
    return week, year


def _section_between(text: str, start_pattern: str, end_pattern: str) -> str:
    match = re.search(start_pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    start = match.start()
    end_match = re.search(end_pattern, text[match.end() :], flags=re.IGNORECASE)
    end = match.end() + end_match.start() if end_match else len(text)
    return text[start:end].strip()


def _indicator_metrics(section: str) -> dict[str, int | float | None]:
    return {
        "suspected_cases": _metric_int(section, r"([\d,.]+)\s+casos sospechosos"),
        "confirmed_cases": _metric_int(section, r"([\d,.]+)\s+casos confirmados"),
        "confirmed_percent": _metric_percent(section, r"casos confirmados\s*\(?\s*([\d,.]+)%"),
        "severe_cases": _metric_int(section, r"([\d,.]+)\s+(?:casos de dengue grave|dengue grave)"),
        "deaths": _metric_int(section, r"([\d,.]+)\s+muertes"),
        "case_fatality_percent": _metric_percent(section, r"([\d,.]+)%\s+letalidad"),
        "reporting_countries": _metric_int(section, r"([\d,.]+)\s+pa[ií]ses con datos reportados"),
    }


def _has_any_metric(metrics: dict[str, int | float | None]) -> bool:
    return any(value is not None for value in metrics.values())


def _report_summary_metrics(text: str) -> dict[str, int | float | None]:
    return {
        "cumulative_incidence_per_100k": _metric_percent(text, r"incidencia acumulada de\s+([\d,.]+)\s+casos por 100,000"),
        "increase_vs_prior_year_percent": _metric_percent(text, r"incremento de\s+([\d,.]+)%\s+en comparaci[oó]n al mismo periodo del\s+2023"),
        "increase_vs_five_year_average_percent": _metric_percent(text, r"([\d,.]+)%\s+con respecto al promedio de los [uú]ltimos 5 a[ñn]os"),
    }


def _split_countries(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = re.sub(r"\s+", " ", value)
    cleaned = cleaned.replace(" ,", ",").replace(", ", ",")
    return [country.strip() for country in cleaned.split(",") if country.strip()]


def _subregion_records(
    *,
    text: str,
    raw_path: Path,
    report_url: str,
    retrieved_at: str,
    epi_week: int | None,
    year: int | None,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    subregion_text = _section_between(text, r"An[aá]lisis por subregi[oó]n", r"Distribuci[oó]n geogr[aá]fica de serotipos")
    subregion_pattern = (
        r"Subregi[oó]n\s+([^\.]+)\.\s+"
        r"((?:Un total|Se registran|En la SE|Se notifican).*?)(?=Subregi[oó]n\s+|Gr[aá]fico 3|$)"
    )
    for match in re.finditer(subregion_pattern, subregion_text, flags=re.IGNORECASE | re.DOTALL):
        subregion = match.group(1).strip()
        body = match.group(2).strip()
        new_cases = _metric_int(body, r"([\d,.]+)\.?\s+nuevos casos sospechosos")
        if new_cases is None:
            continue
        increase_countries: list[str] = []
        if "Ningún país" not in body and "Ningun pais" not in body:
            countries_text = _first(r"([A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s,()]+?)\s+muestra[n]?\s+un incremento", body)
            increase_countries = _split_countries(countries_text)
        record_id = (
            "public_health:surveillance:paho_dengue:"
            f"subregion:{_normalize_id(subregion).lower()}:{year or 'unknown'}:week{epi_week or 'unknown'}"
        )
        text_parts = [
            f"PAHO dengue surveillance subregion summary for {subregion}.",
            f"Epidemiological week {epi_week}, {year}." if epi_week and year else "",
            f"New suspected dengue cases: {new_cases}." if new_cases is not None else "",
            (
                f"Countries or territories with increased cases versus the prior four epidemiological weeks: {', '.join(increase_countries)}."
                if increase_countries
                else "No countries or territories with an increase were listed in this subregion section."
            ),
            "Aedes aegypti relevance: dengue is indexed here as Aedes-relevant public-health surveillance, not as mosquito abundance.",
        ]
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane="public_health",
                source=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                title=f"PAHO dengue surveillance subregion: {subregion} week {epi_week}, {year}",
                text=" ".join(part for part in text_parts if part),
                species="Aedes aegypti",
                url=report_url,
                media_url=None,
                provenance=Provenance(
                    source_id=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#subregion-{_normalize_id(subregion)}",
                    retrieved_at=retrieved_at,
                    license="PAHO/WHO public health surveillance page; source page terms apply",
                    source_url=report_url,
                ),
                payload={
                    "organization": "PAHO/WHO",
                    "disease": "dengue",
                    "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
                    "aggregation_type": "subregion_week_summary",
                    "subregion": subregion,
                    "year": year,
                    "epi_week": epi_week,
                    "new_suspected_cases": new_cases,
                    "countries_with_increase": increase_countries,
                    "raw_html_path": raw_path.as_posix(),
                },
            )
        )
    return records


def _figure_records(
    *,
    html: str,
    raw_path: Path,
    report_url: str,
    retrieved_at: str,
    epi_week: int | None,
    year: int | None,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    pattern = re.compile(
        r"<p[^>]*>\s*<b>\s*((?:Gr[aá]fico|Tabla)\s+(\d+)\.)\s*</b>(.*?)</p>\s*<img\s+src=[\"']([^\"']+)[\"']",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        figure_label = _clean_text(match.group(1))
        figure_number = match.group(2)
        caption = _clean_text(match.group(3))
        media_url = urljoin(report_url, match.group(4))
        normalized_label = "table" if "Tabla" in figure_label else "graph"
        record_id = (
            "public_health:surveillance:paho_dengue:"
            f"visual:{normalized_label}_{figure_number}:{year or 'unknown'}:week{epi_week or 'unknown'}"
        )
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane="public_health",
                source=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                title=f"PAHO dengue surveillance {figure_label} {year or ''}",
                text=(
                    f"Official PAHO dengue surveillance visual: {figure_label} {caption}. "
                    "Aedes aegypti relevance: dengue public-health surveillance, with the source image preserved as media."
                ),
                species="Aedes aegypti",
                url=report_url,
                media_url=media_url,
                provenance=Provenance(
                    source_id=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#visual-{normalized_label}-{figure_number}",
                    retrieved_at=retrieved_at,
                    license="PAHO/WHO public health surveillance page; source page terms apply",
                    source_url=report_url,
                ),
                payload={
                    "organization": "PAHO/WHO",
                    "disease": "dengue",
                    "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
                    "aggregation_type": "surveillance_visual",
                    "figure_label": figure_label,
                    "figure_number": figure_number,
                    "caption": caption,
                    "year": year,
                    "epi_week": epi_week,
                    "media_url": media_url,
                    "raw_html_path": raw_path.as_posix(),
                },
            )
        )
    return records


def _regional_records(
    *,
    html: str,
    raw_path: Path,
    report_url: str,
    landing_url: str | None,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    text = _clean_text(html)
    epi_week, year = _week_year(text)
    updated_at = _first(r"Actualizado:\s*([^\.]+?)\s+Situaci[oó]n", text)
    weekly_section = _section_between(text, r"Indicadores de la semana\s+\d+,\s*\d{4}", r"Indicadores de las semanas")
    cumulative_section = _section_between(text, r"Indicadores de las semanas\s+1\s*-\s*\d+,\s*\d{4}", r"Entre las semanas")
    weekly_metrics = _indicator_metrics(weekly_section)
    cumulative_metrics = _indicator_metrics(cumulative_section)
    cumulative_metrics.update(_report_summary_metrics(text))
    records = []
    if epi_week is not None and year is not None and _has_any_metric(weekly_metrics):
        records.append(
            _regional_record(
                aggregation_type="regional_week_summary",
                metrics=weekly_metrics,
                raw_path=raw_path,
                report_url=report_url,
                landing_url=landing_url,
                retrieved_at=retrieved_at,
                epi_week=epi_week,
                year=year,
                updated_at=updated_at,
            )
        )
    if epi_week is not None and year is not None and _has_any_metric(cumulative_metrics):
        records.append(
            _regional_record(
                aggregation_type="regional_year_to_date_summary",
                metrics=cumulative_metrics,
                raw_path=raw_path,
                report_url=report_url,
                landing_url=landing_url,
                retrieved_at=retrieved_at,
                epi_week=epi_week,
                year=year,
                updated_at=updated_at,
            )
        )
    records.extend(_subregion_records(text=text, raw_path=raw_path, report_url=report_url, retrieved_at=retrieved_at, epi_week=epi_week, year=year))
    serotype_record = _serotype_record(text=text, raw_path=raw_path, report_url=report_url, retrieved_at=retrieved_at, epi_week=epi_week, year=year)
    if serotype_record:
        records.append(serotype_record)
    records.extend(_figure_records(html=html, raw_path=raw_path, report_url=report_url, retrieved_at=retrieved_at, epi_week=epi_week, year=year))
    return records


def _regional_record(
    *,
    aggregation_type: str,
    metrics: dict[str, int | float | None],
    raw_path: Path,
    report_url: str,
    landing_url: str | None,
    retrieved_at: str,
    epi_week: int | None,
    year: int | None,
    updated_at: str | None,
) -> EvidenceRecord:
    label = "week" if aggregation_type == "regional_week_summary" else "year to date"
    metric_text = ", ".join(
        f"{key.replace('_', ' ')}: {value}"
        for key, value in metrics.items()
        if value is not None
    )
    record_id = f"public_health:surveillance:paho_dengue:{aggregation_type}:{year or 'unknown'}:week{epi_week or 'unknown'}"
    return EvidenceRecord(
        record_id=record_id,
        lane="public_health",
        source=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"PAHO dengue surveillance {label} summary week {epi_week}, {year}",
        text=(
            f"PAHO dengue surveillance {label} summary for the Region of the Americas. "
            f"Epidemiological week {epi_week}, {year}. Metrics: {metric_text}. "
            "Aedes aegypti relevance: dengue is indexed as Aedes-relevant public-health surveillance, not as mosquito abundance."
        ),
        species="Aedes aegypti",
        url=report_url,
        media_url=None,
        provenance=Provenance(
            source_id=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#{aggregation_type}",
            retrieved_at=retrieved_at,
            license="PAHO/WHO public health surveillance page; source page terms apply",
            source_url=report_url,
        ),
        payload={
            "organization": "PAHO/WHO",
            "disease": "dengue",
            "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": aggregation_type,
            "region": "Region of the Americas",
            "year": year,
            "epi_week": epi_week,
            "report_updated_at": updated_at,
            "metrics": metrics,
            "report_url": report_url,
            "landing_url": landing_url,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _serotype_record(
    *,
    text: str,
    raw_path: Path,
    report_url: str,
    retrieved_at: str,
    epi_week: int | None,
    year: int | None,
) -> EvidenceRecord | None:
    serotype_text = _first(r"(Los cuatro serotipos.*?Ver gr[aá]fico 8\)?\.?)", text)
    if not serotype_text:
        return None
    countries = _split_countries(_first(r"En\s+\d+\s+pa[ií]ses de la Regi[oó]n\s*\((.*?)\)\s+se reporta la circulaci[oó]n simult[aá]nea", serotype_text))
    record_id = f"public_health:surveillance:paho_dengue:serotypes:{year or 'unknown'}:week{epi_week or 'unknown'}"
    return EvidenceRecord(
        record_id=record_id,
        lane="public_health",
        source=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=f"PAHO dengue serotype surveillance week {epi_week}, {year}",
        text=(
            "PAHO dengue surveillance reports DENV-1, DENV-2, DENV-3, and DENV-4 in the Region of the Americas. "
            f"Countries or territories reporting simultaneous circulation of all four serotypes: {', '.join(countries)}. "
            "Aedes aegypti relevance: dengue serotype circulation is indexed as Aedes-relevant public-health surveillance."
        ),
        species="Aedes aegypti",
        url=report_url,
        media_url=None,
        provenance=Provenance(
            source_id=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#serotypes",
            retrieved_at=retrieved_at,
            license="PAHO/WHO public health surveillance page; source page terms apply",
            source_url=report_url,
        ),
        payload={
            "organization": "PAHO/WHO",
            "disease": "dengue",
            "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
            "aggregation_type": "serotype_regional_summary",
            "region": "Region of the Americas",
            "year": year,
            "epi_week": epi_week,
            "serotypes": ["DENV-1", "DENV-2", "DENV-3", "DENV-4"],
            "countries_with_all_four_serotypes": countries,
            "raw_html_path": raw_path.as_posix(),
        },
    )


def _dashboard_gap(url: str, html: str, raw_path: Path, retrieved_at: str) -> dict[str, object]:
    iframe_urls = re.findall(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    return {
        "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        "lane": "public_health",
        "reason": "paho_dashboard_data_not_yet_cell_queryable",
        "url": url,
        "raw_html_path": raw_path.as_posix(),
        "iframe_urls": iframe_urls,
        "detail": "PAHO dengue dashboard page and iframe URLs are mapped, but embedded Tableau/PHIP cells need a stable unauthenticated CSV/JSON endpoint before Ask Insects can claim country-level dashboard records.",
        "retrieved_at": retrieved_at,
    }


def _dashboard_locator_records(url: str, html: str, raw_path: Path, retrieved_at: str) -> list[EvidenceRecord]:
    iframe_urls = re.findall(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    title = _clean_text(_first(r"<title[^>]*>(.*?)</title>", html) or "PAHO dengue dashboard")
    iframes_text = ", ".join(iframe_urls) if iframe_urls else "no iframe URL found in saved page"
    records: list[EvidenceRecord] = []
    for index, iframe_url in enumerate(iframe_urls or [""], start=1):
        iframe_piece = _normalize_id(iframe_url or "page")
        record_id = (
            "public_health:surveillance:paho_dengue:"
            f"dashboard_locator:{hashlib.sha1(f'{url}:{index}:{iframe_url}'.encode('utf-8')).hexdigest()[:12]}"
        )
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane="public_health",
                source=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                title=f"PAHO dengue dashboard locator: {title}",
                text=(
                    f"Official PAHO dengue dashboard locator for Aedes-relevant public-health surveillance. "
                    f"Dashboard page: {url}. Embedded iframe URLs: {iframes_text}. "
                    "This record makes the official dashboard surface queryable, but it is not a country-week "
                    "PAHO/PLISA cell row because no stable unauthenticated CSV, JSON, or API endpoint has been proven."
                ),
                species="Aedes aegypti",
                url=url,
                media_url=iframe_url or None,
                provenance=Provenance(
                    source_id=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    locator=f"{raw_path.as_posix()}#dashboard-locator-{index}-{iframe_piece}",
                    retrieved_at=retrieved_at,
                    license="PAHO/WHO public health surveillance page; source page terms apply",
                    source_url=url,
                ),
                payload={
                    "organization": "PAHO/WHO",
                    "disease": "dengue",
                    "aedes_relevance": "Dengue dashboard surface relevant to Aedes aegypti vector public-health intelligence",
                    "aggregation_type": "dashboard_locator",
                    "dashboard_page_url": url,
                    "dashboard_title": title,
                    "iframe_url": iframe_url or None,
                    "iframe_urls": iframe_urls,
                    "raw_html_path": raw_path.as_posix(),
                    "machine_readable_cell_status": "not_proven",
                    "source_gap_reason": "paho_dashboard_data_not_yet_cell_queryable",
                },
            )
        )
    return records


def fetch_paho_dengue_surveillance_records(
    reports: list[dict[str, str]] | tuple[dict[str, str], ...] = DEFAULT_PAHO_DENGUE_REPORTS,
    *,
    raw_dir: Path,
    fetch_text=None,
    retrieved_at: str,
    dashboard_pages: list[str] | tuple[str, ...] = DEFAULT_PAHO_DENGUE_DASHBOARD_PAGES,
) -> PahoDengueSurveillanceResult:
    fetch = fetch_text or _default_fetch_text
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    report_count = 0
    dashboard_page_count = 0

    for report in reports:
        url = str(report.get("url") or "")
        if not url:
            gaps.append(
                {
                    "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "paho_dengue_report_url_missing",
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
                    "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "paho_dengue_report_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path = raw_dir / f"report_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}.html"
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        report_records = _regional_records(
            html=html,
            raw_path=raw_path,
            report_url=url,
            landing_url=report.get("landing_url"),
            retrieved_at=retrieved_at,
        )
        if not report_records:
            gaps.append(
                {
                    "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "paho_dengue_report_no_records_parsed",
                    "url": url,
                    "raw_html_path": raw_path.as_posix(),
                    "retrieved_at": retrieved_at,
                }
            )
        records.extend(report_records)
        report_count += 1

    for url in dashboard_pages:
        requested_urls.append(url)
        try:
            html = fetch(url)
        except Exception as exc:
            gaps.append(
                {
                    "source": PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
                    "lane": "public_health",
                    "reason": "paho_dengue_dashboard_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
            continue
        raw_path = raw_dir / f"dashboard_{_safe_filename(url)}_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]}.html"
        raw_path.write_text(html, encoding="utf-8")
        raw_artifacts.append(raw_path.as_posix())
        records.extend(_dashboard_locator_records(url, html, raw_path, retrieved_at))
        gaps.append(_dashboard_gap(url, html, raw_path, retrieved_at))
        dashboard_page_count += 1

    return PahoDengueSurveillanceResult(
        source_id=PAHO_DENGUE_SURVEILLANCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        report_count=report_count,
        dashboard_page_count=dashboard_page_count,
    )
