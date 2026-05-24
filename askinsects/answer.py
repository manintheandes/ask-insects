from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex
from .planner import QueryPlan, plan_question
from .records import EvidenceRecord
from .sources.occurrence_ecology import OCCURRENCE_ECOLOGY_SOURCE_ID
from .sources.resistance_markers import MARKER_SPECS, RESISTANCE_MARKER_SOURCE_ID


LITERATURE_QUERY_STOPWORDS = {
    "and",
    "about",
    "article",
    "articles",
    "discuss",
    "does",
    "from",
    "in",
    "literature",
    "paper",
    "papers",
    "research",
    "review",
    "reviews",
    "since",
    "studies",
    "study",
    "the",
    "what",
    "which",
    "with",
}

RESISTANCE_MARKER_QUERY_TERMS = {
    alias.lower()
    for spec in MARKER_SPECS
    for alias in spec.aliases
}
RESISTANCE_MARKER_QUERY_TERMS.update({"kdr", "vgsc", "vssc", "metabolic resistance", "resistance marker", "resistance markers"})


def record_to_evidence(record: EvidenceRecord) -> dict[str, object]:
    return {
        "record_id": record.record_id,
        "lane": record.lane,
        "source": record.source,
        "title": record.title,
        "text": record.text,
        "species": record.species,
        "url": record.url,
        "media_url": record.media_url,
        "provenance": record.provenance.to_dict(),
    }


def source_gap(plan: QueryPlan, reason: str) -> dict[str, object]:
    lane = plan.lanes[0] if plan.lanes else "unknown"
    return {
        "ok": False,
        "answer_shape": plan.answer_shape,
        "answer": f"I do not see enough indexed Ask Insects evidence for this question yet. {reason}",
        "evidence": [],
        "source_gap": {
            "lane": lane,
            "reason": reason,
            "checked_lanes": list(plan.lanes),
        },
    }


def _answer_text(plan: QueryPlan, records: list[EvidenceRecord]) -> str:
    if plan.answer_shape == "identity":
        return f"From the Ask Insects index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "evidence":
        return f"I found {len(records)} indexed Ask Insects evidence record(s) matching the question."
    if plan.answer_shape == "action":
        return f"The Ask Insects index supports this next step: {records[0].text}"
    if plan.answer_shape == "literature":
        return f"From the Ask Insects literature index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "media":
        return f"I found {len(records)} indexed Ask Insects media record(s)."
    if plan.answer_shape == "genomics":
        return f"From the local mosquito genomics index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "neurobiology":
        return f"From the local mosquito neurobiology index, {records[0].title}: {records[0].text}"
    if plan.answer_shape in {"behavior", "vector_competence", "resistance", "ecology", "public_health"}:
        label = plan.answer_shape.replace("_", " ")
        return f"From the Ask Insects {label} index, {records[0].title}: {records[0].text}"
    return f"I found {len(records)} indexed Ask Insects record(s)."


def _search_queries(question: str) -> list[str]:
    q = question.lower()
    if any(term in q for term in ("biosample", "biosamples", "sample", "samples", "strain", "strains", "isolate", "isolates")) or (
        "sra" in q and "reanalysis" not in q and "raw read" not in q and "runinfo" not in q
    ):
        generic_terms = {
            "aedes",
            "aegypti",
            "biosample",
            "biosamples",
            "from",
            "show",
            "sample",
            "samples",
            "strain",
            "strains",
            "isolate",
            "isolates",
            "sra",
            "the",
            "what",
            "which",
        }
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower() not in generic_terms
        ]
        queries = []
        if salient:
            queries.append(f"Aedes aegypti {' '.join(salient)}")
            queries.append(" ".join(salient))
        queries.extend(["NCBI BioSample Aedes aegypti", "BioSample", "sample strain isolate SRA"])
        species = _requested_species(question)
        if species:
            queries.append(species)
        return list(dict.fromkeys(queries))
    if any(term in q for term in ("vectorbase", "veupathdb", "aael", "go annotation", "go term", "gene ontology")):
        generic_terms = {
            "aedes",
            "aegypti",
            "annotation",
            "for",
            "gene",
            "genes",
            "genomics",
            "go",
            "show",
            "term",
            "terms",
            "the",
            "vectorbase",
            "veupathdb",
            "what",
            "which",
        }
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower() not in generic_terms
        ]
        queries = []
        aael_terms = [token for token in salient if token.upper().startswith("AAEL")]
        if aael_terms:
            queries.extend(aael_terms)
            queries.extend(f"VectorBase {term}" for term in aael_terms)
        if salient:
            queries.append(" ".join(salient))
        queries.extend(["VectorBase Aedes aegypti", "Aedes aegypti VectorBase", question])
        return list(dict.fromkeys(queries))
    if "mosquito alert" in q:
        return ["Mosquito Alert Aedes aegypti", "Mosquito Alert", "citizen-science observation", question]
    if "gbif" in q and any(term in q for term in ("observation", "observations", "occurrence", "occurrences", "record", "records")):
        generic_terms = {
            "aedes",
            "aegypti",
            "gbif",
            "in",
            "occurrence",
            "occurrences",
            "observation",
            "observations",
            "record",
            "records",
            "show",
            "the",
        }
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower() not in generic_terms
        ]
        queries = []
        if salient:
            queries.append(f"Aedes aegypti {' '.join(salient)} GBIF occurrence")
            queries.append(f"{' '.join(salient)} GBIF")
        queries.extend(["Aedes aegypti GBIF occurrence", "GBIF occurrence", question])
        return list(dict.fromkeys(queries))
    if "dryad" in q:
        return ["Dryad Aedes aegypti behavior video", "Dryad video archive", "Dryad behavior dataset", question]
    if any(term in q for term in ("assay", "infection rate", "dissemination", "transmission", "dose", "midgut", "saliva", "salivary", "extrinsic incubation")) and any(
        term in q for term in ("dengue", "zika", "chikungunya", "yellow fever", "west nile", "mayaro", "vector competence")
    ):
        pathogen_terms = _named_pathogen_terms(question)
        pathogen_query = " ".join(pathogen_terms)
        if pathogen_query:
            return [
                f"{pathogen_query} vector competence assay infection dissemination transmission dose temperature",
                f"{pathogen_query} dose transmission infection dissemination",
                "vector competence assay Aedes aegypti",
                question,
            ]
        return ["vector competence assay Aedes aegypti", "infection dissemination transmission dose temperature", question]
    if any(term in q for term in ("paho", "plisa", "surveillance", "outbreak", "incidence", "epidemic", "case fatality", "cases", "deaths", "public health")):
        if any(term in q for term in ("paho", "plisa", "surveillance", "dengue", "cases", "deaths")):
            return [
                "PAHO dengue surveillance week summary",
                "PAHO dengue surveillance Aedes aegypti",
                "PAHO dengue surveillance",
                "dengue surveillance public health",
                question,
            ]
        return ["public health Aedes aegypti", "surveillance outbreak incidence", question]
    if "pathogen" in q or any(term in q for term in ("dengue", "zika", "chikungunya", "yellow fever")):
        return ["NCBI Taxonomy pathogen", "pathogen taxonomy Aedes aegypti", question]
    if "coi-5p" in q or re.search(r"\bcoi\b", q):
        return ["COI-5P", "Marker COI", question]
    if "bold" in q and ("barcode" in q or "barcodes" in q):
        return ["BOLD barcode", question]
    marker_terms = _resistance_marker_terms(question)
    if marker_terms:
        marker_query_terms = [
            term
            for term in marker_terms
            if term not in {"resistance marker", "resistance markers", "metabolic resistance"}
        ] or marker_terms
        marker_query = " ".join(marker_query_terms)
        return [
            marker_query,
            f"{marker_query} resistance",
            f"{marker_query} Aedes aegypti",
            "kdr metabolic resistance marker",
            "IR Mapper Aedes insecticide resistance",
            question,
        ]
    if (
        not any(
            term in q
            for term in (
                "assay",
                "cdc",
                "dengue",
                "guidance",
                "insecticide resistance",
                "kdr",
                "pathogen",
                "paho",
                "pyrethroid resistance",
                "recommendation",
                "recommendations",
                "susceptibility",
                "vector competence",
                "who",
                "yellow fever",
                "zika",
            )
        )
        and any(
        term in q
        for term in (
            "ecology",
            "range",
            "distribution",
            "where",
            "country",
            "countries",
            "seasonality",
            "seasonal",
            "month",
            "monthly",
            "habitat",
            "observed",
            "occurrence",
            "occurrences",
        )
        )
    ):
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower()
            not in {
                "aedes",
                "aegypti",
                "country",
                "countries",
                "does",
                "ecology",
                "evidence",
                "exists",
                "for",
                "by",
                "in",
                "is",
                "month",
                "monthly",
                "mosquito",
                "mosquitoes",
                "occurrence",
                "occurrences",
                "range",
                "seasonality",
                "seasonal",
                "show",
                "the",
                "what",
                "where",
            }
        ]
        queries = []
        if salient:
            queries.append(f"Aedes aegypti occurrence ecology {' '.join(salient)}")
            queries.append(" ".join(salient))
        queries.extend(["Aedes aegypti occurrence ecology", "range distribution seasonality", question])
        return list(dict.fromkeys(queries))
    if any(
        term in q
        for term in (
            "cdc",
            "guidance",
            "insecticide resistance",
            "paho",
            "recommendation",
            "recommendations",
            "pyrethroid resistance",
            "kdr",
            "knockdown resistance",
            "susceptibility",
            "bioassay",
            "resistance mutation",
            "who",
        )
    ):
        if any(term in q for term in ("insecticide resistance", "pyrethroid resistance", "kdr", "knockdown resistance", "susceptibility", "bioassay", "resistance mutation")):
            return ["IR Mapper Aedes insecticide resistance", "insecticide resistance", "resistance", question]
        if any(term in q for term in ("cdc", "guidance", "paho", "recommendation", "recommendations", "who")):
            return [
                "Official public-health guidance Aedes aegypti vector control",
                "Aedes aegypti vector control guidance",
                "vector control",
                question,
            ]
    if "catmaid" in q and ("skeleton" in q or "bulk" in q or "export" in q or "download" in q):
        return ["CATMAID Aedes skeleton export manifest", "skeleton manifest bulk download", "CATMAID skeleton IDs", question]
    if "catmaid" in q or "em dataset" in q or ("public" in q and "connectome" in q):
        return ["CATMAID project accessible", "Public CATMAID project", "CATMAID Aedes project", "CATMAID EM dataset", "aedes_public", question]
    if "connectome" in q:
        return ["whole brain connectome source gap", "connectome", question]
    if "h5ad" in q or "anndata" in q:
        return ["H5AD", "Mosquito Cell Atlas H5AD", question]
    if "sra" in q and ("reanalysis" in q or "workflow" in q or "align" in q or "alignment" in q):
        return ["raw SRA reanalysis workflow", "reanalysis workflow", "fasterq-dump", question]
    if "sra" in q or "raw read" in q or "runinfo" in q:
        return ["SRA SRP290992", "SRA raw read", "SRR12972760", question]
    if "voxel" in q or "mha" in q or "mhd" in q or "volume" in q:
        return ["DimSize", "brain volume", question]
    queries = [question]
    species = _requested_species(question)
    added_domain_phrase = False
    for phrase in (
        "brain atlas",
        "female brain",
        "reference brain",
        "segmentation files",
        "single-nucleus",
        "single nucleus",
        "h5ad",
        "anndata",
        "sra",
        "raw reads",
        "runinfo",
        "mha",
        "mhd",
        "voxel",
        "volume",
        "catmaid",
        "em dataset",
        "cell atlas",
        "mosquito cell atlas",
        "antennal lobe",
        "olfactory sensory neurons",
        "olfactory sensory neuron",
        "odorant receptor",
        "gustatory receptor",
        "ionotropic receptor",
        "cytochrome p450",
        "sodium channel",
        "insecticide resistance",
        "pyrethroid resistance",
        "knockdown resistance",
        "resistance",
        "vector competence",
        "transmission competence",
        "competence",
        "host seeking",
        "host-seeking",
        "behavior",
        "blood feeding",
        "oviposition",
        "larval habitat",
        "breeding site",
        "ecology",
        "public health",
        "surveillance",
        "vector control",
        "outbreak",
        "video",
        "videos",
        "orco",
    ):
        if phrase in q:
            queries.append(phrase)
            added_domain_phrase = True
    if species and not added_domain_phrase:
        queries.append(species)
    if not added_domain_phrase and "host seeking" in question.lower():
        queries.append("host seeking")
    for term in ("Brazil", "mosquito"):
        if term.lower() in question.lower():
            queries.append(term)
    return list(dict.fromkeys(queries))


def _literature_search_queries(question: str) -> list[str]:
    species = _requested_species(question)
    topical_tokens = _literature_topical_tokens(question, species)
    queries = [question]
    queries.extend(
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", question)
        if token.lower() in topical_tokens
    )
    queries.extend(_search_queries(question))
    return list(dict.fromkeys(queries))


def _asks_for_still_images(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in ("image", "images", "photo", "photos", "picture", "pictures"))


def _requested_species(question: str) -> str | None:
    species_match = re.search(r"\b(Aedes|Culex|Anopheles)\s+[a-z]+\b", question, flags=re.IGNORECASE)
    if not species_match:
        return None
    return species_match.group(0)


def _literature_topical_tokens(question: str, species: str | None) -> set[str]:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", question)}
    if species:
        tokens -= {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", species)}
    tokens -= LITERATURE_QUERY_STOPWORDS
    tokens -= {"mosquito", "mosquitoes"}
    return {token for token in tokens if not token.isdigit()}


def _fulltext_literature_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    for search_query in _literature_search_queries(question):
        query_records = index.search_literature_fulltext(search_query, limit=limit)
        for record in query_records:
            if record.record_id in seen_record_ids:
                continue
            records.append(record)
            seen_record_ids.add(record.record_id)
        if query_records:
            break
    return records


def _record_matches_any_token(record: EvidenceRecord, tokens: set[str]) -> bool:
    haystack = f"{record.title}\n{record.text}".lower()
    return any(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)


def _prioritize_genomics_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if any(term in q for term in ("vectorbase", "veupathdb", "aael", "go annotation", "go term", "gene ontology")):
        aael_terms = [token.lower() for token in re.findall(r"AAEL[A-Za-z0-9-]+", question, flags=re.IGNORECASE)]
        if aael_terms:
            exact_records = [
                record
                for record in records
                if any(term in f"{record.record_id}\n{record.title}\n{record.text}".lower() for term in aael_terms)
            ]
            if exact_records:
                records = exact_records
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "vectorbase_aedes_genomics" else 1,
                0 if record.lane in {"genes", "proteins", "transcripts", "genome_features"} else 1,
            ),
        )
    if any(term in q for term in ("biosample", "biosamples", "sample", "samples", "strain", "strains", "isolate", "isolates")) or (
        "sra" in q and "reanalysis" not in q and "raw read" not in q and "runinfo" not in q
    ):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "ncbi_biosamples" else 1,
                0 if record.lane == "biosamples" else 1,
            ),
        )
    if not any(term in q for term in ("barcode", "barcodes", "bold", "coi", "coi-5p")):
        return records

    def score(record: EvidenceRecord) -> tuple[int, int, int]:
        haystack = f"{record.title}\n{record.text}".lower()
        return (
            0 if record.lane == "dna_barcodes" else 1,
            0 if any(term in haystack for term in ("coi-5p", "marker: coi", "marker:coi", " coi ")) else 1,
            0 if record.source == "bold_api" else 1,
        )

    return sorted(records, key=score)


def _resistance_marker_terms(question: str) -> list[str]:
    lower = question.lower()
    matched = []
    for term in sorted(RESISTANCE_MARKER_QUERY_TERMS, key=len, reverse=True):
        if term and term in lower:
            matched.append(term)
    return list(dict.fromkeys(matched))


def _prioritize_resistance_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    wants_marker = bool(_resistance_marker_terms(question))

    def score(record: EvidenceRecord) -> tuple[int, int, int]:
        marker_rank = 0 if wants_marker and record.source == RESISTANCE_MARKER_SOURCE_ID else 1
        irmapper_rank = 0 if not wants_marker and record.source == "irmapper_aedes" else 1
        return (
            marker_rank,
            irmapper_rank,
            0 if record.lane == "resistance" else 1,
        )

    return sorted(records, key=score)


def _prioritize_public_health_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(term in q for term in ("cdc", "guidance", "paho", "plisa", "surveillance", "recommendation", "recommendations", "who")):
        return records

    def score(record: EvidenceRecord) -> tuple[int, int, int]:
        paho_rank = 0 if any(term in q for term in ("paho", "plisa", "surveillance")) and record.source == "aedes_paho_dengue_surveillance" else 1
        guidance_rank = 0 if record.source == "aedes_public_health_guidance" else 1
        if record.source == "aedes_paho_dengue_surveillance" and any(term in q for term in ("paho", "plisa", "surveillance")):
            if "regional_week_summary" in record.record_id:
                record_rank = 0
            elif "regional_year_to_date_summary" in record.record_id:
                record_rank = 1
            elif "subregion" in record.record_id:
                record_rank = 2
            elif "serotypes" in record.record_id:
                record_rank = 3
            else:
                record_rank = 4
        else:
            record_rank = 0
        return (
            paho_rank,
            guidance_rank,
            record_rank if record.lane == "public_health" else 9,
        )

    return sorted(records, key=score)


def _prioritize_ecology_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(
        term in q
        for term in (
            "ecology",
            "range",
            "distribution",
            "where",
            "country",
            "countries",
            "seasonality",
            "seasonal",
            "month",
            "monthly",
            "habitat",
            "occurrence",
            "observed",
        )
    ):
        return records

    def score(record: EvidenceRecord) -> tuple[int, int]:
        return (
            0 if record.source == OCCURRENCE_ECOLOGY_SOURCE_ID else 1,
            0 if record.lane == "ecology" else 1,
        )

    return sorted(records, key=score)


def _named_pathogen_terms(question: str) -> list[str]:
    q = question.lower()
    terms = []
    for term in ("dengue", "zika", "chikungunya", "yellow fever", "west nile", "mayaro"):
        if term in q:
            terms.append(term)
    return terms


def _prioritize_named_source_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if "pathogen" in q or any(term in q for term in ("dengue", "zika", "chikungunya", "yellow fever")):
        pathogen_terms = _named_pathogen_terms(question)
        wants_taxonomy = "taxonomy" in q
        wants_assay = any(
            term in q
            for term in (
                "assay",
                "infection rate",
                "dissemination",
                "transmission",
                "dose",
                "temperature",
                "midgut",
                "saliva",
                "salivary",
                "extrinsic incubation",
            )
        )

        assay_terms = [
            term
            for term in (
                "infection",
                "dissemination",
                "transmission",
                "dose",
                "temperature",
                "midgut",
                "saliva",
                "salivary",
                "extrinsic incubation",
            )
            if term in q
        ]

        def score_pathogen(record: EvidenceRecord) -> tuple[int, int, int, int]:
            haystack = f"{record.title}\n{record.text}".lower()
            if wants_taxonomy:
                preferred_source = "aedes_pathogen_taxonomy"
            elif wants_assay:
                preferred_source = "aedes_vector_competence_assays"
            else:
                preferred_source = "aedes_vector_competence_assays" if record.source == "aedes_vector_competence_assays" else "aedes_pathogen_taxonomy"
            missing_assay_terms = sum(1 for term in assay_terms if term not in haystack)
            return (
                0 if record.source == preferred_source else 1,
                0 if record.lane == "vector_competence" else 1,
                0 if pathogen_terms and any(term in haystack for term in pathogen_terms) else 1,
                missing_assay_terms,
            )

        return sorted(
            records,
            key=score_pathogen,
        )
    if "dryad" in q:
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "dryad_aedes_behavior_videos" else 1,
                0 if record.lane in {"media", "behavior"} else 1,
            ),
        )
    if "mosquito alert" not in q:
        return records

    def score(record: EvidenceRecord) -> tuple[int, int]:
        return (
            0 if record.source == "mosquito_alert_gbif" else 1,
            0 if record.lane in {"observations", "media"} else 1,
        )

    return sorted(records, key=score)


def _index_ready(index: SourceIndex) -> bool:
    if not index.path.exists():
        return False
    try:
        index.summary()
    except sqlite3.Error:
        return False
    return True


def answer_question(question: str, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, limit: int = 5) -> dict[str, object]:
    plan = plan_question(question)
    index = SourceIndex(Path(artifact_dir) / "source_index.sqlite")
    if not _index_ready(index):
        return source_gap(plan, "The Ask Insects source index has not been built yet.")

    all_records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    for lane in plan.lanes:
        search_queries = (
            _literature_search_queries(plan.search_query)
            if plan.answer_shape == "literature" and lane == "literature"
            else _search_queries(plan.search_query)
        )
        for search_query in search_queries:
            query_records = index.search(search_query, lane=lane, limit=limit)
            for record in query_records:
                if record.record_id in seen_record_ids:
                    continue
                all_records.append(record)
                seen_record_ids.add(record.record_id)
            if query_records:
                break

    if plan.answer_shape == "media":
        media_records = [
            record
            for record in all_records
            if record.media_url and record.lane == "media" and "still image" not in record.title.lower()
        ]
        if not media_records:
            return source_gap(plan, "The Ask Insects index has no matching moving-image media records.")
        all_records = media_records

    if plan.answer_shape == "evidence" and _asks_for_still_images(plan.question):
        still_records = [record for record in all_records if record.media_url and record.lane == "media"]
        if still_records:
            all_records = still_records + [record for record in all_records if record not in still_records]

    all_records = _prioritize_named_source_records(plan.question, all_records)

    if plan.answer_shape == "literature":
        literature_records = [record for record in all_records if record.lane == "literature"]
        species = _requested_species(plan.question)
        if species:
            literature_records = [
                record for record in literature_records if record.species and record.species.lower() == species.lower()
            ]
        topical_tokens = _literature_topical_tokens(plan.question, species)
        if topical_tokens:
            literature_records = [
                record for record in literature_records if _record_matches_any_token(record, topical_tokens)
            ]
        if not literature_records:
            literature_records = _fulltext_literature_records(index, plan.question, limit=limit)
        if not literature_records:
            return source_gap(plan, "The Ask Insects index has no matching literature metadata or full-text records.")
        all_records = literature_records

    if plan.answer_shape == "genomics":
        all_records = _prioritize_genomics_records(plan.question, all_records)

    if plan.answer_shape == "resistance":
        all_records = _prioritize_resistance_records(plan.question, all_records)

    if plan.answer_shape == "public_health":
        all_records = _prioritize_public_health_records(plan.question, all_records)

    if plan.answer_shape == "ecology":
        all_records = _prioritize_ecology_records(plan.question, all_records)

    if not all_records:
        return source_gap(plan, "No matching Ask Insects records were found in the checked lanes.")

    evidence = [record_to_evidence(record) for record in all_records[:limit]]
    return {
        "ok": True,
        "answer_shape": plan.answer_shape,
        "answer": _answer_text(plan, all_records),
        "evidence": evidence,
        "source_gap": None,
    }
