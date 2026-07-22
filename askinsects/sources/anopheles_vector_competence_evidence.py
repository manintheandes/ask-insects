from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from askinsects.records import EvidenceRecord, Provenance


ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID = "anopheles_vector_competence_evidence"

ANOPHELES_SPECIES_ALIASES: dict[str, tuple[str, ...]] = {
    "Anopheles gambiae": ("Anopheles gambiae", "An. gambiae"),
    "Anopheles coluzzii": ("Anopheles coluzzii", "An. coluzzii"),
    "Anopheles funestus": ("Anopheles funestus", "An. funestus"),
    "Anopheles stephensi": ("Anopheles stephensi", "An. stephensi"),
    "Anopheles arabiensis": ("Anopheles arabiensis", "An. arabiensis"),
    "Anopheles dirus": ("Anopheles dirus", "An. dirus"),
    "Anopheles minimus": ("Anopheles minimus", "An. minimus"),
    "Anopheles sinensis": ("Anopheles sinensis", "An. sinensis"),
    "Anopheles albimanus": ("Anopheles albimanus", "An. albimanus"),
    "Anopheles darlingi": ("Anopheles darlingi", "An. darlingi"),
    "Anopheles culicifacies": ("Anopheles culicifacies", "An. culicifacies"),
    "Anopheles aquasalis": ("Anopheles aquasalis", "An. aquasalis"),
    "Anopheles melas": ("Anopheles melas", "An. melas"),
    "Anopheles merus": ("Anopheles merus", "An. merus"),
    "Anopheles nili": ("Anopheles nili", "An. nili"),
    "Anopheles moucheti": ("Anopheles moucheti", "An. moucheti"),
    "Anopheles atroparvus": ("Anopheles atroparvus", "An. atroparvus"),
    "Anopheles labranchiae": ("Anopheles labranchiae", "An. labranchiae"),
    "Anopheles sacharovi": ("Anopheles sacharovi", "An. sacharovi"),
    "Anopheles freeborni": ("Anopheles freeborni", "An. freeborni"),
}

PLASMODIUM_ALIASES: dict[str, tuple[str, ...]] = {
    "Plasmodium falciparum": ("Plasmodium falciparum", "P. falciparum"),
    "Plasmodium vivax": ("Plasmodium vivax", "P. vivax"),
    "Plasmodium malariae": ("Plasmodium malariae", "P. malariae"),
    "Plasmodium ovale": ("Plasmodium ovale", "P. ovale"),
    "Plasmodium knowlesi": ("Plasmodium knowlesi", "P. knowlesi"),
    "Plasmodium berghei": ("Plasmodium berghei", "P. berghei"),
    "Plasmodium yoelii": ("Plasmodium yoelii", "P. yoelii"),
    "Plasmodium cynomolgi": ("Plasmodium cynomolgi", "P. cynomolgi"),
}

ENDPOINT_ALIASES: dict[str, tuple[str, ...]] = {
    "sporozoite_rate": ("sporozoite rate", "sporozoite infection rate", "sporozoite prevalence"),
    "sporozoite_detection": ("sporozoite", "sporozoites"),
    "oocyst_rate": ("oocyst rate", "oocyst infection rate", "oocyst prevalence"),
    "oocyst_intensity": ("oocyst intensity", "oocyst count", "oocyst load", "oocysts"),
    "infection_rate": ("infection rate", "infection prevalence", "infectivity rate"),
    "parasite_burden": ("parasite prevalence", "parasite load", "parasite intensity"),
    "transmission_rate": ("transmission rate", "transmission efficiency"),
    "entomological_inoculation_rate": ("entomological inoculation rate", "EIR"),
}

EXPERIMENTAL_TERMS = (
    "membrane feed", "membrane-feeding", "membrane feeding", "artificial blood",
    "infected blood", "infectious blood", "gametocyte", "experimentally infected",
    "experimental infection", "laboratory infection", "mosquito feeding assay",
    "direct feeding assay", "smfa", "dmfa", "colony mosquitoes", "laboratory-reared",
)
FIELD_TERMS = (
    "field collected", "field-collected", "collected", "collection", "light trap",
    "trap", "survey", "surveillance", "household", "village", "study site", "wild-caught",
    "indoor", "outdoor", "human landing catch", "pyrethrum spray catch", "psc",
)
MODEL_TERMS = (
    "modelled", "modeled", "modelling", "modeling", "simulation", "simulated",
    "predicted", "projected", "scenario", "in silico",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_NUMERIC_RESULT_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:infectious bites?|bites?|oocysts?|sporozoites?)\b|"
    r"\bn\s*=\s*\d+\b|\b\d+\s*(?:/|of)\s*\d+\b|\b\d+(?:\.\d+)?\s*(?:per|fold)\b)",
    re.IGNORECASE,
)
_SHARED_PERCENT_SERIES_RE = re.compile(
    r"\b(\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)+(?:\s*,?\s*and\s*\d+(?:\.\d+)?)?)\s*%",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AnophelesVectorCompetenceResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    source_record_count: int
    candidate_sentence_count: int
    excluded_model_sentence_count: int


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _abstract_text(text: str) -> str:
    match = re.search(r"(?:^|\n)Abstract:\s*(.*?)(?=\n(?:DOI|Venue|Publication date|Authors|Inclusion paths):|\Z)", text, re.DOTALL)
    if match:
        value = match.group(1).strip()
        return "" if value.lower() == "missing" else value
    return text.strip()


def _matches_by_canonical(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    matches: list[str] = []
    for canonical, terms in aliases.items():
        if any(re.search(r"(?<![A-Za-z])" + re.escape(term) + r"\b", text, re.IGNORECASE) for term in terms):
            matches.append(canonical)
    return matches


def _endpoint_matches(text: str) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for endpoint, terms in ENDPOINT_ALIASES.items():
        if any((term.lower() == "eir" and re.search(r"\bEIR\b", text)) or term.lower() in lowered for term in terms):
            matches.append(endpoint)
    if (
        "infection_rate" not in matches
        and re.search(r"\binfected\b", text, re.IGNORECASE)
        and re.search(r"\b(?:\d+\s*(?:/|of)\s*\d+|\d+(?:\.\d+)?\s*%)\b", text, re.IGNORECASE)
    ):
        matches.append("infection_rate")
    return matches


def _numeric_results(sentence: str) -> list[str]:
    values: list[str] = []
    for series in _SHARED_PERCENT_SERIES_RE.finditer(sentence):
        values.extend(re.findall(r"\d+(?:\.\d+)?", series.group(1)))
    values.extend(match.group(0).strip() for match in _NUMERIC_RESULT_RE.finditer(sentence))
    return list(dict.fromkeys(values))


def _evidence_class(context: str) -> str:
    lowered = context.lower()
    if any(term in lowered for term in EXPERIMENTAL_TERMS):
        return "experimental_vector_competence_result"
    if any(term in lowered for term in FIELD_TERMS):
        return "field_surveillance_result"
    return "abstract_reported_result"


def extract_anopheles_vector_competence_records(
    source_records: list[EvidenceRecord],
    *,
    retrieved_at: str | None = None,
) -> AnophelesVectorCompetenceResult:
    retrieved = retrieved_at or _utc_now()
    records: list[EvidenceRecord] = []
    candidate_sentence_count = 0
    excluded_model_sentence_count = 0

    for source_record in source_records:
        if source_record.source != "anopheles_literature_openalex" or not source_record.record_id.startswith("anopheles_openalex:"):
            continue
        abstract = _abstract_text(source_record.text)
        if not abstract:
            continue
        sentences = _SENTENCE_SPLIT_RE.split(re.sub(r"\s+", " ", abstract).strip())
        for sentence_index, sentence in enumerate(sentences):
            species = _matches_by_canonical(sentence, ANOPHELES_SPECIES_ALIASES)
            endpoints = _endpoint_matches(sentence)
            numeric_results = _numeric_results(sentence)
            if not species or not endpoints or not numeric_results:
                continue
            candidate_sentence_count += 1
            context_sentences = sentences[max(0, sentence_index - 1) : min(len(sentences), sentence_index + 2)]
            context = " ".join(context_sentences)
            if any(term in context.lower() for term in MODEL_TERMS):
                excluded_model_sentence_count += 1
                continue
            pathogens = _matches_by_canonical(context, PLASMODIUM_ALIASES)
            evidence_class = _evidence_class(context)
            digest = hashlib.sha256(
                f"{source_record.record_id}|{sentence_index}|{sentence}".encode("utf-8")
            ).hexdigest()[:16]
            source_locator = source_record.provenance.locator
            locator = f"{source_locator}/abstract/sentence/{sentence_index + 1}"
            records.append(EvidenceRecord(
                record_id=f"anopheles_vector_competence:abstract_result:{digest}",
                lane="vector_competence",
                source=ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
                title=f"Anopheles abstract-reported {', '.join(endpoints)} result",
                text=(
                    f"Evidence class: {evidence_class}. Exact abstract sentence: {sentence} "
                    "This is an abstract-level extraction and has not been validated against a full-text table."
                ),
                species=species[0] if len(species) == 1 else "Anopheles",
                url=source_record.url,
                media_url=None,
                provenance=Provenance(
                    source_id=ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
                    locator=locator,
                    retrieved_at=retrieved,
                    license=source_record.provenance.license,
                    source_url=source_record.provenance.source_url or source_record.url,
                ),
                payload={
                    "record_type": "anopheles_vector_competence_abstract_result",
                    "evidence_class": evidence_class,
                    "validation_status": "abstract_extraction_not_fulltext_validated",
                    "source_record_id": source_record.record_id,
                    "source_record_source": source_record.source,
                    "source_title": source_record.title,
                    "source_provenance": source_record.provenance.to_dict(),
                    "abstract_sentence_index": sentence_index + 1,
                    "exact_result_sentence": sentence,
                    "context_sentences": context_sentences,
                    "species_mentions": species,
                    "pathogen_mentions": pathogens,
                    "endpoint_mentions": endpoints,
                    "numeric_results": numeric_results,
                },
            ))

    gaps: list[dict[str, object]] = []
    if not records:
        gaps.append({
            "source": ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
            "lane": "vector_competence",
            "reason": "no_qualifying_anopheles_abstract_result_sentences",
            "source_record_count": len(source_records),
            "candidate_sentence_count": candidate_sentence_count,
            "excluded_model_sentence_count": excluded_model_sentence_count,
            "retrieved_at": retrieved,
        })
    return AnophelesVectorCompetenceResult(
        source_id=ANOPHELES_VECTOR_COMPETENCE_SOURCE_ID,
        records=records,
        gaps=gaps,
        source_record_count=len(source_records),
        candidate_sentence_count=candidate_sentence_count,
        excluded_model_sentence_count=excluded_model_sentence_count,
    )


def build_anopheles_vector_competence_records(
    artifact_dir: Path,
    *,
    retrieved_at: str | None = None,
) -> AnophelesVectorCompetenceResult:
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"missing source index: {db_path}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT record_id, lane, source, title, text, species, url, media_url, provenance_json
            FROM records
            WHERE source = 'anopheles_literature_openalex'
              AND record_id LIKE 'anopheles_openalex:%'
            ORDER BY record_id
            """
        ).fetchall()
    source_records = [EvidenceRecord.from_row(dict(row)) for row in rows]
    return extract_anopheles_vector_competence_records(source_records, retrieved_at=retrieved_at)
