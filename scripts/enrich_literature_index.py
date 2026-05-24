#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from askinsects.index import SourceIndex
from askinsects.sources.literature import FullTextUnit, LITERATURE_SOURCE_ID, fulltext_units_for_record, normalize_doi


FetchJson = Callable[[str], dict[str, object]]
FetchBytes = Callable[[str], tuple[bytes, str]]
PdfToText = Callable[[Path], str]


@dataclass(frozen=True)
class EnrichmentConfig:
    artifact_dir: Path = Path("artifacts/aedes-literature-2020")
    email: str | None = None
    pubmed: bool = True
    unpaywall: bool = True
    fulltext: bool = True
    limit: int | None = None
    delay_seconds: float = 1.0
    ncbi_delay_seconds: float = 0.5
    pubmed_batch_size: int = 100
    http_timeout_seconds: float = 10.0
    pdf_timeout_seconds: float = 20.0
    max_fulltext_bytes: int = 60_000_000
    resume: bool = True
    record_id_shard_count: int = 1
    record_id_shard_index: int = 0


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_json_url(url: str, timeout: float = 10.0) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": "ask-insects/0.1"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"URL returned non-object JSON for {url}")
    return payload


def fetch_url_bytes(url: str, timeout: float = 10.0, max_bytes: int = 60_000_000) -> tuple[bytes, str]:
    with tempfile.NamedTemporaryFile() as body, tempfile.NamedTemporaryFile(mode="w+") as headers:
        result = subprocess.run(
            [
                "/usr/bin/curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                str(timeout),
                "--connect-timeout",
                str(min(8.0, timeout)),
                "--max-filesize",
                str(max_bytes),
                "--user-agent",
                "ask-insects/0.1",
                "--dump-header",
                headers.name,
                "--output",
                body.name,
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stderr:
            raise RuntimeError(result.stderr.strip())
        header_text = Path(headers.name).read_text(encoding="utf-8", errors="replace")
        content_types = re.findall(r"(?im)^content-type:\s*([^\r\n;]+)", header_text)
        return Path(body.name).read_bytes(), content_types[-1] if content_types else ""


def pdftotext(pdf_path: Path, timeout: float = 20.0) -> str:
    result = subprocess.run(
        ["/opt/homebrew/bin/pdftotext", "-layout", pdf_path.as_posix(), "-"],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    return result.stdout


def _row_in_shard(record_id: str, shard_count: int, shard_index: int) -> bool:
    if shard_count <= 1:
        return True
    digest = hashlib.sha256(record_id.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big")
    return value % shard_count == shard_index


def _load_rows(conn: sqlite3.Connection, config: EnrichmentConfig) -> list[sqlite3.Row]:
    query = """
        SELECT p.record_id, p.payload_json, p.provenance_json, r.species
        FROM record_payloads p
        LEFT JOIN records r ON r.record_id = p.record_id
        WHERE p.source = ? AND p.lane = 'literature'
        ORDER BY p.record_id
    """
    params: list[object] = [LITERATURE_SOURCE_ID]
    rows = [
        row
        for row in conn.execute(query, params)
        if _row_in_shard(row["record_id"], config.record_id_shard_count, config.record_id_shard_index)
    ]
    if config.limit is not None:
        return rows[: max(0, int(config.limit))]
    return rows


def _update_payload(conn: sqlite3.Connection, record_id: str, payload: dict[str, object]) -> None:
    conn.execute(
        "UPDATE record_payloads SET payload_json=? WHERE record_id=?",
        (json.dumps(payload, sort_keys=True), record_id),
    )
    conn.commit()


def _raw_work(payload: dict[str, object]) -> dict[str, object]:
    work = payload.get("raw_openalex_work")
    return work if isinstance(work, dict) else {}


def _extract_pmid(payload: dict[str, object]) -> str | None:
    ids = _raw_work(payload).get("ids")
    raw = ids.get("pmid") if isinstance(ids, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    match = re.search(r"(\d+)$", raw.strip())
    return match.group(1) if match else raw.strip()


def _extract_doi(payload: dict[str, object]) -> str | None:
    work = _raw_work(payload)
    doi = work.get("doi")
    if isinstance(doi, str):
        normalized = normalize_doi(doi)
        if normalized:
            return normalized
    ids = work.get("ids")
    raw = ids.get("doi") if isinstance(ids, dict) else None
    return normalize_doi(raw) if isinstance(raw, str) else None


def _openalex_pdf_url(payload: dict[str, object]) -> str | None:
    location = _raw_work(payload).get("best_oa_location")
    if not isinstance(location, dict):
        return None
    url = location.get("pdf_url")
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else None


def _gap(
    *,
    reason: str,
    record_id: str,
    species: object,
    retrieved_at: str,
    locator: str,
    external_id: object | None = None,
    error: object | None = None,
) -> dict[str, object]:
    gap: dict[str, object] = {
        "source": LITERATURE_SOURCE_ID,
        "lane": "literature",
        "reason": reason,
        "record_id": record_id,
        "species": species,
        "retrieved_at": retrieved_at,
        "locator": locator,
    }
    if external_id is not None:
        gap["external_id"] = external_id
    if error is not None:
        gap["error"] = str(error)
    return gap


def _load_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gap_key(gap: dict[str, object]) -> tuple[str, str, str, str, str]:
    return (
        str(gap.get("source", "")),
        str(gap.get("lane", "")),
        str(gap.get("reason", "")),
        str(gap.get("record_id", "")),
        str(gap.get("locator", "")),
    )


def _dedupe_gaps(gaps: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    for gap in gaps:
        deduped[_gap_key(gap)] = gap
    return list(deduped.values())


def _append_gaps(artifact_dir: Path, gaps: list[dict[str, object]]) -> None:
    gaps_path = artifact_dir / "gaps.json"
    existing = _load_json_list(gaps_path)
    if gaps:
        existing.extend(gaps)
    _write_json(gaps_path, _dedupe_gaps(existing))


def _pubmed_esummary_url(pmids: list[str], email: str) -> str:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "id": ",".join(pmids),
        "tool": "ask-insects",
        "email": email,
    }
    return f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urlencode(params)}"


def _pubmed_entries(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return {}
    uids = result.get("uids")
    if not isinstance(uids, list):
        return {}
    entries: dict[str, dict[str, object]] = {}
    for uid in uids:
        entry = result.get(str(uid))
        if isinstance(entry, dict):
            entries[str(uid)] = entry
    return entries


def enrich_pubmed(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    config: EnrichmentConfig,
    retrieved_at: str,
    fetch_json: FetchJson,
) -> tuple[dict[str, int], list[dict[str, object]]]:
    counts = {"enriched": 0, "skipped": 0, "missing_pmid": 0, "failed": 0}
    gaps: list[dict[str, object]] = []
    candidates: list[tuple[sqlite3.Row, dict[str, object], str]] = []

    for row in rows:
        payload = json.loads(row["payload_json"])
        if config.resume and isinstance(payload.get("pubmed"), dict):
            counts["skipped"] += 1
            continue
        pmid = _extract_pmid(payload)
        if not pmid:
            counts["missing_pmid"] += 1
            gaps.append(
                _gap(
                    reason="pubmed_missing_pmid",
                    record_id=row["record_id"],
                    species=row["species"],
                    retrieved_at=retrieved_at,
                    locator=f"record_payloads#{row['record_id']}",
                )
            )
            continue
        candidates.append((row, payload, pmid))

    batch_size = max(1, int(config.pubmed_batch_size))
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        if start > 0 and config.ncbi_delay_seconds > 0:
            time.sleep(config.ncbi_delay_seconds)
        pmids = [pmid for _, _, pmid in batch]
        url = _pubmed_esummary_url(pmids, config.email or "")
        try:
            entries = _pubmed_entries(fetch_json(url))
        except Exception as exc:
            for row, _, pmid in batch:
                counts["failed"] += 1
                gaps.append(
                    _gap(
                        reason="pubmed_fetch_failed",
                        record_id=row["record_id"],
                        species=row["species"],
                        retrieved_at=retrieved_at,
                        locator=url,
                        external_id=pmid,
                        error=exc,
                    )
                )
            continue
        for row, payload, pmid in batch:
            entry = entries.get(pmid)
            if not entry:
                counts["failed"] += 1
                gaps.append(
                    _gap(
                        reason="pubmed_fetch_failed",
                        record_id=row["record_id"],
                        species=row["species"],
                        retrieved_at=retrieved_at,
                        locator=url,
                        external_id=pmid,
                        error="PMID missing from ESummary result",
                    )
                )
                continue
            payload["pubmed"] = {"pmid": pmid, "match": entry, "retrieved_at": retrieved_at}
            _update_payload(conn, row["record_id"], payload)
            counts["enriched"] += 1

    return counts, gaps


def _unpaywall_url(doi: str, email: str) -> str:
    return f"https://api.unpaywall.org/v2/{quote(doi, safe='')}?{urlencode({'email': email})}"


def enrich_unpaywall(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    config: EnrichmentConfig,
    retrieved_at: str,
    fetch_json: FetchJson,
) -> tuple[dict[str, int], list[dict[str, object]]]:
    counts = {"queried": 0, "skipped": 0, "missing_doi": 0, "failed": 0}
    gaps: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        payload = json.loads(row["payload_json"])
        if config.resume and isinstance(payload.get("unpaywall"), dict):
            counts["skipped"] += 1
            continue
        doi = _extract_doi(payload)
        if not doi:
            counts["missing_doi"] += 1
            gaps.append(
                _gap(
                    reason="missing_doi",
                    record_id=row["record_id"],
                    species=row["species"],
                    retrieved_at=retrieved_at,
                    locator=f"record_payloads#{row['record_id']}",
                )
            )
            continue
        if index > 0 and config.delay_seconds > 0:
            time.sleep(config.delay_seconds)
        url = _unpaywall_url(doi, config.email or "")
        try:
            unpaywall = fetch_json(url)
        except Exception as exc:
            counts["failed"] += 1
            gaps.append(
                _gap(
                    reason="unpaywall_fetch_failed",
                    record_id=row["record_id"],
                    species=row["species"],
                    retrieved_at=retrieved_at,
                    locator=url,
                    external_id=doi,
                    error=exc,
                )
            )
            continue
        payload["unpaywall"] = unpaywall
        _update_payload(conn, row["record_id"], payload)
        counts["queried"] += 1
        if not _direct_fulltext_from_payload(payload):
            location = unpaywall.get("best_oa_location")
            landing = location.get("url_for_landing_page") if isinstance(location, dict) else None
            gaps.append(
                _gap(
                    reason="fulltext_landing_page_only" if isinstance(landing, str) and landing else "unpaywall_no_fulltext_url",
                    record_id=row["record_id"],
                    species=row["species"],
                    retrieved_at=retrieved_at,
                    locator=url,
                    external_id=landing if isinstance(landing, str) else doi,
                )
            )
    return counts, gaps


def _direct_fulltext_from_payload(payload: dict[str, object]) -> tuple[str, str | None] | None:
    unpaywall = payload.get("unpaywall")
    if isinstance(unpaywall, dict) and unpaywall.get("is_oa"):
        location = unpaywall.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("url_for_pdf") or location.get("url_for_xml")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                license_value = location.get("license")
                return url, str(license_value) if license_value else None
    fallback = _openalex_pdf_url(payload)
    if fallback:
        return fallback, "OpenAlex OA PDF URL"
    return None


def _fulltext_exists(conn: sqlite3.Connection, record_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM literature_fulltext_units WHERE record_id=? LIMIT 1", (record_id,)).fetchone()
    return row is not None


def _text_from_direct_url(url: str, fetch_bytes: FetchBytes, pdf_to_text: PdfToText, pdf_timeout_seconds: float) -> str:
    data, content_type = fetch_bytes(url)
    lowered = content_type.lower()
    if "pdf" in lowered or url.lower().split("?", 1)[0].endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temp:
            temp.write(data)
            temp.flush()
            if pdf_to_text is pdftotext:
                return pdftotext(Path(temp.name), timeout=pdf_timeout_seconds)
            return pdf_to_text(Path(temp.name))
    if any(marker in lowered for marker in ("text/plain", "text/html", "application/xml", "text/xml")):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"unsupported direct fulltext content-type: {content_type or 'unknown'}")


def enrich_fulltext(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    config: EnrichmentConfig,
    retrieved_at: str,
    fetch_bytes: FetchBytes,
    pdf_to_text: PdfToText,
) -> tuple[dict[str, int], list[dict[str, object]]]:
    counts = {"records": 0, "units": 0, "skipped": 0, "failed": 0}
    gaps: list[dict[str, object]] = []
    index = SourceIndex(config.artifact_dir / "source_index.sqlite")
    pending_units: list[FullTextUnit] = []

    def flush_units() -> None:
        if not pending_units:
            return
        conn.commit()
        index.upsert_fulltext_units(pending_units)
        pending_units.clear()

    for row_index, row in enumerate(rows):
        record_id = row["record_id"]
        if config.resume and _fulltext_exists(conn, record_id):
            counts["skipped"] += 1
            continue
        payload = json.loads(row["payload_json"])
        target = _direct_fulltext_from_payload(payload)
        if not target:
            continue
        if row_index > 0 and config.delay_seconds > 0:
            time.sleep(config.delay_seconds)
        url, license_value = target
        try:
            text = _text_from_direct_url(url, fetch_bytes, pdf_to_text, config.pdf_timeout_seconds)
            units = fulltext_units_for_record(record_id, text, url, license_value, retrieved_at)
        except Exception as exc:
            counts["failed"] += 1
            gaps.append(
                _gap(
                    reason="fulltext_fetch_failed",
                    record_id=record_id,
                    species=row["species"],
                    retrieved_at=retrieved_at,
                    locator=url,
                    external_id=url,
                    error=exc,
                )
            )
            continue
        if not units:
            counts["failed"] += 1
            gaps.append(
                _gap(
                    reason="fulltext_parse_failed",
                    record_id=record_id,
                    species=row["species"],
                    retrieved_at=retrieved_at,
                    locator=url,
                    external_id=url,
                )
            )
            continue
        pending_units.extend(units)
        counts["records"] += 1
        counts["units"] += len(units)
        if len(pending_units) >= 100:
            flush_units()
    flush_units()
    return counts, gaps


def _load_receipt(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _update_receipt(artifact_dir: Path, summary: dict[str, object]) -> None:
    path = artifact_dir / "literature_enrichment_receipt.json"
    existing = _load_receipt(path)
    runs = existing.get("runs")
    if not isinstance(runs, list):
        runs = []
    runs.append(summary)
    receipt = {
        "source": LITERATURE_SOURCE_ID,
        "latest": summary,
        "runs": runs[-20:],
    }
    _write_json(path, receipt)


def _count_direct_fulltext_candidates(payload_rows: list[sqlite3.Row]) -> int:
    count = 0
    for row in payload_rows:
        payload = json.loads(row["payload_json"])
        if _direct_fulltext_from_payload(payload):
            count += 1
    return count


def _reconcile_source_artifacts(conn: sqlite3.Connection, artifact_dir: Path, generated_at: str) -> dict[str, object]:
    gaps = _load_json_list(artifact_dir / "gaps.json")
    lane_rows = conn.execute("SELECT lane, count(*) AS n FROM records GROUP BY lane ORDER BY lane").fetchall()
    source_rows = conn.execute("SELECT source, count(*) AS n FROM records GROUP BY source ORDER BY source").fetchall()
    payload_rows = conn.execute(
        "SELECT record_id, payload_json FROM record_payloads WHERE source=? ORDER BY record_id",
        (LITERATURE_SOURCE_ID,),
    ).fetchall()
    literature_count = int(
        conn.execute("SELECT count(*) FROM records WHERE source=?", (LITERATURE_SOURCE_ID,)).fetchone()[0]
    )
    payload_count = len(payload_rows)
    pubmed_enriched = int(
        conn.execute(
            "SELECT count(*) FROM record_payloads WHERE source=? AND json_type(payload_json, '$.pubmed')='object'",
            (LITERATURE_SOURCE_ID,),
        ).fetchone()[0]
    )
    unpaywall_enriched = int(
        conn.execute(
            "SELECT count(*) FROM record_payloads WHERE source=? AND json_type(payload_json, '$.unpaywall')='object'",
            (LITERATURE_SOURCE_ID,),
        ).fetchone()[0]
    )
    fulltext_record_count = int(conn.execute("SELECT count(distinct record_id) FROM literature_fulltext_units").fetchone()[0])
    fulltext_unit_count = int(conn.execute("SELECT count(*) FROM literature_fulltext_units").fetchone()[0])
    fulltext_fts_count = int(conn.execute("SELECT count(*) FROM literature_fulltext_fts").fetchone()[0])
    direct_candidates = _count_direct_fulltext_candidates(payload_rows)
    sources = [row["source"] for row in source_rows]
    source_status = {
        "ok": True,
        "source_id": LITERATURE_SOURCE_ID,
        "sources": sources,
        "boundary": "Aedes aegypti literature since 2020 with fixture seed records retained when built with --fixtures",
        "generated_at": generated_at,
        "fully_parsed": True,
        "record_count": sum(int(row["n"]) for row in source_rows),
        "source_counts": {row["source"]: int(row["n"]) for row in source_rows},
        "lanes": {row["lane"]: int(row["n"]) for row in lane_rows},
        "gap_count": len(gaps),
        "literature": {
            "source": LITERATURE_SOURCE_ID,
            "record_count": literature_count,
            "payload_count": payload_count,
            "pubmed_enriched_count": pubmed_enriched,
            "unpaywall_enriched_count": unpaywall_enriched,
            "direct_fulltext_candidate_count": direct_candidates,
            "fulltext_record_count": fulltext_record_count,
            "fulltext_unit_count": fulltext_unit_count,
            "fulltext_fts_count": fulltext_fts_count,
        },
    }
    receipt_path = artifact_dir / "source_receipt.json"
    receipt = _load_receipt(receipt_path)
    receipt.update(
        {
            "artifact_dir": artifact_dir.as_posix(),
            "source_id": LITERATURE_SOURCE_ID,
            "sources": sources,
            "generated_at": generated_at,
            "record_count": source_status["record_count"],
            "source_counts": source_status["source_counts"],
            "lanes": source_status["lanes"],
            "gap_count": len(gaps),
        }
    )
    literature = receipt.get("literature")
    if not isinstance(literature, dict):
        literature = {}
    literature.update(source_status["literature"])
    literature["open_fulltext_count"] = fulltext_record_count
    literature["gap_count"] = len([gap for gap in gaps if gap.get("source") == LITERATURE_SOURCE_ID])
    literature["gaps_path"] = (artifact_dir / "gaps.json").as_posix()
    literature["payload_store"] = "record_payloads.payload_json"
    literature["fulltext_store"] = "literature_fulltext_units"
    receipt["literature"] = literature
    _write_json(artifact_dir / "source_status.json", source_status)
    _write_json(receipt_path, receipt)
    return dict(source_status["literature"])


def run_enrichment(
    config: EnrichmentConfig,
    *,
    fetch_json: FetchJson = fetch_json_url,
    fetch_bytes: FetchBytes = fetch_url_bytes,
    pdf_to_text: PdfToText = pdftotext,
) -> dict[str, object]:
    if (config.pubmed or config.unpaywall) and not config.email:
        raise ValueError("--email is required when PubMed or Unpaywall enrichment is enabled")
    started_at = utc_now()
    artifact_dir = Path(config.artifact_dir)
    db_path = artifact_dir / "source_index.sqlite"
    all_gaps: list[dict[str, object]] = []
    summary: dict[str, object] = {
        "ok": True,
        "source": LITERATURE_SOURCE_ID,
        "artifact_dir": artifact_dir.as_posix(),
        "started_at": started_at,
        "finished_at": None,
        "records_seen": 0,
        "pubmed": {"enriched": 0, "skipped": 0, "missing_pmid": 0, "failed": 0},
        "unpaywall": {"queried": 0, "skipped": 0, "missing_doi": 0, "failed": 0},
        "fulltext": {"records": 0, "units": 0, "skipped": 0, "failed": 0},
        "gaps_appended": 0,
    }

    def timed_fetch_json(url: str) -> dict[str, object]:
        if fetch_json is fetch_json_url:
            return fetch_json_url(url, timeout=config.http_timeout_seconds)
        return fetch_json(url)

    def timed_fetch_bytes(url: str) -> tuple[bytes, str]:
        if fetch_bytes is fetch_url_bytes:
            return fetch_url_bytes(url, timeout=config.http_timeout_seconds, max_bytes=config.max_fulltext_bytes)
        return fetch_bytes(url)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = _load_rows(conn, config)
        summary["records_seen"] = len(rows)
        if config.pubmed:
            counts, gaps = enrich_pubmed(conn, rows, config, started_at, timed_fetch_json)
            summary["pubmed"] = counts
            all_gaps.extend(gaps)
        if config.unpaywall:
            rows = _load_rows(conn, config)
            counts, gaps = enrich_unpaywall(conn, rows, config, started_at, timed_fetch_json)
            summary["unpaywall"] = counts
            all_gaps.extend(gaps)
        if config.fulltext:
            rows = _load_rows(conn, config)
            counts, gaps = enrich_fulltext(conn, rows, config, started_at, timed_fetch_bytes, pdf_to_text)
            summary["fulltext"] = counts
            all_gaps.extend(gaps)

    _append_gaps(artifact_dir, all_gaps)
    summary["gaps_appended"] = len(all_gaps)
    summary["finished_at"] = utc_now()
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        summary["artifact_totals"] = _reconcile_source_artifacts(conn, artifact_dir, str(summary["finished_at"]))
    _update_receipt(artifact_dir, summary)
    return summary


def parse_args(argv: list[str] | None = None) -> EnrichmentConfig:
    parser = argparse.ArgumentParser(description="Enrich the Ask Insects Aedes literature index in place.")
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/aedes-literature-2020"))
    parser.add_argument("--email")
    parser.add_argument("--pubmed", action="store_true")
    parser.add_argument("--unpaywall", action="store_true")
    parser.add_argument("--fulltext", action="store_true")
    parser.add_argument("--pubmed-only", action="store_true")
    parser.add_argument("--unpaywall-only", action="store_true")
    parser.add_argument("--fulltext-only", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--ncbi-delay-seconds", type=float, default=0.5)
    parser.add_argument("--pubmed-batch-size", type=int, default=100)
    parser.add_argument("--http-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--pdf-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--max-fulltext-bytes", type=int, default=60_000_000)
    parser.add_argument("--resume", dest="resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--record-id-shard-count", type=int, default=1)
    parser.add_argument("--record-id-shard-index", type=int, default=0)
    args = parser.parse_args(argv)

    explicit = args.pubmed or args.unpaywall or args.fulltext
    pubmed = unpaywall = fulltext = not explicit
    if explicit:
        pubmed = args.pubmed
        unpaywall = args.unpaywall
        fulltext = args.fulltext
    if args.pubmed_only:
        pubmed, unpaywall, fulltext = True, False, False
    if args.unpaywall_only:
        pubmed, unpaywall, fulltext = False, True, False
    if args.fulltext_only:
        pubmed, unpaywall, fulltext = False, False, True

    shard_count = max(1, args.record_id_shard_count)
    if args.record_id_shard_index < 0 or args.record_id_shard_index >= shard_count:
        parser.error("--record-id-shard-index must be between 0 and --record-id-shard-count - 1")

    return EnrichmentConfig(
        artifact_dir=args.artifact_dir,
        email=args.email,
        pubmed=pubmed,
        unpaywall=unpaywall,
        fulltext=fulltext,
        limit=args.limit,
        delay_seconds=args.delay_seconds,
        ncbi_delay_seconds=max(0.34, args.ncbi_delay_seconds),
        pubmed_batch_size=args.pubmed_batch_size,
        http_timeout_seconds=max(1.0, args.http_timeout_seconds),
        pdf_timeout_seconds=max(1.0, args.pdf_timeout_seconds),
        max_fulltext_bytes=max(1, args.max_fulltext_bytes),
        resume=args.resume,
        record_id_shard_count=shard_count,
        record_id_shard_index=args.record_id_shard_index,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        summary = run_enrichment(parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
