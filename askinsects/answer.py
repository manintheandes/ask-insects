from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex
from .planner import QueryPlan, plan_question
from .records import EvidenceRecord
from .sources.extracted_facts import EXTRACTED_FACTS_SOURCE_ID
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
VIDEO_ATOM_QUERY_TERMS = (
    "keyframe",
    "keyframes",
    "thumbnail",
    "thumbnails",
    "preview",
    "previews",
    "frame manifest",
    "motion",
    "velocity",
    "distance moved",
    "movement",
    "locomotory video",
    "trajectory",
    "trajectories",
    "tracking",
    "track id",
    "coordinates",
    "fps",
    "codec",
    "duration",
    "resolution",
    "gap",
    "gaps",
    "failed",
    "failure",
    "discovery",
)
VIDEO_DISCOVERY_REPOSITORIES = ("pmc_oa", "pmc", "dryad", "mendeley", "osf", "zenodo", "figshare", "institutional", "paper_supplements")
IMAGE_ATOM_QUERY_TERMS = (
    "image",
    "images",
    "photo",
    "photos",
    "picture",
    "pictures",
    "life stage",
    "lifestage",
    "adult",
    "larva",
    "larval",
    "egg",
    "female",
    "male",
    "sex",
    "anatomy",
    "body part",
    "quality",
    "format",
    "still image",
)

PUBLIC_HEALTH_QUERY_STOPWORDS = {
    "aedes",
    "aegypti",
    "annual",
    "case",
    "cases",
    "core",
    "data",
    "dengue",
    "for",
    "from",
    "indicator",
    "indicators",
    "open",
    "paho",
    "show",
    "the",
}


def _wants_extracted_facts(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in ("extracted", "extracted fact", "extracted facts", "supplement", "supplementary", "table", "tables", "row", "rows"))


def _public_health_focus_terms(question: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z.-]{2,}", question):
        normalized = token.strip(".-")
        if normalized.lower() in PUBLIC_HEALTH_QUERY_STOPWORDS:
            continue
        if normalized not in terms:
            terms.append(normalized)
    return terms


def _wants_video_atoms(question: str) -> bool:
    q = question.lower()
    atom_specific_terms = (
        "keyframe",
        "keyframes",
        "thumbnail",
        "thumbnails",
        "preview",
        "previews",
        "frame manifest",
        "fps",
        "codec",
        "duration",
        "resolution",
        "motion",
        "velocity",
        "distance moved",
        "movement",
        "locomotory",
        "trajectory",
        "trajectories",
        "tracking",
        "track id",
        "coordinates",
        "gap",
        "gaps",
        "failed",
        "failure",
        "discovery",
    )
    if any(term in q for term in ("dryad", "mendeley", "osf", "flighttrackai", "flighttrack", "pmc")) and not any(
        term in q for term in atom_specific_terms
    ):
        return False
    video_specific_terms = (
        "video",
        "videos",
        "movie",
        "movies",
        "moving",
        "keyframe",
        "keyframes",
        "thumbnail",
        "thumbnails",
        "preview",
        "previews",
        "frame manifest",
        "fps",
        "codec",
        "duration",
        "resolution",
        "motion",
        "velocity",
        "distance moved",
        "movement",
        "locomotory",
        "trajectory",
        "trajectories",
        "tracking",
        "track id",
        "coordinates",
    )
    return any(term in q for term in video_specific_terms)


def _wants_video_gaps(question: str) -> bool:
    q = question.lower()
    return _wants_video_atoms(question) and any(term in q for term in ("gap", "gaps", "failed", "failure", "license", "too large"))


def _wants_video_discovery(question: str) -> bool:
    return _wants_video_atoms(question) and "discovery" in question.lower()


def _wants_video_motion(question: str) -> bool:
    q = question.lower()
    return _wants_video_atoms(question) and any(
        term in q for term in ("motion", "velocity", "distance moved", "movement", "locomotory", "trajectory", "trajectories", "tracking", "track id", "coordinates")
    )


def _wants_image_atoms(question: str) -> bool:
    q = question.lower()
    video_specific_terms = ("video", "videos", "movie", "movies", "moving", "keyframe", "thumbnail", "preview", "frame manifest", "fps", "codec", "duration", "resolution")
    return any(term in q for term in IMAGE_ATOM_QUERY_TERMS) and not any(term in q for term in video_specific_terms)


def _wants_image_gaps(question: str) -> bool:
    q = question.lower()
    return _wants_image_atoms(question) and any(term in q for term in ("gap", "gaps", "missing", "unlabeled", "label missing"))


def _wants_image_labels(question: str) -> bool:
    q = question.lower()
    return _wants_image_atoms(question) and any(
        term in q
        for term in (
            "label",
            "labels",
            "life stage",
            "lifestage",
            "adult",
            "larva",
            "larval",
            "egg",
            "female",
            "male",
            "sex",
            "anatomy",
            "body part",
            "quality",
            "format",
        )
    )


def _video_discovery_repository(question: str) -> str | None:
    q = question.lower()
    if "pmc oa" in q or "pmc open access" in q:
        return "pmc_oa"
    return next((repository for repository in VIDEO_DISCOVERY_REPOSITORIES if repository in q), None)


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
    if _wants_video_atoms(question):
        if any(term in q for term in ("motion", "velocity", "distance moved", "movement", "locomotory", "trajectory", "trajectories", "tracking", "track id", "coordinates")):
            return [
                "video motion trajectory coordinates",
                "locomotory video analysis velocity",
                "motion trajectory coordinates",
                "track frame time coordinates",
                question,
            ]
        if _wants_video_gaps(question):
            return [
                "video gap",
                "source gap",
                "probe failed",
                "artifact generation failed",
                "license unclear",
                "too large",
                question,
            ]
        if _wants_video_discovery(question):
            return [
                "video discovery",
                "discovery repository",
                "video gap",
                "video asset",
                question,
            ]
        if any(term in q for term in ("fps", "codec", "duration", "resolution")):
            return [
                "fps codec duration",
                "duration fps",
                "resolution codec",
                "video asset",
                question,
            ]
        artifact_queries: list[str] = []
        if "keyframe" in q or "keyframes" in q:
            artifact_queries.append("keyframe")
        if "preview" in q or "previews" in q:
            artifact_queries.append("preview")
        if "thumbnail" in q or "thumbnails" in q:
            artifact_queries.append("thumbnail")
        if "frame manifest" in q:
            artifact_queries.append("frame manifest")
        if artifact_queries:
            artifact_queries.append(question)
            return artifact_queries
        return [
            "keyframe",
            "preview",
            "thumbnail",
            "video asset",
            "video",
            "videos",
            question,
        ]
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
    if any(
        term in q
        for term in (
            "vectorbase",
            "veupathdb",
            "aael",
            "codon",
            "codon usage",
            "cds",
            "coding sequence",
            "coding sequences",
            "transcript sequence",
            "go annotation",
            "go term",
            "gene ontology",
            "id event",
            "id events",
            "identifier event",
            "identifier history",
            "linkout",
            "ncbi linkout",
        )
    ):
        generic_terms = {
            "aedes",
            "aegypti",
            "annotation",
            "codon",
            "cds",
            "coding",
            "for",
            "gene",
            "genes",
            "genomics",
            "sequence",
            "sequences",
            "go",
            "history",
            "id",
            "identifier",
            "linkout",
            "ncbi",
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
    if "vectornet" in q:
        return [
            "VectorNet Aedes aegypti detection presence evidence",
            "VectorNet Aedes aegypti surveillance",
            "VectorNet ECDC EFSA Aedes aegypti",
            "VectorNet regional surveillance",
            question,
        ]
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
    if "osf" in q or "flighttrackai" in q or "flighttrack" in q or "flight tracking" in q:
        return [
            "OSF FlightTrackAI Aedes aegypti video",
            "FlightTrackAI Aedes aegypti flight behavior",
            "OSF FlightTrackAI video file",
            question,
        ]
    if "mendeley" in q:
        if any(term in q for term in ("table", "tables", "row", "rows", "xlsx", "csv", "temperature", "gradient", "gradients")):
            queries = [question]
            if any(term in q for term in ("temperature", "gradient", "gradients")):
                queries.extend(
                    [
                        "Data VideoAnalysis temperature gradients AeAegypti",
                        "Aedes aegypti temperature gradients locomotory behavior",
                        "Temperature Species aegypti Behavioural Activity",
                    ]
                )
            queries.extend(
                [
                    "Mendeley Aedes aegypti behavior table row",
                    "Mendeley Aedes aegypti parsed behavior table",
                ]
            )
            return list(dict.fromkeys(queries))
        return ["Mendeley Aedes aegypti behavior media", "Mendeley wing flash video", "Mendeley flight tone", question]
    if any(term in q for term in ("wing flash", "flight tone", "flight tones", "mate recognition", "locomotory", "temperature regime", "temperature gradient", "temperature gradients")):
        return [
            "Mendeley Aedes aegypti behavior media",
            "Aedes aegypti wing flash mate recognition flight tone locomotory behavior",
            question,
        ]
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
    if any(
        term in q
        for term in (
            "cdc",
            "ecdc",
            "fact sheet",
            "factsheet",
            "guidance",
            "prevention",
            "prevent",
            "recommendation",
            "recommendations",
            "who",
            "paho",
            "plisa",
            "surveillance",
            "outbreak",
            "incidence",
            "epidemic",
            "case fatality",
            "cases",
            "deaths",
            "public health",
        )
    ):
        if "ecdc" in q:
            return [
                "ECDC Aedes aegypti factsheet",
                "Aedes aegypti vector factsheet control ecology",
                question,
                "official public-health guidance Aedes aegypti",
            ]
        if any(term in q for term in ("guidance", "prevention", "prevent", "recommendation", "recommendations", "cdc", "ecdc", "who")):
            return [
                "dengue prevention guidance",
                "official dengue guidance",
                "Aedes vector control guidance",
                "official public-health guidance Aedes aegypti",
                question,
            ]
        if any(term in q for term in ("paho", "plisa", "surveillance", "dengue", "cases", "deaths")):
            if any(term in q for term in ("core indicator", "core indicators", "open data", "annual", "country", "territory", "csv", "machine-readable", "machine readable")):
                focus_terms = _public_health_focus_terms(question)
                focus_queries = []
                for term in focus_terms[:3]:
                    focus_queries.extend([term, f"PAHO Core Indicators {term}"])
                return focus_queries + [
                    question,
                    "PAHO Core Indicators dengue cases",
                    "PAHO Open Data annual dengue cases",
                    "paho_core_indicator_dengue_cases",
                    "PAHO dengue surveillance",
                ]
            if any(term in q for term in ("dashboard", "plisa", "iframe", "tableau")):
                return [
                    "PAHO PLISA dashboard locator",
                    "PAHO dengue dashboard iframe",
                    "PAHO dengue dashboard locator",
                    "PAHO dengue surveillance",
                    question,
                ]
            return [
                "PAHO dengue surveillance week summary",
                "PAHO dengue surveillance Aedes aegypti",
                "PAHO dengue surveillance",
                "dengue surveillance public health",
                question,
            ]
        return ["official public-health guidance Aedes aegypti", "vector control guidance", "prevention guidance", question]
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
    if any(
        term in q
        for term in (
            "vectorbase",
            "veupathdb",
            "aael",
            "codon",
            "codon usage",
            "cds",
            "coding sequence",
            "coding sequences",
            "transcript sequence",
            "go annotation",
            "go term",
            "gene ontology",
            "id event",
            "id events",
            "identifier event",
            "identifier history",
            "linkout",
            "ncbi linkout",
        )
    ):
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

    def score(record: EvidenceRecord) -> tuple[int, int, int, int]:
        haystack = f"{record.title}\n{record.text}".lower()
        return (
            0 if record.lane == "dna_barcodes" else 1,
            0 if any(term in haystack for term in ("coi-5p", "marker: coi", "marker:coi", " coi ")) else 1,
            0 if record.source == "bold_api" else 1,
        )

    return sorted(records, key=score)


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _vectorbase_auxiliary_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(
        term in q
        for term in (
            "vectorbase",
            "veupathdb",
            "codon",
            "codon usage",
            "cds",
            "coding sequence",
            "coding sequences",
            "transcript sequence",
            "id event",
            "identifier event",
            "identifier history",
            "linkout",
            "ncbi linkout",
            "aael",
        )
    ):
        return []

    records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    clauses: list[tuple[str, tuple[object, ...]]] = []
    if "codon" in q:
        for codon in re.findall(r"\b[AUCGT]{3}\b", question.upper()):
            clauses.append(("record_id = ?", (f"vectorbase:codon_usage:{codon.replace('T', 'U')}",)))
    for aael_id in re.findall(r"\bAAEL[0-9A-Za-z-]+\b", question, flags=re.IGNORECASE):
        if any(term in q for term in ("cds", "coding sequence", "coding sequences")):
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:cds:{_like_escape(aael_id.upper())}%",),
                )
            )
        if "transcript sequence" in q:
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:transcript_sequence:{_like_escape(aael_id.upper())}%",),
                )
            )
        clauses.append(
            (
                "record_id LIKE ? ESCAPE '\\'",
                (f"vectorbase:id_event:{_like_escape(aael_id.upper())}:%",),
            )
        )
    for linkout_id in re.findall(r"\bAaegL5_[0-9A-Za-z_.-]+\b", question, flags=re.IGNORECASE):
        clauses.append(
            (
                "record_id LIKE ? ESCAPE '\\'",
                (f"vectorbase:ncbi_linkout:%:{_like_escape(linkout_id)}:%",),
            )
        )
    if not clauses:
        return []

    with index.connect() as conn:
        for where_sql, params in clauses:
            rows = conn.execute(
                f"""
                SELECT *
                FROM records
                WHERE source = 'vectorbase_aedes_genomics'
                  AND lane IN ('genome_features', 'transcripts')
                  AND {where_sql}
                ORDER BY record_id
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            for row in rows:
                record = EvidenceRecord.from_row(dict(row))
                if record.record_id in seen_record_ids:
                    continue
                records.append(record)
                seen_record_ids.add(record.record_id)
                if len(records) >= limit:
                    return records
    return records


def _paho_surveillance_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(term in q for term in ("paho", "plisa", "core indicator", "core indicators", "open data")):
        return []

    clauses = ["source = ?"]
    params: list[object] = ["aedes_paho_dengue_surveillance"]
    if any(
        term in q
        for term in (
            "core indicator",
            "core indicators",
            "open data",
            "annual",
            "country",
            "territory",
            "csv",
            "machine-readable",
            "machine readable",
        )
    ):
        clauses.append("record_id LIKE ?")
        params.append("%core_indicator%")
        focus_terms = _public_health_focus_terms(question)
        if focus_terms:
            term_clauses = []
            for term in focus_terms[:4]:
                pattern = f"%{term.lower()}%"
                term_clauses.append("(lower(title) LIKE ? OR lower(text) LIKE ? OR lower(record_id) LIKE ?)")
                params.extend([pattern, pattern, pattern])
            clauses.append("(" + " OR ".join(term_clauses) + ")")
    elif any(term in q for term in ("dashboard", "plisa", "iframe", "tableau")):
        clauses.append("record_id LIKE ?")
        params.append("%dashboard_locator%")

    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM records
            WHERE {" AND ".join(clauses)}
            ORDER BY record_id DESC
            LIMIT ?
            """,
            (*params, max(limit * 10, 20)),
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _resistance_marker_terms(question: str) -> list[str]:
    lower = question.lower()
    matched = []
    for term in sorted(RESISTANCE_MARKER_QUERY_TERMS, key=len, reverse=True):
        if term and term in lower:
            matched.append(term)
    return list(dict.fromkeys(matched))


def _prioritize_resistance_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    wants_marker = bool(_resistance_marker_terms(question))
    wants_extracted = _wants_extracted_facts(question)

    def score(record: EvidenceRecord) -> tuple[int, int, int, int]:
        extracted_rank = 0 if wants_extracted and record.source == EXTRACTED_FACTS_SOURCE_ID else 1
        marker_rank = 0 if wants_marker and record.source == RESISTANCE_MARKER_SOURCE_ID else 1
        irmapper_rank = 0 if not wants_marker and record.source == "irmapper_aedes" else 1
        return (
            extracted_rank,
            marker_rank,
            irmapper_rank,
            0 if record.lane == "resistance" else 1,
        )

    return sorted(records, key=score)


def _prioritize_public_health_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if "vectornet" in q:
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "vectornet_aedes_surveillance" else 1,
                0 if record.lane in {"observations", "ecology"} else 1,
            ),
        )
    if _wants_extracted_facts(question):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == EXTRACTED_FACTS_SOURCE_ID else 1,
                0 if record.lane == "public_health" else 1,
            ),
        )
    if not any(
        term in q
        for term in (
            "cdc",
            "ecdc",
            "fact sheet",
            "factsheet",
            "guidance",
            "paho",
            "plisa",
            "surveillance",
            "recommendation",
            "recommendations",
            "who",
        )
    ):
        return records
    wants_guidance = any(
        term in q
        for term in (
            "cdc",
            "ecdc",
            "fact sheet",
            "factsheet",
            "guidance",
            "prevention",
            "prevent",
            "recommendation",
            "recommendations",
            "who",
        )
    )

    requested_years = set(re.findall(r"\b(?:19|20)\d{2}\b", q))

    def score(record: EvidenceRecord) -> tuple[int, int, int, int, int, int]:
        haystack = f"{record.title}\n{record.text}\n{record.url or ''}".lower()
        if "ecdc" in q:
            organization_rank = 0 if "ecdc" in haystack else 1
        elif "cdc" in q:
            organization_rank = 0 if "cdc" in haystack else 1
        elif "world health organization" in q or "who" in q:
            organization_rank = 0 if "who" in haystack or "world health organization" in haystack else 1
        else:
            organization_rank = 0
        factsheet_rank = 0 if not any(term in q for term in ("fact sheet", "factsheet")) or any(term in haystack for term in ("fact sheet", "factsheet")) else 1
        guidance_rank = 0 if wants_guidance and record.source == "aedes_public_health_guidance" else 1
        paho_rank = 0 if not wants_guidance and any(term in q for term in ("paho", "plisa", "surveillance")) and record.source == "aedes_paho_dengue_surveillance" else 1
        if record.source == "aedes_paho_dengue_surveillance" and any(term in q for term in ("paho", "plisa", "surveillance")):
            if any(term in q for term in ("core indicator", "core indicators", "open data", "annual", "country", "territory", "csv", "machine-readable", "machine readable")) and "core_indicator" in record.record_id:
                record_rank = 0
                year_match = re.search(r":(\d{4})$", record.record_id)
                if year_match and requested_years:
                    recency_rank = 0 if year_match.group(1) in requested_years else 1
                elif year_match:
                    recency_rank = -int(year_match.group(1))
                else:
                    recency_rank = 0
            elif any(term in q for term in ("dashboard", "plisa", "iframe", "tableau")) and "dashboard_locator" in record.record_id:
                record_rank = 0
                recency_rank = 0
            elif "regional_week_summary" in record.record_id:
                record_rank = 0
                recency_rank = 0
            elif "regional_year_to_date_summary" in record.record_id:
                record_rank = 1
                recency_rank = 0
            elif "subregion" in record.record_id:
                record_rank = 2
                recency_rank = 0
            elif "serotypes" in record.record_id:
                record_rank = 3
                recency_rank = 0
            else:
                record_rank = 4
                recency_rank = 0
        else:
            record_rank = 0
            recency_rank = 0
        return (
            paho_rank,
            guidance_rank,
            organization_rank,
            factsheet_rank,
            record_rank if record.lane == "public_health" else 9,
            recency_rank,
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

    def score(record: EvidenceRecord) -> tuple[int, int, int, int]:
        extracted_rank = 0 if _wants_extracted_facts(question) and record.source == EXTRACTED_FACTS_SOURCE_ID else 1
        vectornet_rank = 0 if "vectornet" in q and record.source == "vectornet_aedes_surveillance" else 1
        return (
            extracted_rank,
            vectornet_rank,
            0 if record.source == OCCURRENCE_ECOLOGY_SOURCE_ID else 1,
            0 if record.lane == "ecology" else 1,
        )

    return sorted(records, key=score)


def _prioritize_behavior_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    if _wants_video_motion(question):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_video_atoms" else 1,
                0 if record.lane == "behavior" else 1,
            ),
        )
    if not _wants_extracted_facts(question):
        return records
    return sorted(
        records,
        key=lambda record: (
            0 if record.source == EXTRACTED_FACTS_SOURCE_ID else 1,
            0 if record.lane == "behavior" else 1,
        ),
    )


def _named_pathogen_terms(question: str) -> list[str]:
    q = question.lower()
    terms = []
    aliases = {
        "dengue": ("dengue", "denv"),
        "zika": ("zika", "zikv"),
        "chikungunya": ("chikungunya", "chikv"),
        "yellow fever": ("yellow fever", "yfv"),
        "west nile": ("west nile", "wnv"),
        "mayaro": ("mayaro", "mayv"),
    }
    for term, term_aliases in aliases.items():
        if term in q:
            terms.extend(term_aliases)
    return terms


def _extracted_fact_grain_rank(question: str, record: EvidenceRecord) -> int:
    if record.source != EXTRACTED_FACTS_SOURCE_ID or not _wants_extracted_facts(question):
        return 3
    locator = record.provenance.locator
    if "raw/extracted_facts/supplements/" in locator and ";row#" in locator:
        return 0
    if ";row#" in locator:
        return 1
    if "supplement#" in locator:
        return 3
    return 2


def _prioritize_named_source_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if _wants_video_atoms(question):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_video_atoms" else 1,
                0 if record.lane in {"media", "behavior"} else 1,
            ),
        )
    if _wants_image_atoms(question):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_image_atoms" else 1,
                0 if record.lane == "media" else 1,
            ),
        )
    if "pathogen" in q or any(term in q for term in ("dengue", "zika", "chikungunya", "yellow fever")):
        pathogen_terms = _named_pathogen_terms(question)
        wants_taxonomy = "taxonomy" in q
        wants_extracted = _wants_extracted_facts(question)
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

        def score_pathogen(record: EvidenceRecord) -> tuple[int, int, int, int, int]:
            haystack = f"{record.title}\n{record.text}".lower()
            if wants_taxonomy:
                preferred_source = "aedes_pathogen_taxonomy"
            elif wants_extracted:
                preferred_source = EXTRACTED_FACTS_SOURCE_ID
            elif wants_assay:
                preferred_source = "aedes_vector_competence_assays"
            else:
                preferred_source = "aedes_vector_competence_assays" if record.source == "aedes_vector_competence_assays" else "aedes_pathogen_taxonomy"
            missing_assay_terms = sum(1 for term in assay_terms if term not in haystack)
            return (
                0 if record.source == preferred_source else 1,
                _extracted_fact_grain_rank(question, record),
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
    if "osf" in q or "flighttrackai" in q or "flighttrack" in q or "flight tracking" in q:
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "osf_flighttrackai_aedes_videos" else 1,
                0 if record.lane in {"media", "behavior"} else 1,
            ),
        )
    if "mendeley" in q or any(term in q for term in ("wing flash", "flight tone", "flight tones", "mate recognition", "locomotory", "temperature regime", "temperature gradient", "temperature gradients")):
        wants_table_rows = any(term in q for term in ("table", "tables", "row", "rows", "xlsx", "csv", "temperature", "gradient", "gradients"))
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "mendeley_aedes_behavior_media" else 1,
                0 if record.lane in {"media", "behavior"} else 1,
                0 if wants_table_rows and record.record_id.startswith("mendeley:table-row:") else 1,
                0 if wants_table_rows and record.record_id.startswith("mendeley:table:") else 1,
            ),
        )
    if "vectornet" in q:
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "vectornet_aedes_surveillance" else 1,
                0 if record.lane in {"observations", "ecology"} else 1,
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


def _source_records(index: SourceIndex, source: str, lanes: list[str], *, limit: int) -> list[EvidenceRecord]:
    if not lanes:
        return []
    placeholders = ",".join("?" for _ in lanes)
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM records
            WHERE source = ? AND lane IN ({placeholders})
            ORDER BY lane, record_id
            LIMIT ?
            """,
            [source, *lanes, limit],
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _extracted_fact_records(index: SourceIndex, lanes: list[str], *, limit: int) -> list[EvidenceRecord]:
    if not lanes:
        return []
    lane_placeholders = ",".join("?" for _ in lanes)
    lane_order = " ".join(f"WHEN ? THEN {i}" for i, _lane in enumerate(lanes))
    params: list[object] = [*lanes, *lanes, limit]
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*
            FROM records r
            LEFT JOIN record_payloads p ON p.record_id = r.record_id
            WHERE r.source = ?
              AND r.lane IN ({lane_placeholders})
            ORDER BY
              CASE json_extract(p.payload_json, '$.confidence')
                WHEN 'parsed' THEN 0
                WHEN 'candidate' THEN 1
                WHEN 'manifest' THEN 2
                ELSE 3
              END,
              CASE r.lane {lane_order} ELSE 99 END,
              r.record_id
            LIMIT ?
            """,
            [EXTRACTED_FACTS_SOURCE_ID, *params],
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _video_atom_records(index: SourceIndex, question: str, lanes: list[str], *, limit: int) -> list[EvidenceRecord]:
    if not lanes:
        return []
    q = question.lower()
    atom_types: list[str]
    if _wants_video_gaps(question):
        atom_types = ["video_gap"]
    elif _wants_video_discovery(question):
        atom_types = ["video_asset", "video_gap"]
    elif any(term in q for term in ("motion", "velocity", "distance moved", "movement", "locomotory", "trajectory", "trajectories", "tracking", "track id", "coordinates")):
        atom_types = ["video_motion_row"]
    elif any(term in q for term in ("fps", "codec", "duration", "resolution")):
        atom_types = ["video_asset"]
    else:
        atom_types = []
        if "keyframe" in q or "keyframes" in q:
            atom_types.append("video_keyframe")
        if "preview" in q or "previews" in q:
            atom_types.append("video_preview_clip")
        if "thumbnail" in q or "thumbnails" in q:
            atom_types.append("video_thumbnail")
        if "frame manifest" in q:
            atom_types.append("video_frame_manifest")
        if not atom_types:
            atom_types = ["video_keyframe", "video_preview_clip", "video_thumbnail", "video_frame_manifest", "video_asset"]
    lane_placeholders = ",".join("?" for _ in lanes)
    atom_placeholders = ",".join("?" for _ in atom_types)
    repository = _video_discovery_repository(question)
    repository_filter = ""
    params: list[object] = [*lanes, *atom_types]
    motion_metric_order = ""
    if any(term in q for term in ("velocity", "distance moved", "movement", "locomotory")):
        motion_metric_order = """
              CASE WHEN json_extract(p.payload_json, '$.velocity_mean_cm_s') IS NOT NULL THEN 0 ELSE 1 END,
              CASE WHEN json_extract(p.payload_json, '$.distance_moved_total_cm') IS NOT NULL THEN 0 ELSE 1 END,
        """
    if repository:
        repository_filter = """
              AND (
                json_extract(p.payload_json, '$.discovery_repository') = ?
                OR json_extract(p.payload_json, '$.repository') = ?
                OR lower(r.title) LIKE ?
                OR lower(r.text) LIKE ?
              )
        """
        params.extend([repository, repository, f"%{repository.replace('_', ' ')}%", f"%{repository.replace('_', ' ')}%"])
    params.append(limit)
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*
            FROM records r
            JOIN record_payloads p ON p.record_id = r.record_id
            WHERE r.source = 'aedes_video_atoms'
              AND r.lane IN ({lane_placeholders})
              AND json_extract(p.payload_json, '$.atom_type') IN ({atom_placeholders})
              {repository_filter}
            ORDER BY
              {motion_metric_order}
              CASE json_extract(p.payload_json, '$.atom_type')
                WHEN 'video_keyframe' THEN 0
                WHEN 'video_preview_clip' THEN 1
                WHEN 'video_thumbnail' THEN 2
                WHEN 'video_frame_manifest' THEN 3
                WHEN 'video_asset' THEN 4
                WHEN 'video_motion_row' THEN 5
                WHEN 'video_gap' THEN 6
                ELSE 7
              END,
              r.record_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _image_atom_records(index: SourceIndex, question: str, lanes: list[str], *, limit: int) -> list[EvidenceRecord]:
    media_lanes = [lane for lane in lanes if lane == "media"]
    if not media_lanes:
        return []
    q = question.lower()
    if _wants_image_gaps(question):
        atom_types = ["image_gap"]
    elif _wants_image_labels(question):
        atom_types = ["image_label"]
    else:
        atom_types = ["image_asset", "image_label"]
    lane_placeholders = ",".join("?" for _ in media_lanes)
    atom_placeholders = ",".join("?" for _ in atom_types)
    filters: list[str] = []
    params: list[object] = [*media_lanes, *atom_types]
    for token in ("adult", "larva", "larval", "egg", "female", "male", "sex", "anatomy", "body part", "quality", "research", "needs_id", "format"):
        if token in q:
            filters.append("(lower(r.title) LIKE ? OR lower(r.text) LIKE ?)")
            like = f"%{token}%"
            params.extend([like, like])
    label_filter = ""
    if filters:
        label_filter = "AND (" + " OR ".join(filters) + ")"
    params.append(limit)
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*
            FROM records r
            JOIN record_payloads p ON p.record_id = r.record_id
            WHERE r.source = 'aedes_image_atoms'
              AND r.lane IN ({lane_placeholders})
              AND json_extract(p.payload_json, '$.atom_type') IN ({atom_placeholders})
              {label_filter}
            ORDER BY
              CASE json_extract(p.payload_json, '$.atom_type')
                WHEN 'image_label' THEN 0
                WHEN 'image_asset' THEN 1
                WHEN 'image_gap' THEN 2
                ELSE 3
              END,
              r.record_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def answer_question(question: str, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, limit: int = 5) -> dict[str, object]:
    plan = plan_question(question)
    index = SourceIndex(Path(artifact_dir) / "source_index.sqlite")
    if not _index_ready(index):
        return source_gap(plan, "The Ask Insects source index has not been built yet.")

    all_records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    if _wants_video_atoms(plan.question):
        for record in _video_atom_records(index, plan.question, list(plan.lanes), limit=limit):
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        if _wants_video_discovery(plan.question) and _video_discovery_repository(plan.question) and not all_records:
            return source_gap(plan, "The Ask Insects video discovery lane has no matching records for that repository.")
    if _wants_image_atoms(plan.question):
        for record in _image_atom_records(index, plan.question, list(plan.lanes), limit=limit):
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "genomics":
        for record in _vectorbase_auxiliary_records(index, plan.question, limit=limit):
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "public_health":
        for record in _paho_surveillance_records(index, plan.question, limit=limit):
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if not all_records:
        for lane in plan.lanes:
            search_queries = (
                _literature_search_queries(plan.search_query)
                if plan.answer_shape == "literature" and lane == "literature"
                else _search_queries(plan.search_query)
            )
            for search_query in search_queries:
                query_limit = max(limit * 20, 50) if plan.answer_shape == "public_health" else limit
                query_records = index.search(search_query, lane=lane, limit=query_limit)
                for record in query_records:
                    if record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
                if query_records:
                    break

    if _wants_extracted_facts(plan.question):
        for record in _extracted_fact_records(index, list(plan.lanes), limit=max(limit * 50, 250)):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "media":
        if _wants_video_gaps(plan.question) or _wants_video_discovery(plan.question):
            media_records = [
                record
                for record in all_records
                if record.lane == "media"
                and (record.media_url or "video gap" in f"{record.title} {record.text}".lower())
            ]
        else:
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

    if plan.answer_shape == "behavior":
        all_records = _prioritize_behavior_records(plan.question, all_records)

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
