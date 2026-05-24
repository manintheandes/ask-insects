from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from askinsects.records import EvidenceRecord, Provenance


RESISTANCE_MARKER_SOURCE_ID = "aedes_resistance_markers"


@dataclass(frozen=True)
class MarkerSpec:
    marker_id: str
    aliases: tuple[str, ...]
    marker_class: str
    gene_or_family: str
    marker_type: str
    specific: bool = True


MARKER_SPECS: tuple[MarkerSpec, ...] = (
    MarkerSpec("kdr", ("kdr", "knockdown resistance"), "target_site", "VGSC", "resistance phenotype", False),
    MarkerSpec(
        "vgsc",
        ("VGSC", "Vgsc", "voltage-gated sodium channel", "voltage-sensitive sodium channel", "voltage sensitive sodium channel"),
        "target_site",
        "VGSC",
        "gene family",
        False,
    ),
    MarkerSpec("V410L", ("V410L",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("G923V", ("G923V",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("S989P", ("S989P", "Ser989Pro"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("I1011M", ("I1011M", "Ile1011Met"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("I1011V", ("I1011V", "Ile1011Val"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("V1016G", ("V1016G", "Val1016Gly"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("V1016I", ("V1016I", "Val1016Ile"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("A1007G", ("A1007G",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("L982W", ("L982W",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("F1269C", ("F1269C",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("F1534C", ("F1534C", "Phe1534Cys"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("F1534L", ("F1534L", "Phe1534Leu"), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("L199F", ("L199F",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("A434T", ("A434T",), "target_site", "VGSC", "amino acid substitution"),
    MarkerSpec("CYP9J", ("CYP9J",), "metabolic", "cytochrome P450 CYP9J family", "gene family", False),
    MarkerSpec("CYP9J10", ("CYP9J10",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP9J24", ("CYP9J24",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP9J26", ("CYP9J26",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP9J27", ("CYP9J27",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP9J28", ("CYP9J28",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP9J32", ("CYP9J32",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP6BB2", ("CYP6BB2",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("CYP6N12", ("CYP6N12",), "metabolic", "cytochrome P450", "gene"),
    MarkerSpec("cytochrome_p450", ("cytochrome P450", "P450 monooxygenase", "monooxygenase"), "metabolic", "cytochrome P450", "enzyme family", False),
    MarkerSpec("GSTE2", ("GSTE2",), "metabolic", "glutathione S-transferase", "gene"),
    MarkerSpec("GSTE7", ("GSTE7",), "metabolic", "glutathione S-transferase", "gene"),
    MarkerSpec("glutathione_s_transferase", ("glutathione S-transferase", "glutathione transferase", "GST"), "metabolic", "GST", "enzyme family", False),
    MarkerSpec("CCEae3a", ("CCEae3a",), "metabolic", "carboxylesterase", "gene"),
    MarkerSpec("carboxylesterase", ("carboxylesterase", "esterase"), "metabolic", "carboxylesterase", "enzyme family", False),
    MarkerSpec("abc_transporter", ("ABC transporter", "ATP-binding cassette transporter"), "metabolic", "ABC transporter", "transporter family", False),
)

RESISTANCE_CONTEXT_TERMS = (
    "insecticide resistance",
    "pyrethroid resistance",
    "resistant",
    "resistance",
    "susceptibility",
    "bioassay",
    "knockdown",
    "kdr",
    "mutation",
    "mutations",
    "detoxification",
    "metabolic resistance",
    "overexpression",
    "upregulated",
    "permethrin",
    "deltamethrin",
    "lambda-cyhalothrin",
    "cyfluthrin",
    "cypermethrin",
    "DDT",
    "temephos",
    "malathion",
    "bendiocarb",
)

INSECTICIDE_TERMS = (
    "permethrin",
    "deltamethrin",
    "lambda-cyhalothrin",
    "cyfluthrin",
    "cypermethrin",
    "DDT",
    "temephos",
    "malathion",
    "bendiocarb",
    "pyrethroid",
    "organophosphate",
    "carbamate",
)


@dataclass(frozen=True)
class MarkerCandidate:
    source_record_id: str
    source_title: str
    species: str | None
    paper_url: str | None
    paper_source: str
    source_provenance: dict[str, object]
    extraction_source: str
    unit_id: str | None
    unit_index: int | None
    unit_url: str | None
    unit_license: str | None
    unit_provenance: dict[str, object] | None
    text: str


@dataclass(frozen=True)
class ResistanceMarkerResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    candidate_count: int
    source_record_count: int
    fulltext_unit_count: int
    marker_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "unknown"


@lru_cache(maxsize=None)
def _pattern_for_alias(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias).replace(r"\ ", r"[\s-]+")
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", re.I)


@lru_cache(maxsize=None)
def _pattern_for_term(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s-]+")
    return re.compile(r"\b" + escaped + r"\b", re.I)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    matches = []
    for term in terms:
        if _pattern_for_term(term).search(text):
            matches.append(term)
    return matches


def _matched_aliases(text: str, spec: MarkerSpec) -> list[str]:
    return [alias for alias in spec.aliases if _pattern_for_alias(alias).search(text)]


def _snippet(text: str, terms: Iterable[str], limit: int = 720) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    lower = compact.lower()
    positions = [lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0]
    start = max(0, min(positions) - 180) if positions else 0
    snippet = compact[start : start + limit]
    if start > 0:
        snippet = "..." + snippet
    if start + limit < len(compact):
        snippet += "..."
    return snippet


def _candidate_rows(conn: sqlite3.Connection) -> tuple[list[MarkerCandidate], int, int]:
    literature_rows = conn.execute(
        """
        SELECT record_id, title, text, species, url, source, provenance_json
        FROM records
        WHERE lane='literature'
        ORDER BY record_id
        """
    ).fetchall()
    literature_by_id = {str(row["record_id"]): row for row in literature_rows}
    marker_query = _fts_or_query(alias for spec in MARKER_SPECS for alias in spec.aliases)
    try:
        fulltext_total = int(conn.execute("SELECT count(*) FROM literature_fulltext_units").fetchone()[0])
        fulltext_rows = conn.execute(
            """
            SELECT DISTINCT u.unit_id, u.record_id, u.unit_index, u.text, u.url, u.license, u.provenance_json
            FROM literature_fulltext_fts f
            JOIN literature_fulltext_units u ON u.unit_id = f.unit_id
            WHERE literature_fulltext_fts MATCH ?
            ORDER BY u.record_id, u.unit_index
            """,
            (marker_query,),
        ).fetchall()
    except sqlite3.OperationalError:
        fulltext_total = 0
        fulltext_rows = []

    candidates: list[MarkerCandidate] = []
    for unit in fulltext_rows:
        paper = literature_by_id.get(str(unit["record_id"]))
        if paper is None:
            continue
        candidates.append(
            MarkerCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                paper_source=str(paper["source"]),
                source_provenance=json.loads(str(paper["provenance_json"])),
                extraction_source="literature_fulltext_units",
                unit_id=str(unit["unit_id"]),
                unit_index=int(unit["unit_index"]),
                unit_url=unit["url"],
                unit_license=unit["license"],
                unit_provenance=json.loads(str(unit["provenance_json"])),
                text=str(unit["text"]),
            )
        )

    for paper in literature_rows:
        combined_literature_text = "\n".join([str(paper["title"]), str(paper["text"])])
        if not any(_matched_aliases(combined_literature_text, spec) for spec in MARKER_SPECS):
            continue
        candidates.append(
            MarkerCandidate(
                source_record_id=str(paper["record_id"]),
                source_title=str(paper["title"]),
                species=paper["species"],
                paper_url=paper["url"],
                paper_source=str(paper["source"]),
                source_provenance=json.loads(str(paper["provenance_json"])),
                extraction_source="literature_record",
                unit_id=None,
                unit_index=None,
                unit_url=None,
                unit_license=None,
                unit_provenance=None,
                text="\n".join([str(paper["title"]), str(paper["text"])]),
            )
        )

    return candidates, len(literature_rows), fulltext_total


def _fts_term(term: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", term)
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    return '"' + " ".join(tokens) + '"'


def _fts_or_query(terms: Iterable[str]) -> str:
    parts = [_fts_term(term) for term in terms]
    parts = [part for part in parts if part]
    return " OR ".join(dict.fromkeys(parts))


def _generic_marker_has_strong_context(spec: MarkerSpec, context_hits: list[str], insecticide_hits: list[str]) -> bool:
    if spec.specific:
        return bool(context_hits)
    if spec.marker_class == "target_site":
        return bool({"kdr", "knockdown", "mutation", "mutations", "insecticide resistance", "pyrethroid resistance"} & set(context_hits))
    return bool(insecticide_hits) and bool(
        {
            "insecticide resistance",
            "pyrethroid resistance",
            "resistance",
            "resistant",
            "detoxification",
            "metabolic resistance",
            "overexpression",
            "upregulated",
        }
        & set(context_hits)
    )


def _record_for_marker(
    candidate: MarkerCandidate,
    spec: MarkerSpec,
    aliases: list[str],
    context_hits: list[str],
    insecticide_hits: list[str],
    *,
    retrieved_at: str,
) -> EvidenceRecord:
    combined_text = "\n".join([candidate.source_title, candidate.text])
    snippet = _snippet(combined_text, list(dict.fromkeys(aliases + context_hits + insecticide_hits)))
    unit_part = candidate.unit_id or "literature-record"
    digest = hashlib.sha1(f"{candidate.source_record_id}|{unit_part}|{spec.marker_id}".encode("utf-8")).hexdigest()[:12]
    locator_parts = [f"records#{candidate.source_record_id}"]
    if candidate.unit_id:
        locator_parts.append(f"literature_fulltext_units#{candidate.unit_id}")
    source_url = candidate.unit_url or candidate.paper_url
    title = f"Aedes aegypti resistance marker: {spec.marker_id}"
    text = (
        f"Deterministic marker extraction for Aedes aegypti insecticide resistance. "
        f"Marker: {spec.marker_id}. Class: {spec.marker_class}. Gene or family: {spec.gene_or_family}. "
        f"Marker type: {spec.marker_type}. Matched aliases: {', '.join(aliases)}. "
        f"Resistance context: {', '.join(context_hits[:12])}. "
        f"Insecticide terms: {', '.join(insecticide_hits[:10]) if insecticide_hits else 'not detected'}. "
        f"Snippet: {snippet}"
    )
    return EvidenceRecord(
        record_id=f"resistance_marker:{_normalize_id(spec.marker_id)}:{_normalize_id(candidate.source_record_id)}:{digest}",
        lane="resistance",
        source=RESISTANCE_MARKER_SOURCE_ID,
        title=title,
        text=text,
        species=candidate.species or "Aedes aegypti",
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=RESISTANCE_MARKER_SOURCE_ID,
            locator=";".join(locator_parts),
            retrieved_at=retrieved_at,
            license=candidate.unit_license or str(candidate.source_provenance.get("license") or "source literature metadata and legal full text where available"),
            source_url=source_url,
        ),
        payload={
            "source_record_id": candidate.source_record_id,
            "source_record_source": candidate.paper_source,
            "source_title": candidate.source_title,
            "extraction_source": candidate.extraction_source,
            "unit_id": candidate.unit_id,
            "unit_index": candidate.unit_index,
            "marker_id": spec.marker_id,
            "matched_aliases": aliases,
            "marker_class": spec.marker_class,
            "gene_or_family": spec.gene_or_family,
            "marker_type": spec.marker_type,
            "context_terms": context_hits,
            "insecticide_terms": insecticide_hits,
            "snippet": snippet,
        },
    )


def build_resistance_marker_records(artifact_dir: Path, *, retrieved_at: str | None = None) -> ResistanceMarkerResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    retrieved = retrieved_at or utc_now()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        candidates, literature_count, fulltext_count = _candidate_rows(conn)

    records: list[EvidenceRecord] = []
    marker_counts: dict[str, int] = {}
    seen_keys: set[tuple[str, str, str | None]] = set()
    for candidate in candidates:
        combined_text = "\n".join([candidate.source_title, candidate.text])
        context_hits = _matched_terms(combined_text, RESISTANCE_CONTEXT_TERMS)
        insecticide_hits = _matched_terms(combined_text, INSECTICIDE_TERMS)
        if not context_hits:
            continue
        for spec in MARKER_SPECS:
            aliases = _matched_aliases(combined_text, spec)
            if not aliases:
                continue
            if not _generic_marker_has_strong_context(spec, context_hits, insecticide_hits):
                continue
            key = (candidate.source_record_id, spec.marker_id, candidate.unit_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            records.append(
                _record_for_marker(
                    candidate,
                    spec,
                    aliases,
                    context_hits,
                    insecticide_hits,
                    retrieved_at=retrieved,
                )
            )
            marker_counts[spec.marker_id] = marker_counts.get(spec.marker_id, 0) + 1

    gaps: list[dict[str, object]] = []
    if not records:
        gaps.append(
            {
                "source": RESISTANCE_MARKER_SOURCE_ID,
                "lane": "resistance",
                "reason": "no_resistance_marker_candidates_detected",
                "literature_record_count": literature_count,
                "fulltext_unit_count": fulltext_count,
                "retrieved_at": retrieved,
            }
        )

    return ResistanceMarkerResult(
        source_id=RESISTANCE_MARKER_SOURCE_ID,
        records=records,
        gaps=gaps,
        candidate_count=len(records),
        source_record_count=literature_count,
        fulltext_unit_count=fulltext_count,
        marker_counts=dict(sorted(marker_counts.items())),
    )
