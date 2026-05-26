from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from io import BytesIO, TextIOWrapper
from pathlib import Path
import hashlib
import re
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from ..records import EvidenceRecord, Provenance


OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID = "aedes_opendatasus_dengue_surveillance"
USER_AGENT = "AskInsects/0.1 source-plane"
DEFAULT_OPENDATASUS_DENGUE_YEARS: tuple[int, ...] = tuple(range(2007, 2027))
OPENDATASUS_DENGUE_PORTAL_URL = "https://dadosabertos.saude.gov.br/dataset/arboviroses-dengue"
OPENDATASUS_DENGUE_DICTIONARY_URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/DIC_DADOS_NET---Dengue.pdf"
OPENDATASUS_LICENSE = "Brazil Ministry of Health OpenDataSUS public open-data files; source portal terms apply"

UF_NAMES = {
    "11": "Rondonia",
    "12": "Acre",
    "13": "Amazonas",
    "14": "Roraima",
    "15": "Para",
    "16": "Amapa",
    "17": "Tocantins",
    "21": "Maranhao",
    "22": "Piaui",
    "23": "Ceara",
    "24": "Rio Grande do Norte",
    "25": "Paraiba",
    "26": "Pernambuco",
    "27": "Alagoas",
    "28": "Sergipe",
    "29": "Bahia",
    "31": "Minas Gerais",
    "32": "Espirito Santo",
    "33": "Rio de Janeiro",
    "35": "Sao Paulo",
    "41": "Parana",
    "42": "Santa Catarina",
    "43": "Rio Grande do Sul",
    "50": "Mato Grosso do Sul",
    "51": "Mato Grosso",
    "52": "Goias",
    "53": "Distrito Federal",
}

CLASSI_FIN_LABELS = {
    "5": "discarded",
    "10": "dengue",
    "11": "dengue_with_warning_signs",
    "12": "severe_dengue",
    "13": "chikungunya",
    "8": "inconclusive",
}


@dataclass(frozen=True)
class OpenDataSusDengueFileSpec:
    year: int
    url: str


@dataclass(frozen=True)
class OpenDataSusDengueSurveillanceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    file_count: int
    source_file_record_count: int
    country_year_record_count: int
    state_year_record_count: int
    country_week_record_count: int
    state_week_record_count: int
    row_count: int
    years: list[int]


def default_opendatasus_dengue_file_specs(years: tuple[int, ...] | list[int] | None = None) -> list[OpenDataSusDengueFileSpec]:
    selected = tuple(years or DEFAULT_OPENDATASUS_DENGUE_YEARS)
    return [
        OpenDataSusDengueFileSpec(
            year=year,
            url=f"https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR{str(year)[-2:]}.csv.zip",
        )
        for year in selected
    ]


def _default_fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=180) as response:
        return response.read()


def _safe(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_").lower() or "unknown"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _int_value(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text or not re.fullmatch(r"\d+", text):
        return None
    return int(text)


def _week_value(row: dict[str, str]) -> str:
    for field in ("SEM_NOT", "SEM_PRI"):
        value = (row.get(field) or "").strip()
        if re.fullmatch(r"\d{6}", value):
            return value
    return "unknown"


def _year_value(row: dict[str, str], fallback: int) -> int:
    value = _int_value(row.get("NU_ANO"))
    if value and 1900 <= value <= 2100:
        return value
    for date_field in ("DT_NOTIFIC", "DT_SIN_PRI"):
        raw = (row.get(date_field) or "").strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return int(raw[:4])
    return fallback


def _uf_code(row: dict[str, str], kind: str) -> str:
    if kind == "residence":
        return (row.get("SG_UF") or row.get("SG_UF_NOT") or "unknown").strip() or "unknown"
    return (row.get("SG_UF_NOT") or row.get("SG_UF") or "unknown").strip() or "unknown"


def _state_name(code: str) -> str:
    return UF_NAMES.get(code, f"UF {code}")


def _update_stats(stats: dict[str, object], row: dict[str, str]) -> None:
    stats["notifications"] = int(stats.get("notifications", 0)) + 1
    evolution = (row.get("EVOLUCAO") or "").strip()
    classification = (row.get("CLASSI_FIN") or "").strip()
    hospitalization = (row.get("HOSPITALIZ") or "").strip()
    sex = (row.get("CS_SEXO") or "").strip() or "unknown"
    criterion = (row.get("CRITERIO") or "").strip() or "unknown"
    if evolution == "2":
        stats["deaths_by_disease"] = int(stats.get("deaths_by_disease", 0)) + 1
    if evolution == "3":
        stats["deaths_other_causes"] = int(stats.get("deaths_other_causes", 0)) + 1
    if classification == "12":
        stats["severe_dengue"] = int(stats.get("severe_dengue", 0)) + 1
    if classification == "11":
        stats["dengue_with_warning_signs"] = int(stats.get("dengue_with_warning_signs", 0)) + 1
    if classification == "10":
        stats["dengue_final_classification"] = int(stats.get("dengue_final_classification", 0)) + 1
    if hospitalization == "1":
        stats["hospitalized"] = int(stats.get("hospitalized", 0)) + 1
    stats.setdefault("classification_counts", Counter())
    stats.setdefault("sex_counts", Counter())
    stats.setdefault("criterion_counts", Counter())
    assert isinstance(stats["classification_counts"], Counter)
    assert isinstance(stats["sex_counts"], Counter)
    assert isinstance(stats["criterion_counts"], Counter)
    stats["classification_counts"][classification or "unknown"] += 1
    stats["sex_counts"][sex] += 1
    stats["criterion_counts"][criterion] += 1


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: int(value) for key, value in sorted(counter.items()) if key}


def _classification_summary(counter: Counter[str]) -> str:
    pieces = []
    for code, count in sorted(counter.items()):
        label = CLASSI_FIN_LABELS.get(code, f"classification_{code or 'unknown'}")
        pieces.append(f"{label}: {count}")
    return "; ".join(pieces) if pieces else "none reported"


def _raw_locator(raw_path: Path, suffix: str) -> str:
    return f"{raw_path.as_posix()}#{suffix}"


def _base_payload(
    *,
    aggregation_type: str,
    year: int,
    raw_path: Path,
    url: str,
    row_count: int,
    stats: dict[str, object],
) -> dict[str, object]:
    return {
        "aggregation_type": aggregation_type,
        "country": "Brazil",
        "year": year,
        "disease": "dengue",
        "aedes_relevance": "Dengue public-health surveillance relevant to Aedes aegypti vector intelligence",
        "notifications": int(stats.get("notifications", 0)),
        "deaths_by_disease": int(stats.get("deaths_by_disease", 0)),
        "deaths_other_causes": int(stats.get("deaths_other_causes", 0)),
        "severe_dengue": int(stats.get("severe_dengue", 0)),
        "dengue_with_warning_signs": int(stats.get("dengue_with_warning_signs", 0)),
        "dengue_final_classification": int(stats.get("dengue_final_classification", 0)),
        "hospitalized": int(stats.get("hospitalized", 0)),
        "classification_counts": _counter_payload(stats.get("classification_counts", Counter())),
        "sex_counts": _counter_payload(stats.get("sex_counts", Counter())),
        "criterion_counts": _counter_payload(stats.get("criterion_counts", Counter())),
        "input_line_count_for_year": row_count,
        "source_file_url": url,
        "raw_zip_path": raw_path.as_posix(),
        "source_portal_url": OPENDATASUS_DENGUE_PORTAL_URL,
    }


def _record(
    *,
    record_id: str,
    title: str,
    text: str,
    raw_path: Path,
    locator_suffix: str,
    source_url: str,
    retrieved_at: str,
    payload: dict[str, object],
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="public_health",
        source=OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
        title=title,
        text=text,
        species="Aedes aegypti",
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
            locator=_raw_locator(raw_path, locator_suffix),
            retrieved_at=retrieved_at,
            license=OPENDATASUS_LICENSE,
            source_url=source_url,
        ),
        payload=payload,
    )


def _source_file_record(*, spec: OpenDataSusDengueFileSpec, raw_path: Path, sha256: str, byte_size: int, row_count: int, retrieved_at: str) -> EvidenceRecord:
    payload = {
        "aggregation_type": "opendatasus_dengue_source_file",
        "country": "Brazil",
        "year": spec.year,
        "disease": "dengue",
        "source_portal_url": OPENDATASUS_DENGUE_PORTAL_URL,
        "data_dictionary_url": OPENDATASUS_DENGUE_DICTIONARY_URL,
        "source_file_url": spec.url,
        "raw_zip_path": raw_path.as_posix(),
        "sha256": sha256,
        "byte_size": byte_size,
        "csv_row_count": row_count,
    }
    return _record(
        record_id=f"public_health:surveillance:opendatasus_dengue:file:brazil:{spec.year}",
        title=f"OpenDataSUS Brazil dengue source file, {spec.year}",
        text=(
            f"Official Brazil Ministry of Health OpenDataSUS SINAN dengue CSV ZIP for {spec.year}. "
            f"The file contains {row_count} notification rows. SHA-256: {sha256}. "
            "Ask Insects indexes aggregate public-health records from this file for Aedes aegypti intelligence."
        ),
        raw_path=raw_path,
        locator_suffix="source-file",
        source_url=spec.url,
        retrieved_at=retrieved_at,
        payload=payload,
    )


def _country_year_record(*, year: int, stats: dict[str, object], raw_path: Path, source_url: str, retrieved_at: str, row_count: int) -> EvidenceRecord:
    payload = _base_payload(
        aggregation_type="opendatasus_dengue_country_year",
        year=year,
        raw_path=raw_path,
        url=source_url,
        row_count=row_count,
        stats=stats,
    )
    classifications = _classification_summary(stats.get("classification_counts", Counter()))
    return _record(
        record_id=f"public_health:surveillance:opendatasus_dengue:country:brazil:{year}",
        title=f"OpenDataSUS Brazil dengue surveillance summary, {year}",
        text=(
            f"Official Brazil OpenDataSUS SINAN dengue aggregate for {year}. "
            f"Notifications: {payload['notifications']}. Deaths coded as death by disease in EVOLUCAO=2: {payload['deaths_by_disease']}. "
            f"Severe dengue classifications: {payload['severe_dengue']}. Hospitalized notifications: {payload['hospitalized']}. "
            f"Final-classification counts: {classifications}. "
            "This is human dengue surveillance evidence relevant to Aedes aegypti vector intelligence, not mosquito occurrence evidence."
        ),
        raw_path=raw_path,
        locator_suffix=f"aggregate/country/Brazil/year/{year}",
        source_url=source_url,
        retrieved_at=retrieved_at,
        payload=payload,
    )


def _state_year_record(*, year: int, state_code: str, state_kind: str, stats: dict[str, object], raw_path: Path, source_url: str, retrieved_at: str, row_count: int) -> EvidenceRecord:
    state = _state_name(state_code)
    payload = _base_payload(
        aggregation_type=f"opendatasus_dengue_{state_kind}_state_year",
        year=year,
        raw_path=raw_path,
        url=source_url,
        row_count=row_count,
        stats=stats,
    )
    payload[f"{state_kind}_state_code"] = state_code
    payload[f"{state_kind}_state"] = state
    return _record(
        record_id=f"public_health:surveillance:opendatasus_dengue:{state_kind}_state:{_safe(state_code)}:{year}",
        title=f"OpenDataSUS Brazil dengue surveillance for {state} ({state_kind} state), {year}",
        text=(
            f"Official Brazil OpenDataSUS SINAN dengue aggregate for {state} by {state_kind} state in {year}. "
            f"Notifications: {payload['notifications']}. Deaths coded as death by disease in EVOLUCAO=2: {payload['deaths_by_disease']}. "
            f"Severe dengue classifications: {payload['severe_dengue']}. Hospitalized notifications: {payload['hospitalized']}."
        ),
        raw_path=raw_path,
        locator_suffix=f"aggregate/{state_kind}_state/{state_code}/year/{year}",
        source_url=source_url,
        retrieved_at=retrieved_at,
        payload=payload,
    )


def _week_record(
    *,
    year: int,
    week: str,
    stats: dict[str, object],
    raw_path: Path,
    source_url: str,
    retrieved_at: str,
    row_count: int,
    state_code: str | None = None,
) -> EvidenceRecord:
    is_state = state_code is not None
    state = _state_name(state_code) if state_code else None
    payload = _base_payload(
        aggregation_type="opendatasus_dengue_residence_state_week" if is_state else "opendatasus_dengue_country_week",
        year=year,
        raw_path=raw_path,
        url=source_url,
        row_count=row_count,
        stats=stats,
    )
    payload["epidemiological_week"] = week
    if is_state:
        payload["residence_state_code"] = state_code
        payload["residence_state"] = state
    label = f"{state}, Brazil" if state else "Brazil"
    record_id = (
        f"public_health:surveillance:opendatasus_dengue:residence_state_week:{_safe(state_code)}:{week}"
        if is_state
        else f"public_health:surveillance:opendatasus_dengue:country_week:brazil:{week}"
    )
    return _record(
        record_id=record_id,
        title=f"OpenDataSUS dengue notifications for {label}, epidemiological week {week}",
        text=(
            f"Official Brazil OpenDataSUS SINAN dengue aggregate for {label}, epidemiological week {week}. "
            f"Notifications: {payload['notifications']}. Deaths coded as death by disease in EVOLUCAO=2: {payload['deaths_by_disease']}. "
            f"Severe dengue classifications: {payload['severe_dengue']}."
        ),
        raw_path=raw_path,
        locator_suffix=(
            f"aggregate/residence_state/{state_code}/week/{week}" if is_state else f"aggregate/country/Brazil/week/{week}"
        ),
        source_url=source_url,
        retrieved_at=retrieved_at,
        payload=payload,
    )


def _gap(*, reason: str, spec: OpenDataSusDengueFileSpec | None, retrieved_at: str, detail: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
        "reason": reason,
        "retrieved_at": retrieved_at,
        "detail": detail,
        "source_portal_url": OPENDATASUS_DENGUE_PORTAL_URL,
    }
    if spec is not None:
        payload.update({"year": spec.year, "source_url": spec.url})
    return payload


def _parse_file(
    *,
    spec: OpenDataSusDengueFileSpec,
    raw_path: Path,
    retrieved_at: str,
    records: list[EvidenceRecord],
    gaps: list[dict[str, object]],
) -> int:
    try:
        with ZipFile(raw_path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                gaps.append(_gap(reason="opendatasus_dengue_zip_without_csv", spec=spec, retrieved_at=retrieved_at, detail="ZIP contained no CSV member"))
                return 0
            with archive.open(csv_names[0]) as stream:
                reader = csv.DictReader(TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
                country_year: dict[int, dict[str, object]] = defaultdict(dict)
                residence_state_year: dict[tuple[int, str], dict[str, object]] = defaultdict(dict)
                notification_state_year: dict[tuple[int, str], dict[str, object]] = defaultdict(dict)
                country_week: dict[tuple[int, str], dict[str, object]] = defaultdict(dict)
                state_week: dict[tuple[int, str, str], dict[str, object]] = defaultdict(dict)
                row_count = 0
                for row in reader:
                    row_count += 1
                    year = _year_value(row, spec.year)
                    week = _week_value(row)
                    residence_uf = _uf_code(row, "residence")
                    notification_uf = _uf_code(row, "notification")
                    _update_stats(country_year[year], row)
                    _update_stats(residence_state_year[(year, residence_uf)], row)
                    _update_stats(notification_state_year[(year, notification_uf)], row)
                    _update_stats(country_week[(year, week)], row)
                    _update_stats(state_week[(year, residence_uf, week)], row)
    except (BadZipFile, OSError, UnicodeError, csv.Error) as exc:
        gaps.append(_gap(reason="opendatasus_dengue_csv_parse_failed", spec=spec, retrieved_at=retrieved_at, detail=str(exc)))
        return 0

    raw_bytes = raw_path.read_bytes()
    records.append(
        _source_file_record(
            spec=spec,
            raw_path=raw_path,
            sha256=_sha(raw_bytes),
            byte_size=len(raw_bytes),
            row_count=row_count,
            retrieved_at=retrieved_at,
        )
    )
    for year, stats in sorted(country_year.items()):
        records.append(_country_year_record(year=year, stats=stats, raw_path=raw_path, source_url=spec.url, retrieved_at=retrieved_at, row_count=row_count))
    for (year, state_code), stats in sorted(residence_state_year.items()):
        records.append(_state_year_record(year=year, state_code=state_code, state_kind="residence", stats=stats, raw_path=raw_path, source_url=spec.url, retrieved_at=retrieved_at, row_count=row_count))
    for (year, state_code), stats in sorted(notification_state_year.items()):
        records.append(_state_year_record(year=year, state_code=state_code, state_kind="notification", stats=stats, raw_path=raw_path, source_url=spec.url, retrieved_at=retrieved_at, row_count=row_count))
    for (year, week), stats in sorted(country_week.items()):
        records.append(_week_record(year=year, week=week, stats=stats, raw_path=raw_path, source_url=spec.url, retrieved_at=retrieved_at, row_count=row_count))
    for (year, state_code, week), stats in sorted(state_week.items()):
        records.append(_week_record(year=year, week=week, state_code=state_code, stats=stats, raw_path=raw_path, source_url=spec.url, retrieved_at=retrieved_at, row_count=row_count))
    return row_count


def fetch_opendatasus_dengue_surveillance_records(
    file_specs: list[OpenDataSusDengueFileSpec] | None = None,
    *,
    raw_dir: Path,
    fetch_bytes=None,
    retrieved_at: str,
) -> OpenDataSusDengueSurveillanceResult:
    specs = file_specs or default_opendatasus_dengue_file_specs()
    fetch = fetch_bytes or _default_fetch_bytes
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    total_rows = 0
    successful_years: list[int] = []

    for spec in specs:
        requested_urls.append(spec.url)
        raw_path = raw_dir / f"DENGBR{str(spec.year)[-2:]}.csv.zip"
        try:
            blob = fetch(spec.url)
            raw_path.write_bytes(blob)
            raw_artifacts.append(raw_path.as_posix())
        except Exception as exc:
            gaps.append(_gap(reason="opendatasus_dengue_file_fetch_failed", spec=spec, retrieved_at=retrieved_at, detail=str(exc)))
            continue
        rows = _parse_file(spec=spec, raw_path=raw_path, retrieved_at=retrieved_at, records=records, gaps=gaps)
        if rows:
            total_rows += rows
            successful_years.append(spec.year)

    deduped: dict[str, EvidenceRecord] = {}
    duplicate_count = 0
    for record in records:
        if record.record_id in deduped:
            duplicate_count += 1
        deduped[record.record_id] = record
    if duplicate_count:
        gaps.append(
            _gap(
                reason="opendatasus_dengue_duplicate_aggregate_ids_collapsed",
                spec=None,
                retrieved_at=retrieved_at,
                detail=f"Collapsed {duplicate_count} duplicate aggregate record IDs across annual files; the latest generated record for each aggregate ID was kept.",
            )
        )
    records = list(deduped.values())

    return OpenDataSusDengueSurveillanceResult(
        source_id=OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        file_count=len(successful_years),
        source_file_record_count=sum(1 for record in records if ":file:" in record.record_id),
        country_year_record_count=sum(1 for record in records if ":country:brazil:" in record.record_id),
        state_year_record_count=sum(1 for record in records if "_state:" in record.record_id),
        country_week_record_count=sum(1 for record in records if ":country_week:" in record.record_id),
        state_week_record_count=sum(1 for record in records if ":residence_state_week:" in record.record_id),
        row_count=total_rows,
        years=successful_years,
    )
