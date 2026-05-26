from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex
from .planner import QueryPlan, plan_question
from .records import EvidenceRecord
from .sources.aedes_deep_sources import (
    AEDES_GLOBAL_COMPENDIUM_SOURCE_ID,
    AEDES_POPULATION_GENOMICS_SOURCE_ID,
    AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
    AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID,
    AEDES_WORLDCLIM_SOURCE_ID,
)
from .sources.aedes_crossref_literature_audit import AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID
from .sources.aedes_olfaction_literature import AEDES_OLFACTION_LITERATURE_SOURCE_ID
from .sources.extracted_facts import EXTRACTED_FACTS_SOURCE_ID
from .sources.expression_omics import EXPRESSION_OMICS_SOURCE_ID
from .sources.harvard_dataverse_suitability import HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID
from .sources.mosquito_repellent_literature import MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID
from .sources.mosquito_repellent_external_discovery import MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID
from .sources.ncbi_snp_variation import NCBI_SNP_VARIATION_SOURCE_ID
from .sources.observation_climate import OBSERVATION_CLIMATE_SOURCE_ID
from .sources.occurrence_ecology import OCCURRENCE_ECOLOGY_SOURCE_ID
from .sources.resistance_markers import MARKER_SPECS, RESISTANCE_MARKER_SOURCE_ID
from .sources.resistance_table_rows import RESISTANCE_TABLE_ROW_SOURCE_ID
from .sources.vectorbyte_abundance import VECTORBYTE_ABUNDANCE_SOURCE_ID
from .sources.who_malaria_threats_resistance import WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID


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
    "ncvbdc",
    "opendatasus",
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
    if any(
        term in q
        for term in (
            "orthogroup",
            "orthogroups",
            "coortholog",
            "coorthologs",
            "inparalog",
            "inparalogs",
            "current id resolution",
            "current-id resolution",
        )
    ):
        return False
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
    if any(term in q for term in ("dryad", "mendeley", "osf", "flighttrackai", "flighttrack", "pmc", "figshare")) and not any(
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


def _wants_olfaction_literature(question: str) -> bool:
    q = question.lower()
    return any(
        term in q
        for term in (
            "olfaction",
            "olfactory",
            "odor",
            "odour",
            "odorant",
            "chemosensory",
            "antenna",
            "antennal",
            "orco",
        )
    ) and any(
        term in q
        for term in (
            "paper",
            "papers",
            "literature",
            "study",
            "studies",
            "research",
            "pubmed",
            "full text",
            "fulltext",
            "figure",
            "fig.",
            "caption",
        )
    )


def _wants_literature_fulltext(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in ("full text", "fulltext", "figure", "fig.", "caption"))


def _wants_crossref_literature_audit(question: str) -> bool:
    q = question.lower()
    return any(
        term in q
        for term in (
            "crossref",
            "doi audit",
            "doi reconciliation",
            "publisher metadata",
            "publisher identifier",
            "literature audit",
            "literature reconciliation",
        )
    )


def _wants_mosquito_repellent_literature(question: str) -> bool:
    q = question.lower()
    repellent_terms = (
        "repellent",
        "repellents",
        "repellency",
        "spatial repellent",
        "topical repellent",
        "personal protection",
        "deet",
        "picaridin",
        "icaridin",
        "ir3535",
        "pmd",
        "citronella",
        "essential oil",
        "plant extract",
    )
    literature_terms = (
        "article",
        "articles",
        "paper",
        "papers",
        "literature",
        "study",
        "studies",
        "research",
        "pubmed",
        "crossref",
        "openalex",
        "europe pmc",
        "semantic scholar",
        "biorxiv",
        "medrxiv",
        "preprint",
        "datacite",
        "zenodo",
        "dryad",
        "figshare",
        "osf",
        "agricola",
        "usda",
        "cabi",
        "patent",
        "patents",
        "google scholar",
        "repository",
        "dataset",
        "datasets",
    )
    return any(term in q for term in repellent_terms) and any(term in q for term in literature_terms)


def _wants_mosquito_repellent_external_discovery(question: str) -> bool:
    q = question.lower()
    external_terms = (
        "dataset",
        "datasets",
        "repository",
        "repositories",
        "datacite",
        "zenodo",
        "figshare",
        "dryad",
        "osf",
        "patent",
        "patents",
        "patentsview",
        "uspto",
        "preprint",
        "biorxiv",
        "medrxiv",
        "openalex",
        "europe pmc",
        "semantic scholar",
        "agricola",
        "usda",
        "cabi",
        "google scholar",
    )
    return _wants_mosquito_repellent_literature(question) and any(term in q for term in external_terms)


def _mosquito_repellent_external_preferred_lanes(question: str) -> list[str]:
    q = question.lower()
    lanes: list[str] = []
    if any(term in q for term in ("patent", "patents", "patentsview", "uspto")):
        lanes.append("patents")
    if any(
        term in q
        for term in (
            "dataset",
            "datasets",
            "repository",
            "repositories",
            "datacite",
            "zenodo",
            "figshare",
            "dryad",
            "osf",
        )
    ):
        lanes.append("datasets")
    if any(
        term in q
        for term in (
            "preprint",
            "biorxiv",
            "medrxiv",
            "openalex",
            "europe pmc",
            "semantic scholar",
            "agricola",
            "usda",
            "cabi",
            "google scholar",
        )
    ):
        lanes.append("literature")
    return lanes


def _mosquito_repellent_external_rank(question: str, record: EvidenceRecord) -> tuple[int, int]:
    q = question.lower()
    preferred_lanes = set(_mosquito_repellent_external_preferred_lanes(question))
    lane_rank = 0 if record.lane in preferred_lanes else 1 if record.lane in {"literature", "datasets", "patents"} else 2

    haystack = " ".join(
        value
        for value in (record.record_id, record.title, record.text, record.url or "")
        if value
    ).lower()
    named_family_terms = (
        "datacite",
        "zenodo",
        "figshare",
        "dryad",
        "osf",
        "patentsview",
        "uspto",
        "biorxiv",
        "medrxiv",
        "openalex",
        "europe pmc",
        "semantic scholar",
        "agricola",
        "usda",
        "cabi",
        "google scholar",
    )
    named_terms = [term for term in named_family_terms if term in q]
    family_rank = 0 if not named_terms or any(term.replace(" ", "_") in haystack or term in haystack for term in named_terms) else 1
    return lane_rank, family_rank


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


def _wants_image_asset_metadata(question: str) -> bool:
    q = question.lower()
    return _wants_image_atoms(question) and any(
        term in q
        for term in (
            "checksum",
            "sha-256",
            "sha256",
            "byte size",
            "bytes",
            "dimension",
            "dimensions",
            "width",
            "height",
            "exif",
            "mirror",
            "mirrored",
            "raw asset",
        )
    )


def _wants_vectorbyte_traits(question: str) -> bool:
    q = question.lower()
    if any(term in q for term in ("vecdyn", "abundance", "trap count", "trap counts", "sample count", "sample counts", "mosquito count", "mosquito counts")):
        return False
    return any(
        term in q
        for term in (
            "vectorbyte",
            "vectraits",
            "trait data",
            "trait observation",
            "temperature trait",
            "thermal response",
            "thermal trait",
            "fecundity",
            "longevity",
            "development time",
            "body size",
            "egg rate",
            "transmission potential",
        )
    )


def _wants_vectorbyte_abundance(question: str) -> bool:
    q = question.lower()
    return any(
        term in q
        for term in (
            "vecdyn",
            "abundance",
            "trap count",
            "trap counts",
            "sample count",
            "sample counts",
            "mosquito count",
            "mosquito counts",
            "vectorbyte abundance",
            "peruvian amazon",
        )
    )


def _video_discovery_repository(question: str) -> str | None:
    q = question.lower()
    if "pmc oa" in q or "pmc open access" in q:
        return "pmc_oa"
    return next((repository for repository in VIDEO_DISCOVERY_REPOSITORIES if repository in q), None)


def _video_repository_source_id(repository: str | None) -> str | None:
    return {
        "pmc": "pmc_open_access_videos",
        "pmc_oa": "pmc_open_access_videos",
        "dryad": "dryad_aedes_behavior_videos",
        "mendeley": "mendeley_aedes_behavior_media",
        "osf": "osf_flighttrackai_aedes_videos",
        "zenodo": "zenodo_aedes_videos",
        "figshare": "figshare_aedes_videos",
    }.get(str(repository or ""))


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
    if plan.answer_shape == "expression":
        return f"From the Ask Insects expression omics index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "genomics":
        return f"From the local mosquito genomics index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "neurobiology":
        return f"From the local mosquito neurobiology index, {records[0].title}: {records[0].text}"
    if plan.answer_shape in {"behavior", "traits", "vector_competence", "resistance", "ecology", "public_health"}:
        label = plan.answer_shape.replace("_", " ")
        return f"From the Ask Insects {label} index, {records[0].title}: {records[0].text}"
    return f"I found {len(records)} indexed Ask Insects record(s)."


def _search_queries(question: str) -> list[str]:
    q = question.lower()
    if (
        not any(term in q for term in ("pathogen", "dengue", "zika", "chikungunya", "yellow fever", "mayaro", "west nile"))
        and any(term in q for term in ("taxonomy", "taxonomic", "synonym", "synonyms", "stegomyia", "mosquito taxonomic inventory", "mti", "wrbu"))
    ):
        return [
            "Aedes aegypti taxonomy authority",
            "Aedes Stegomyia aegypti synonym",
            "Mosquito Taxonomic Inventory Stegomyia",
            "ECDC Aedes aegypti factsheet",
            question,
        ]
    if any(term in q for term in ("who", "world health organization", "discriminating concentration", "discriminating concentrations", "bioassay", "bioassays")) and any(
        term in q for term in ("insecticide resistance", "resistance", "bioassay", "bioassays", "discriminating concentration", "discriminating concentrations")
    ):
        return [
            "WHO Aedes insecticide-resistance method",
            "discriminating concentrations bioassays Aedes",
            "WHO test procedures Aedes resistance",
            question,
        ]
    if any(term in q for term in ("climate-linked", "climate linked", "climate join", "observation climate", "joined to", "bioclim")) and any(
        term in q for term in ("observation", "observations", "occurrence", "coordinates", "country", "temperature", "precipitation")
    ):
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower()
            not in {
                "aedes",
                "aegypti",
                "annual",
                "climate",
                "climate-linked",
                "ecology",
                "linked",
                "observation",
                "observations",
                "show",
                "temperature",
                "the",
            }
        ]
        queries = [question]
        for token in salient:
            queries.append(f"{token} observation climate")
            queries.append(token)
        queries.extend([
            "WorldClim indexed Aedes aegypti observation climate sample",
            "bioclim raster values joined to indexed Aedes aegypti observation",
            "annual mean temperature precipitation observation",
        ])
        return list(dict.fromkeys(queries))
    if any(term in q for term in ("worldclim", "climate", "precipitation", "rainfall", "environmental suitability", "suitability")):
        return [
            "WorldClim climate source Aedes aegypti ecology",
            "WorldClim historical climate precipitation temperature",
            "WorldClim Aedes aegypti suitability",
            question,
        ]
    if any(term in q for term in ("global compendium", "compendium", "occurrence compendium")):
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower()
            not in {
                "aedes",
                "aegypti",
                "ae",
                "global",
                "compendium",
                "occurrence",
                "occurrences",
                "row",
                "rows",
                "show",
                "the",
                "for",
            }
        ]
        queries = []
        if salient:
            queries.append(f"Global Aedes occurrence compendium {' '.join(salient)}")
        queries.extend(["Global Aedes occurrence compendium", "Aedes aegypti occurrence compendium", question])
        return list(dict.fromkeys(queries))
    if any(term in q for term in ("bioproject", "bioprojects", "population genomics", "population-genomics", "variation", "variant", "variants", "introgression", "divergence")):
        return [
            "NCBI BioProject population-genomics Aedes aegypti",
            "Aedes aegypti population genomics BioProject",
            "introgression divergence Aedes aegypti population genomics",
            question,
        ]
    if _wants_vectorbyte_traits(question):
        generic_terms = {
            "aedes",
            "aegypti",
            "data",
            "for",
            "show",
            "temperature",
            "trait",
            "traits",
            "vectorbyte",
            "vectraits",
        }
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9.-]+", question)
            if token.lower().strip(".-") not in generic_terms
        ]
        queries = []
        if salient:
            queries.append(f"Aedes aegypti {' '.join(salient)} trait")
            queries.append(" ".join(salient))
        queries.extend(
            [
                "VectorByte Aedes aegypti trait",
                "VecTraits Aedes aegypti temperature",
                "Aedes aegypti fecundity temperature",
                question,
            ]
        )
        return list(dict.fromkeys(queries))
    if _wants_vectorbyte_abundance(question):
        generic_terms = {
            "aedes",
            "aegypti",
            "abundance",
            "count",
            "counts",
            "data",
            "for",
            "mosquito",
            "mosquitoes",
            "sample",
            "show",
            "trap",
            "vectorbyte",
            "vecdyn",
        }
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9.-]+", question)
            if token.lower().strip(".-") not in generic_terms
        ]
        queries = []
        if salient:
            queries.append(f"Aedes aegypti VecDyn {' '.join(salient)} abundance")
            queries.append(" ".join(salient))
        queries.extend(
            [
                "VectorByte VecDyn Aedes aegypti abundance",
                "Aedes aegypti abundance sample count",
                "Aedes aegypti trap count",
                question,
            ]
        )
        return list(dict.fromkeys(queries))
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
            "geo",
            "gene expression",
            "expression data",
            "expression omics",
            "expression matrix",
            "expression matrices",
            "count matrix",
            "count matrices",
            "differential expression",
            "differential-expression",
            "raw sra reanalysis",
            "sra reanalysis",
            "rna-seq",
            "rnaseq",
            "transcriptome",
            "transcriptomic",
            "transcriptomics",
            "sra run",
            "sra runs",
        )
    ):
        generic_terms = {
            "aedes",
            "aegypti",
            "data",
            "expression",
            "for",
            "geo",
            "omics",
            "rna",
            "rnaseq",
            "run",
            "runs",
            "seq",
            "show",
            "sra",
            "the",
            "transcriptome",
            "transcriptomic",
            "transcriptomics",
        }
        salient = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", question)
            if token.lower() not in generic_terms
        ]
        queries = []
        if salient:
            queries.append(" ".join(salient))
            queries.append(f"Aedes aegypti expression {' '.join(salient)}")
        if any(term in q for term in ("count matrix", "count matrices", "expression matrix", "expression matrices", "differential expression", "differential-expression")):
            queries.extend(["count matrices differential-expression outputs source gap", "expression matrix source gap"])
        if any(term in q for term in ("raw sra reanalysis", "sra reanalysis", "raw read reanalysis", "raw reads reanalysis")):
            queries.append("raw SRA reanalysis count matrices source gap")
        queries.extend(["GEO RNA-seq expression Aedes aegypti", "SRA RNA-seq Aedes aegypti", question])
        return list(dict.fromkeys(queries))
    if any(term in q for term in ("uniprot", "protein function", "proteome")):
        accession_terms = [
            token
            for token in re.findall(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|A0A[A-Z0-9]+|UP[0-9]{9}|AAEL[0-9A-Za-z-]+)\b", question, flags=re.IGNORECASE)
        ]
        queries = []
        queries.extend(accession_terms)
        queries.extend(f"UniProt {term}" for term in accession_terms)
        queries.extend(["UniProt Aedes aegypti protein function", "UniProt proteome Aedes aegypti", question])
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
            "homolog",
            "homologs",
            "ortholog",
            "orthologs",
            "orthology",
            "orthomcl",
            "orthogroup",
            "orthogroups",
            "coortholog",
            "coorthologs",
            "inparalog",
            "inparalogs",
            "current id resolution",
            "current-id resolution",
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
            "homolog",
            "homologs",
            "ncbi",
            "ortholog",
            "orthologs",
            "orthology",
            "orthomcl",
            "orthogroup",
            "orthogroups",
            "coortholog",
            "coorthologs",
            "inparalog",
            "inparalogs",
            "current",
            "resolution",
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
        if _wants_orthomcl_relationship(question, "ortholog"):
            queries.extend(["OrthoMCL ortholog Aedes aegypti", "aaeg-old AAEL ortholog", "VectorBase Aedes orthology"])
        if _wants_orthomcl_relationship(question, "coortholog"):
            queries.extend(["OrthoMCL coortholog Aedes aegypti", "aaeg-old AAEL coortholog"])
        if _wants_orthomcl_relationship(question, "inparalog"):
            queries.extend(["OrthoMCL inparalog Aedes aegypti", "aaeg-old AAEL inparalog"])
        if any(term in q for term in ("orthogroup", "orthogroups")):
            queries.extend(
                [
                    "OrthoMCL orthogroup Aedes aegypti",
                    "aaeg AAEL orthogroup",
                    "VectorBase orthogroup membership",
                ]
            )
        if any(term in q for term in ("current id resolution", "current-id resolution")):
            queries.extend(["current VectorBase identifier resolution", "current ID resolution AAEL"])
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
            "wer",
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
            "wolbachia",
            "world mosquito program",
            "wmp",
            "yogyakarta",
        )
    ):
        if any(term in q for term in ("wolbachia", "world mosquito program", "wmp", "yogyakarta")):
            return [
                "World Mosquito Program Wolbachia Yogyakarta",
                "Wolbachia intervention Aedes aegypti",
                "Yogyakarta Wolbachia dengue reduction",
                question,
            ]
        if "ecdc" in q:
            return [
                "ECDC Aedes aegypti factsheet",
                "Aedes aegypti vector factsheet control ecology",
                question,
                "official public-health guidance Aedes aegypti",
            ]
        if "cdc" in q and any(term in q for term in ("arbonet", "surveillance", "current data", "historic data", "cases", "county", "jurisdiction", "week")):
            return [
                "CDC ArboNET dengue surveillance",
                "CDC dengue current historic CSV",
                "CDC dengue cases by jurisdiction county week",
                question,
            ]
        if any(term in q for term in ("india", "ncvbdc", "national centre for vector borne", "national center for vector borne")) and any(
            term in q for term in ("dengue", "cases", "deaths", "surveillance")
        ):
            if any(term in q for term in ("last two", "two years", "recent", "latest")):
                return [
                    "NCVBDC India dengue last two complete years deaths",
                    "NCVBDC India dengue deaths 2024 2025",
                    question,
                    "India dengue cases deaths NCVBDC",
                ]
            return [
                "NCVBDC India dengue cases deaths",
                "India national dengue cases deaths by year",
                question,
            ]
        if any(term in q for term in ("brazil", "opendatasus", "datasus", "sinan")) and any(
            term in q for term in ("dengue", "cases", "deaths", "surveillance", "notifications", "hospitalized")
        ):
            if any(term in q for term in ("week", "weekly", "epidemiological")):
                return [
                    "OpenDataSUS Brazil dengue epidemiological week",
                    "SINAN Brazil dengue weekly notifications",
                    question,
                ]
            if any(term in q for term in ("state", "uf", "sao paulo", "rio de janeiro")):
                return [
                    "OpenDataSUS Brazil dengue state surveillance",
                    "SINAN Brazil dengue state deaths notifications",
                    question,
                ]
            return [
                "OpenDataSUS Brazil dengue surveillance summary",
                "SINAN Brazil dengue notifications deaths",
                question,
            ]
        if "who" in q and any(term in q for term in ("wer", "surveillance", "situation update", "dashboard", "health data", "global update", "cases", "deaths")):
            if any(term in q for term in ("dashboard", "health data", "data platform", "shiny")):
                return [
                    "WHO dengue dashboard locator",
                    "WHO Western Pacific Health Data Platform dengue",
                    "WHO dengue surveillance dashboard",
                    question,
                ]
            if any(term in q for term in ("wer", "global update", "publication", "2024")):
                return [
                    "WHO WER dengue global situation surveillance progress",
                    "WHO dengue global situation surveillance progress 2024 update",
                    "WHO dengue publication download",
                    question,
                ]
            return [
                "WHO dengue surveillance situation update",
                "WHO Western Pacific dengue situation update",
                "WHO dengue surveillance",
                question,
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
    for search_query in _fulltext_literature_search_queries(question):
        query_limit = max(limit * 20, 50) if _wants_literature_fulltext(question) else limit
        query_records = index.search_literature_fulltext(search_query, limit=query_limit)
        if any(term in question.lower() for term in ("figure", "fig.", "caption")):
            query_records = sorted(
                query_records,
                key=lambda record: (
                    0 if record.text.lower().startswith("figure caption:") else 1,
                    0 if record.source == AEDES_OLFACTION_LITERATURE_SOURCE_ID else 1,
                ),
            )
        for record in query_records:
            if record.record_id in seen_record_ids:
                continue
            records.append(record)
            seen_record_ids.add(record.record_id)
            if len(records) >= limit:
                break
        if query_records:
            break
    return records


def _fulltext_literature_search_queries(question: str) -> list[str]:
    species = _requested_species(question)
    tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", question)]
    excluded = set(LITERATURE_QUERY_STOPWORDS)
    excluded.update(
        {
            "caption",
            "captions",
            "fig",
            "figure",
            "figures",
            "mention",
            "mentions",
            "mentioned",
            "olfaction",
            "olfactory",
        }
    )
    excluded.update({"aedes", "aegypti", "mosquito", "mosquitoes"})
    if species:
        excluded.update(token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", species))
    distinctive = [token for token in tokens if token.lower() not in excluded]
    queries: list[str] = []
    if distinctive:
        queries.append(" ".join(distinctive))
    queries.extend(_literature_search_queries(question))
    return list(dict.fromkeys(queries))


def _record_matches_any_token(record: EvidenceRecord, tokens: set[str]) -> bool:
    haystack = f"{record.title}\n{record.text}".lower()
    return any(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)


def _wants_snp_variation(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in ("dbsnp", "snp", "snps", "variant", "variants", "variation"))


def _record_payload_reason(record: EvidenceRecord) -> str:
    if record.payload:
        return str(record.payload.get("reason") or "")
    if ":gap:" in record.record_id:
        return record.record_id.rsplit(":gap:", 1)[-1]
    return ""


def _wants_expression_computed_outputs(question: str) -> bool:
    q = question.lower()
    return any(
        term in q
        for term in (
            "count matrix",
            "count matrices",
            "expression matrix",
            "expression matrices",
            "normalized expression",
            "normalised expression",
            "differential expression",
            "differential-expression",
            "raw sra reanalysis",
            "sra reanalysis",
            "raw read reanalysis",
            "raw reads reanalysis",
        )
    )


def _expression_computed_gap_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    if not _wants_expression_computed_outputs(question):
        return []
    q = question.lower()
    preferred_reasons: list[str] = []
    if any(term in q for term in ("raw sra", "sra reanalysis", "raw read", "raw reads", "count matrix", "count matrices")):
        preferred_reasons.append("raw_sra_reanalysis_not_performed")
    if any(
        term in q
        for term in (
            "differential expression",
            "differential-expression",
            "expression matrix",
            "expression matrices",
            "normalized expression",
            "normalised expression",
        )
    ):
        preferred_reasons.append("differential_expression_outputs_not_indexed")
    preferred_reasons.extend(["raw_sra_reanalysis_not_performed", "differential_expression_outputs_not_indexed"])
    reason_rank = {reason: index for index, reason in enumerate(dict.fromkeys(preferred_reasons))}
    records = [
        record
        for record in _source_records(index, EXPRESSION_OMICS_SOURCE_ID, ["expression"], limit=max(limit * 20, 50))
        if record.record_id.startswith("expression:gap:")
    ]
    return sorted(records, key=lambda record: reason_rank.get(_record_payload_reason(record), len(reason_rank)))[:limit]


def _prioritize_expression_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    if not _wants_expression_computed_outputs(question):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == EXPRESSION_OMICS_SOURCE_ID else 1,
                0 if record.lane == "expression" else 1,
            ),
        )
    q = question.lower()
    raw_terms = ("raw sra", "sra reanalysis", "raw read", "raw reads", "count matrix", "count matrices")
    differential_terms = (
        "differential expression",
        "differential-expression",
        "expression matrix",
        "expression matrices",
        "normalized expression",
        "normalised expression",
    )
    preferred: list[str] = []
    if any(term in q for term in raw_terms):
        preferred.append("raw_sra_reanalysis_not_performed")
    if any(term in q for term in differential_terms):
        preferred.append("differential_expression_outputs_not_indexed")
    preferred.extend(["raw_sra_reanalysis_not_performed", "differential_expression_outputs_not_indexed"])
    reason_rank = {reason: index for index, reason in enumerate(dict.fromkeys(preferred))}
    return sorted(
        records,
        key=lambda record: (
            0 if record.source == EXPRESSION_OMICS_SOURCE_ID else 1,
            0 if record.record_id.startswith("expression:gap:") else 1,
            reason_rank.get(_record_payload_reason(record), len(reason_rank)),
            0 if record.lane == "expression" else 1,
        ),
    )


def _wants_advanced_orthology_boundary(question: str) -> bool:
    q = question.lower()
    return any(
        term in q
        for term in (
            "orthogroup",
            "orthogroups",
        )
    )


def _wants_current_id_resolution(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in ("current id resolution", "current-id resolution", "current identifier resolution"))


def _wants_orthomcl_relationship(question: str, relationship_type: str) -> bool:
    q = question.lower()
    if relationship_type == "coortholog":
        return any(term in q for term in ("coortholog", "coorthologs"))
    if relationship_type == "inparalog":
        return any(term in q for term in ("inparalog", "inparalogs"))
    if relationship_type == "ortholog":
        if (
            _wants_advanced_orthology_boundary(question)
            or _wants_orthomcl_relationship(question, "coortholog")
            or _wants_orthomcl_relationship(question, "inparalog")
        ):
            return False
        return any(term in q for term in ("homolog", "homologs", "ortholog", "orthologs", "orthology", "orthomcl"))
    return False


def _prioritize_genomics_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if _wants_snp_variation(question):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == NCBI_SNP_VARIATION_SOURCE_ID else 1,
                0 if record.lane == "genome_features" else 1,
            ),
        )
    if any(term in q for term in ("bioproject", "bioprojects", "population genomics", "population-genomics", "introgression", "divergence")):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == AEDES_POPULATION_GENOMICS_SOURCE_ID else 1,
                0 if record.lane == "genome_features" else 1,
            ),
        )
    if any(term in q for term in ("uniprot", "protein function", "proteome")):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_uniprot_proteins" else 1,
                0 if record.lane == "proteins" else 1,
            ),
        )
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
            "homolog",
            "homologs",
            "ortholog",
            "orthologs",
            "orthology",
            "orthomcl",
            "orthogroup",
            "orthogroups",
            "coortholog",
            "coorthologs",
            "inparalog",
            "inparalogs",
            "current id resolution",
            "current-id resolution",
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
        relationship_prefixes: list[str] = []
        if _wants_orthomcl_relationship(question, "coortholog"):
            relationship_prefixes.append("vectorbase:coortholog:")
        if _wants_orthomcl_relationship(question, "inparalog"):
            relationship_prefixes.append("vectorbase:inparalog:")
        if _wants_orthomcl_relationship(question, "ortholog"):
            relationship_prefixes.append("vectorbase:ortholog:")
        wants_orthogroup = _wants_advanced_orthology_boundary(question)
        wants_current_id = _wants_current_id_resolution(question)
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "vectorbase_aedes_genomics" else 1,
                0 if wants_orthogroup and record.record_id.startswith("vectorbase:orthogroup:") else 1,
                0 if wants_current_id and not wants_orthogroup and record.record_id.startswith("vectorbase:current_id:") else 1,
                0
                if relationship_prefixes and any(record.record_id.startswith(prefix) for prefix in relationship_prefixes)
                else 1
                if relationship_prefixes
                else 0,
                2 if record.record_id == "vectorbase:gap:advanced_orthology_current_id_resolution" else 1,
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


def _prioritize_neurobiology_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if "sra" in q and ("reanalysis" in q or "workflow" in q or "align" in q or "alignment" in q):
        return sorted(
            records,
            key=lambda record: (
                0 if record.record_id.endswith(":reanalysis-workflow") else 1,
                0 if "reanalysis workflow" in f"{record.title} {record.text}".lower() else 1,
            ),
        )
    return records


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _record_id_prefix_range(prefix: str) -> tuple[str, str]:
    return prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)


def _uniprot_direct_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    terms = _uniprot_exact_terms(question)
    if not terms:
        return []

    records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    with index.connect() as conn:
        for term in terms:
            clauses: list[tuple[str, tuple[object, ...]]] = []
            if term.startswith("UP"):
                clauses.append(("record_id = ?", (f"uniprot:proteome:{term}",)))
            elif term.startswith("AAEL"):
                like = f"%{_like_escape(term)}%"
                clauses.append(
                    (
                        "(title LIKE ? ESCAPE '\\' OR text LIKE ? ESCAPE '\\')",
                        (like, like),
                    )
                )
            else:
                clauses.append(("record_id = ?", (f"uniprot:protein:{term}",)))

            for where_sql, params in clauses:
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM records
                    WHERE source = 'aedes_uniprot_proteins'
                      AND lane = 'proteins'
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


def _uniprot_exact_terms(question: str) -> list[str]:
    q = question.lower()
    if not any(term in q for term in ("uniprot", "protein function", "proteome")):
        return []
    return [
        term.upper()
        for term in re.findall(
            r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|A0A[A-Z0-9]+|UP[0-9]{9}|AAEL[0-9A-Za-z-]+)\b",
            question,
            flags=re.IGNORECASE,
        )
    ]


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
            "homolog",
            "homologs",
            "ortholog",
            "orthologs",
            "orthology",
            "orthomcl",
            "orthogroup",
            "orthogroups",
            "coortholog",
            "coorthologs",
            "inparalog",
            "inparalogs",
            "current id resolution",
            "current-id resolution",
            "aael",
        )
    ):
        return []

    records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    clauses: list[tuple[str, tuple[object, ...]]] = []
    aael_ids = re.findall(r"\bAAEL[0-9A-Za-z-]+\b", question, flags=re.IGNORECASE)
    if _wants_advanced_orthology_boundary(question) and not aael_ids:
        lower, upper = _record_id_prefix_range("vectorbase:orthogroup:")
        clauses.append(("record_id >= ? AND record_id < ?", (lower, upper)))
    if "codon" in q:
        for codon in re.findall(r"\b[AUCGT]{3}\b", question.upper()):
            clauses.append(("record_id = ?", (f"vectorbase:codon_usage:{codon.replace('T', 'U')}",)))
    for relationship_type in ("coortholog", "inparalog", "ortholog"):
        if not aael_ids and _wants_orthomcl_relationship(question, relationship_type):
            lower, upper = _record_id_prefix_range(f"vectorbase:{relationship_type}:")
            clauses.append(("record_id >= ? AND record_id < ?", (lower, upper)))
    for aael_id in aael_ids:
        escaped_aael = _like_escape(aael_id.upper())
        if _wants_current_id_resolution(question):
            clauses.append(
                (
                    "record_id = ?",
                    (f"vectorbase:current_id:{aael_id.upper()}",),
                )
            )
        if _wants_advanced_orthology_boundary(question):
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:orthogroup:%:aaeg_{escaped_aael}",),
                )
            )
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:orthogroup:%:aaeg-old_{escaped_aael}",),
                )
            )
        if _wants_orthomcl_relationship(question, "ortholog"):
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:ortholog:aaeg-old_{escaped_aael}:%",),
                )
            )
        if _wants_orthomcl_relationship(question, "coortholog"):
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:coortholog:aaeg-old_{escaped_aael}:%",),
                )
            )
        if _wants_orthomcl_relationship(question, "inparalog"):
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:inparalog:aaeg-old_{escaped_aael}:%",),
                )
            )
        if any(term in q for term in ("cds", "coding sequence", "coding sequences")):
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:cds:{escaped_aael}%",),
                )
            )
        if "transcript sequence" in q:
            clauses.append(
                (
                    "record_id LIKE ? ESCAPE '\\'",
                    (f"vectorbase:transcript_sequence:{escaped_aael}%",),
                )
            )
        clauses.append(
            (
                "record_id LIKE ? ESCAPE '\\'",
                (f"vectorbase:id_event:{escaped_aael}:%",),
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


def _who_surveillance_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if "who" not in q and "wer" not in q:
        return []
    if not any(term in q for term in ("surveillance", "situation", "dashboard", "health data", "wer", "global update", "cases", "deaths")):
        return []

    clauses = ["source = ?"]
    params: list[object] = ["aedes_who_dengue_surveillance"]
    if any(term in q for term in ("dashboard", "health data", "data platform", "shiny")):
        clauses.append("record_id LIKE ?")
        params.append("%dashboard_locator%")
    elif any(term in q for term in ("wer", "global update", "publication", "download", "2024")):
        clauses.append("(record_id LIKE ? OR record_id LIKE ? OR lower(text) LIKE ?)")
        params.extend(["%wer_global_update%", "%publication_download%", "%global%"])
    elif any(term in q for term in ("situation update", "situation report", "bi-weekly", "biweekly")):
        clauses.append("(record_id LIKE ? OR record_id LIKE ?)")
        params.extend(["%situation_report%", "%archive%"])

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


def _cdc_surveillance_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(term in q for term in ("cdc", "arbonet")):
        return []
    if not any(term in q for term in ("dengue", "surveillance", "current", "historic", "cases", "county", "jurisdiction", "week", "limitation")):
        return []

    clauses = ["source = ?"]
    params: list[object] = ["aedes_cdc_dengue_surveillance"]
    if "limitation" in q or "under-report" in q or "underreport" in q or "lag" in q:
        clauses.append("record_id LIKE ?")
        params.append("%:limitation:%")
    elif "current" in q or re.search(r"\b2026\b", q):
        clauses.append("(record_id LIKE ? OR lower(text) LIKE ?)")
        params.extend(["%:current_%", "%current%"])
    elif "historic" in q or "cumulative" in q or re.search(r"\b20(?:1\d|2[0-5])\b", q):
        clauses.append("(record_id LIKE ? OR lower(text) LIKE ?)")
        params.extend(["%:historic:%", "%historic%"])
    focus_terms = _public_health_focus_terms(question)
    if focus_terms:
        term_clauses = []
        for term in focus_terms[:4]:
            pattern = f"%{term.lower()}%"
            term_clauses.append("(lower(title) LIKE ? OR lower(text) LIKE ? OR lower(record_id) LIKE ?)")
            params.extend([pattern, pattern, pattern])
        clauses.append("(" + " OR ".join(term_clauses) + ")")

    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM records
            WHERE {" AND ".join(clauses)}
            ORDER BY
                CASE
                    WHEN record_id LIKE '%Data_Bites%' THEN 0
                    WHEN record_id LIKE '%Cases_by_Jurisdiction%' THEN 1
                    WHEN record_id LIKE '%Cases_by_County%' THEN 2
                    WHEN record_id LIKE '%Epi_Curve%' THEN 3
                    WHEN record_id LIKE '%:limitation:%' THEN 4
                    ELSE 5
                END,
                record_id
            LIMIT ?
            """,
            (*params, max(limit * 20, 50)),
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _ncvbdc_surveillance_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(term in q for term in ("india", "ncvbdc", "national centre for vector borne", "national center for vector borne")):
        return []
    if not any(term in q for term in ("dengue", "surveillance", "cases", "deaths")):
        return []

    clauses = ["source = ?"]
    params: list[object] = ["aedes_ncvbdc_dengue_surveillance"]
    if any(term in q for term in ("last two", "two years", "recent", "latest")):
        clauses.append("record_id LIKE ?")
        params.append("%last_two_complete_years%")
    elif re.search(r"\b20(?:2[1-6])\b", q):
        years = re.findall(r"\b20(?:2[1-6])\b", q)
        year_clauses = []
        for year in years[:4]:
            year_clauses.append("record_id LIKE ?")
            params.append(f"%:{year}")
        clauses.append("(" + " OR ".join(year_clauses) + ")")
    else:
        clauses.append("(record_id LIKE ? OR record_id LIKE ?)")
        params.extend(["%:country:india:%", "%last_two_complete_years%"])
    focus_terms = _public_health_focus_terms(question)
    focus_terms = [term for term in focus_terms if term.lower() not in {"india"}]
    if focus_terms:
        term_clauses = []
        for term in focus_terms[:4]:
            pattern = f"%{term.lower()}%"
            term_clauses.append("(lower(title) LIKE ? OR lower(text) LIKE ? OR lower(record_id) LIKE ?)")
            params.extend([pattern, pattern, pattern])
        clauses.append("(" + " OR ".join(term_clauses) + ")")

    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM records
            WHERE {" AND ".join(clauses)}
            ORDER BY
              CASE WHEN record_id LIKE '%last_two_complete_years%' THEN 0 ELSE 1 END,
              record_id DESC
            LIMIT ?
            """,
            (*params, max(limit * 10, 20)),
        ).fetchall()
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _opendatasus_surveillance_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not any(term in q for term in ("brazil", "opendatasus", "datasus", "sinan")):
        return []
    if not any(term in q for term in ("dengue", "surveillance", "cases", "deaths", "notifications", "hospitalized", "week")):
        return []

    clauses = ["source = ?"]
    params: list[object] = ["aedes_opendatasus_dengue_surveillance"]
    if any(term in q for term in ("week", "weekly", "epidemiological")):
        clauses.append("(record_id LIKE ? OR record_id LIKE ?)")
        params.extend(["%:country_week:%", "%:residence_state_week:%"])
    elif any(term in q for term in ("state", "uf", "sao paulo", "rio de janeiro")):
        clauses.append("(record_id LIKE ? OR record_id LIKE ?)")
        params.extend(["%:residence_state:%", "%:notification_state:%"])
    else:
        clauses.append("record_id LIKE ?")
        params.append("%:country:brazil:%")
    years = re.findall(r"\b20(?:2[0-9])\b", q)
    if years:
        year_clauses = []
        for year in years[:4]:
            year_clauses.append("(record_id LIKE ? OR lower(text) LIKE ?)")
            params.extend([f"%:{year}", f"%{year}%"])
        clauses.append("(" + " OR ".join(year_clauses) + ")")
    focus_terms = [term for term in _public_health_focus_terms(question) if term.lower() not in {"brazil", "sinan", "datasus"}]
    if focus_terms:
        term_clauses = []
        for term in focus_terms[:4]:
            pattern = f"%{term.lower()}%"
            term_clauses.append("(lower(title) LIKE ? OR lower(text) LIKE ? OR lower(record_id) LIKE ?)")
            params.extend([pattern, pattern, pattern])
        clauses.append("(" + " OR ".join(term_clauses) + ")")

    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM records
            WHERE {" AND ".join(clauses)}
            ORDER BY
              CASE
                WHEN record_id LIKE '%:country:brazil:%' THEN 0
                WHEN record_id LIKE '%:residence_state:%' THEN 1
                WHEN record_id LIKE '%:country_week:%' THEN 2
                WHEN record_id LIKE '%:residence_state_week:%' THEN 3
                ELSE 4
              END,
              record_id DESC
            LIMIT ?
            """,
            (*params, max(limit * 20, 50)),
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
    q = question.lower()
    wants_table = wants_extracted or any(term in q for term in ("frequency", "frequencies", "haplotype", "genotype", "mortality", "lc50", "lc90", "table row"))
    wants_who_database = any(term in q for term in ("malaria threats", "who database", "global database", "who resistance database", "who insecticide resistance database"))
    wants_who_guidance = any(term in q for term in ("who", "world health organization", "guidance", "method", "methods", "bioassay", "bioassays", "discriminating concentration", "discriminating concentrations"))

    def score(record: EvidenceRecord) -> tuple[object, ...]:
        who_database_rank = 0 if wants_who_database and record.source == WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID else 1
        who_guidance_rank = 0 if wants_who_guidance and record.source == AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID else 1
        table_rank = 0 if wants_table and record.source == RESISTANCE_TABLE_ROW_SOURCE_ID else 1
        extracted_rank = 0 if wants_extracted and record.source == EXTRACTED_FACTS_SOURCE_ID else 1
        marker_rank = 0 if wants_marker and not wants_table and record.source == RESISTANCE_MARKER_SOURCE_ID else 1
        irmapper_rank = 0 if not wants_marker and record.source == "irmapper_aedes" else 1
        return (
            who_database_rank,
            who_guidance_rank,
            table_rank,
            extracted_rank,
            marker_rank,
            irmapper_rank,
            0 if record.lane == "resistance" else 1,
            record.record_id,
        )

    return sorted(records, key=score)


def _resistance_table_row_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not (
        _wants_extracted_facts(question)
        or any(term in q for term in ("frequency", "frequencies", "haplotype", "genotype", "mortality", "lc50", "lc90", "table row"))
    ):
        return []
    with index.connect() as conn:
        rows = conn.execute(
            """
            SELECT r.*
            FROM records r
            JOIN record_payloads p ON p.record_id = r.record_id
            WHERE r.source = ?
              AND r.lane = 'resistance'
              AND json_extract(p.payload_json, '$.confidence') = 'parsed_table_schema_validated'
            ORDER BY r.record_id
            LIMIT ?
            """,
            (RESISTANCE_TABLE_ROW_SOURCE_ID, max(limit * 50, 250)),
        ).fetchall()
    records = [EvidenceRecord.from_row(dict(row)) for row in rows]
    if records:
        return _prioritize_named_source_records(question, records)[:limit]
    records = _source_search_records(
        index,
        RESISTANCE_TABLE_ROW_SOURCE_ID,
        "resistance",
        question,
        limit=max(limit * 20, 50),
    )
    if records:
        return _prioritize_named_source_records(question, records)[:limit]
    return _source_records(index, RESISTANCE_TABLE_ROW_SOURCE_ID, ["resistance"], limit=limit)


def _prioritize_public_health_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    q = question.lower()
    if any(term in q for term in ("wolbachia", "world mosquito program", "wmp", "yogyakarta")):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_wolbachia_interventions" else 1,
                0 if record.lane == "public_health" else 1,
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
    if any(term in q for term in ("cdc", "arbonet")) and any(term in q for term in ("dengue", "surveillance", "current", "historic", "cases", "county", "jurisdiction", "week", "limitation")):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_cdc_dengue_surveillance" else 1,
                0 if record.lane == "public_health" else 1,
                0 if "Data_Bites" in record.record_id else 1,
                0 if "Cases_by_Jurisdiction" in record.record_id else 1,
                0 if "Cases_by_County" in record.record_id else 1,
                0 if "Epi_Curve" in record.record_id else 1,
            ),
        )
    if any(term in q for term in ("india", "ncvbdc", "national centre for vector borne", "national center for vector borne")) and any(
        term in q for term in ("dengue", "surveillance", "cases", "deaths")
    ):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_ncvbdc_dengue_surveillance" else 1,
                0 if "last_two_complete_years" in record.record_id else 1,
                0 if record.lane == "public_health" else 1,
            ),
        )
    if any(term in q for term in ("brazil", "opendatasus", "datasus", "sinan")) and any(
        term in q for term in ("dengue", "surveillance", "cases", "deaths", "notifications", "hospitalized", "week")
    ):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "aedes_opendatasus_dengue_surveillance" else 1,
                0 if record.lane == "public_health" else 1,
                0 if "country:brazil" in record.record_id else 1,
                0 if "residence_state" in record.record_id else 1,
                0 if "country_week" in record.record_id else 1,
                record.record_id,
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
            "wer",
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
    wants_who_surveillance = ("who" in q or "world health organization" in q or "wer" in q) and any(
        term in q
        for term in (
            "wer",
            "surveillance",
            "situation",
            "dashboard",
            "health data",
            "global update",
            "cases",
            "deaths",
        )
    )
    if wants_who_surveillance:
        wants_guidance = any(
            term in q
            for term in (
                "fact sheet",
                "factsheet",
                "guidance",
                "prevention",
                "prevent",
                "recommendation",
                "recommendations",
            )
        )

    requested_years = set(re.findall(r"\b(?:19|20)\d{2}\b", q))

    def score(record: EvidenceRecord) -> tuple[object, ...]:
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
        who_rank = 0 if wants_who_surveillance and record.source == "aedes_who_dengue_surveillance" else 1
        paho_rank = 0 if not wants_guidance and any(term in q for term in ("paho", "plisa", "surveillance")) and record.source == "aedes_paho_dengue_surveillance" else 1
        if record.source == "aedes_who_dengue_surveillance" and wants_who_surveillance:
            if any(term in q for term in ("dashboard", "health data", "data platform", "shiny")) and "dashboard_locator" in record.record_id:
                record_rank = 0
            elif any(term in q for term in ("wer", "global update", "publication", "2024")) and ("wer_global_update" in record.record_id or "publication_download" in record.record_id):
                record_rank = 0
            elif any(term in q for term in ("situation", "bi-weekly", "biweekly")) and ("situation_report" in record.record_id or "archive" in record.record_id):
                record_rank = 0
            else:
                record_rank = 1
            recency_rank = 0
        elif record.source == "aedes_paho_dengue_surveillance" and any(term in q for term in ("paho", "plisa", "surveillance")):
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
            who_rank,
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
            "climate-linked",
            "climate linked",
            "climate join",
            "observation climate",
            "bioclim",
            "joined",
            "global compendium",
            "compendium",
            "worldclim",
            "climate",
            "precipitation",
            "temperature",
            "suitability",
            "dataverse",
            "transmission risk",
        )
    ):
        return records

    wants_observation_climate = any(term in q for term in ("climate-linked", "climate linked", "climate join", "observation climate", "bioclim", "joined")) and any(
        term in q for term in ("observation", "observations", "occurrence", "country", "coordinates", "temperature", "precipitation")
    )
    wants_worldclim = any(term in q for term in ("worldclim", "climate", "precipitation", "temperature", "suitability"))
    wants_dataverse_suitability = any(term in q for term in ("dataverse", "suitability", "transmission risk", "dengue transmission"))
    wants_compendium = any(term in q for term in ("global compendium", "compendium", "occurrence compendium"))
    wants_vectorbyte_abundance = _wants_vectorbyte_abundance(question)
    focus_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", question)
        if token.lower()
        not in {
            "aedes",
            "aegypti",
            "and",
            "annual",
            "climate",
            "for",
            "in",
            "linked",
            "mean",
            "ecology",
            "observation",
            "observations",
            "precipitation",
            "sample",
            "samples",
            "show",
            "temperature",
            "the",
            "worldclim",
        }
    }

    def score(record: EvidenceRecord) -> tuple[object, ...]:
        worldclim_rank = 0 if wants_worldclim and record.source == AEDES_WORLDCLIM_SOURCE_ID else 1
        observation_climate_rank = 0 if wants_observation_climate and record.source == OBSERVATION_CLIMATE_SOURCE_ID else 1
        dataverse_rank = 0 if wants_dataverse_suitability and record.source == HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID else 1
        compendium_rank = 0 if wants_compendium and record.source == AEDES_GLOBAL_COMPENDIUM_SOURCE_ID else 1
        haystack = f"{record.title}\n{record.text}".lower()
        focus_rank = 0 if not focus_tokens or any(token in haystack for token in focus_tokens) else 1
        extracted_rank = 0 if _wants_extracted_facts(question) and record.source == EXTRACTED_FACTS_SOURCE_ID else 1
        vectornet_rank = 0 if "vectornet" in q and record.source == "vectornet_aedes_surveillance" else 1
        vectorbyte_abundance_rank = 0 if wants_vectorbyte_abundance and record.source == VECTORBYTE_ABUNDANCE_SOURCE_ID else 1
        return (
            vectorbyte_abundance_rank,
            observation_climate_rank,
            dataverse_rank,
            worldclim_rank,
            compendium_rank,
            focus_rank,
            extracted_rank,
            vectornet_rank,
            0 if record.source == OCCURRENCE_ECOLOGY_SOURCE_ID else 1,
            0 if record.lane == "ecology" else 1,
            record.record_id,
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


def _prioritize_trait_records(question: str, records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    return sorted(
        records,
        key=lambda record: (
            0 if record.source == "aedes_vectorbyte_traits" else 1,
            0 if record.lane == "traits" else 1,
            0 if _record_matches_any_token(record, _trait_focus_tokens(question)) else 1,
        ),
    )


def _trait_focus_tokens(question: str) -> set[str]:
    generic = {
        "aedes",
        "aegypti",
        "data",
        "for",
        "show",
        "temperature",
        "trait",
        "traits",
        "vectorbyte",
        "vectraits",
    }
    return {
        token.lower().strip(".-")
        for token in re.findall(r"[A-Za-z0-9.-]+", question)
        if token.lower().strip(".-") not in generic
    }


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


def _vector_competence_assay_grain_rank(question: str, record: EvidenceRecord) -> int:
    if record.source != "aedes_vector_competence_assays":
        return 3
    if _wants_extracted_facts(question) and record.record_id.startswith("assay_table:vector_competence:"):
        return 0
    if record.record_id.startswith("assay_candidate:vector_competence:"):
        return 1
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
    if _wants_mosquito_repellent_literature(question):
        prefer_external = _wants_mosquito_repellent_external_discovery(question)
        return sorted(
            records,
            key=lambda record: (
                0
                if prefer_external and record.source == MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID
                else 1
                if record.source
                in {MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID, MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID}
                else 2,
                *_mosquito_repellent_external_rank(question, record),
            ),
        )
    if any(
        term in q
        for term in (
            "olfaction",
            "olfactory",
            "odor",
            "odour",
            "odorant",
            "chemosensory",
            "antenna",
            "antennal",
            "orco",
        )
    ) and any(term in q for term in ("paper", "papers", "literature", "study", "studies", "research", "pubmed")):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == AEDES_OLFACTION_LITERATURE_SOURCE_ID else 1,
                0 if record.lane == "literature" else 1,
            ),
        )
    if not any(term in q for term in ("pathogen", "dengue", "zika", "chikungunya", "yellow fever", "mayaro", "west nile")) and any(term in q for term in ("taxonomy", "taxonomic", "synonym", "synonyms", "stegomyia", "mosquito taxonomic inventory", "mti", "wrbu")):
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID else 1,
                0 if record.lane == "taxonomy" else 1,
            ),
        )
    if any(term in q for term in ("worldclim", "global compendium", "compendium")):
        return sorted(
            records,
            key=lambda record: (
                0 if "worldclim" in q and record.source == AEDES_WORLDCLIM_SOURCE_ID else 1,
                0 if "compendium" in q and record.source == AEDES_GLOBAL_COMPENDIUM_SOURCE_ID else 1,
                0 if record.lane in {"ecology", "observations"} else 1,
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
            elif wants_extracted and wants_assay:
                preferred_source = "aedes_vector_competence_assays"
            elif wants_extracted:
                preferred_source = EXTRACTED_FACTS_SOURCE_ID
            elif wants_assay:
                preferred_source = "aedes_vector_competence_assays"
            else:
                preferred_source = "aedes_vector_competence_assays" if record.source == "aedes_vector_competence_assays" else "aedes_pathogen_taxonomy"
            missing_assay_terms = sum(1 for term in assay_terms if term not in haystack)
            return (
                0 if record.source == preferred_source else 1,
                _vector_competence_assay_grain_rank(question, record),
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
    if "figshare" in q:
        return sorted(
            records,
            key=lambda record: (
                0 if record.source == "figshare_aedes_videos" else 1,
                0 if record.lane == "media" else 1,
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


def _source_count(index: SourceIndex, source: str) -> int:
    with index.connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM records WHERE source=?", (source,)).fetchone()[0])


def _source_search_records(index: SourceIndex, source: str, lane: str, query: str, *, limit: int) -> list[EvidenceRecord]:
    terms = [term for term in re.findall(r"[A-Za-z0-9]+", query) if term]
    if not terms:
        return []
    match = " AND ".join(f"{term}*" for term in terms)
    with index.connect() as conn:
        rows = conn.execute(
            """
            SELECT r.*
            FROM records_fts f
            JOIN records r ON r.record_id = f.record_id
            WHERE records_fts MATCH ?
              AND r.source = ?
              AND r.lane = ?
            ORDER BY bm25(records_fts)
            LIMIT ?
            """,
            (match, source, lane, limit),
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


def _vector_competence_assay_records(index: SourceIndex, question: str, *, limit: int) -> list[EvidenceRecord]:
    q = question.lower()
    if not (
        _wants_extracted_facts(question)
        or any(
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
    ):
        return []
    if _wants_extracted_facts(question):
        with index.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*
                FROM records r
                JOIN record_payloads p ON p.record_id = r.record_id
                WHERE r.source = 'aedes_vector_competence_assays'
                  AND r.lane = 'vector_competence'
                  AND json_extract(p.payload_json, '$.confidence') = 'parsed_table_schema_validated'
                ORDER BY r.record_id
                LIMIT ?
                """,
                (max(limit * 50, 250),),
            ).fetchall()
        records = [EvidenceRecord.from_row(dict(row)) for row in rows]
        if records:
            return _prioritize_named_source_records(question, records)[:limit]
    records = _source_search_records(
        index,
        "aedes_vector_competence_assays",
        "vector_competence",
        question,
        limit=max(limit * 20, 50),
    )
    if records:
        return _prioritize_named_source_records(question, records)[:limit]
    return _source_records(index, "aedes_vector_competence_assays", ["vector_competence"], limit=limit)


def _video_atom_records(index: SourceIndex, question: str, lanes: list[str], *, limit: int) -> list[EvidenceRecord]:
    if not lanes:
        return []
    q = question.lower()
    atom_types: list[str]
    if _wants_video_gaps(question):
        atom_types = ["video_sweep", "video_gap"] if (_video_discovery_repository(question) or "repository" in q or "sweep" in q) else ["video_gap"]
    elif _wants_video_discovery(question):
        atom_types = ["video_sweep", "video_asset", "video_gap"]
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
    artifact_atom_types = {"video_keyframe", "video_preview_clip", "video_thumbnail", "video_frame_manifest"}
    repository = _video_discovery_repository(question)
    verified_filter = ""
    if "verified" in q:
        verified_filter = "AND json_extract(p.payload_json, '$.verification_status') = 'verified'"
    motion_metric_order = ""
    gap_reason_order = ""
    wants_license_gap_order = False
    wants_hash_gap_order = False
    if any(term in q for term in ("velocity", "distance moved", "movement", "locomotory")):
        motion_metric_order = """
              CASE WHEN json_extract(p.payload_json, '$.velocity_mean_cm_s') IS NOT NULL THEN 0 ELSE 1 END,
              CASE WHEN json_extract(p.payload_json, '$.distance_moved_total_cm') IS NOT NULL THEN 0 ELSE 1 END,
        """
    if _wants_video_gaps(question):
        gap_reason_order = """
              CASE
                WHEN ? AND json_extract(p.payload_json, '$.reason') = 'video_license_unclear' THEN 0
                WHEN ? AND json_extract(p.payload_json, '$.reason') = 'video_discovery_license_unclear' THEN 1
                WHEN ? AND json_extract(p.payload_json, '$.source_hashes') IS NOT NULL THEN 0
                WHEN ? AND lower(coalesce(r.text, '')) LIKE '%sha-256%' THEN 0
                ELSE 2
              END,
        """
        wants_license_gap_order = "license" in q
        wants_hash_gap_order = any(term in q for term in ("hash", "hashes", "checksum", "sha-256", "sha256"))

    def fetch_rows(selected_atom_types: list[str], selected_limit: int) -> list[sqlite3.Row]:
        lane_placeholders = ",".join("?" for _ in lanes)
        atom_placeholders = ",".join("?" for _ in selected_atom_types)
        repository_filter = ""
        params: list[object] = [*lanes, *selected_atom_types]
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
        if gap_reason_order:
            params.extend([wants_license_gap_order, wants_license_gap_order, wants_hash_gap_order, wants_hash_gap_order])
        params.append(selected_limit)
        with index.connect() as conn:
            return conn.execute(
                f"""
                SELECT r.*
                FROM records r
                JOIN record_payloads p ON p.record_id = r.record_id
                WHERE r.source = 'aedes_video_atoms'
                  AND r.lane IN ({lane_placeholders})
                  AND json_extract(p.payload_json, '$.atom_type') IN ({atom_placeholders})
                  {repository_filter}
                  {verified_filter}
                ORDER BY
                  {motion_metric_order}
                  CASE json_extract(p.payload_json, '$.atom_type')
                    WHEN 'video_sweep' THEN 0
                    WHEN 'video_keyframe' THEN 0
                    WHEN 'video_preview_clip' THEN 1
                    WHEN 'video_thumbnail' THEN 2
                    WHEN 'video_frame_manifest' THEN 3
                    WHEN 'video_asset' THEN 4
                    WHEN 'video_motion_row' THEN 5
                    WHEN 'video_gap' THEN 6
                    ELSE 7
                  END,
                  CASE
                    WHEN json_extract(p.payload_json, '$.verification_status')='verified' THEN 0
                    ELSE 1
                  END,
                  {gap_reason_order}
                  r.record_id
                LIMIT ?
                """,
                params,
            ).fetchall()

    if len(atom_types) > 1 and set(atom_types).issubset(artifact_atom_types):
        buckets = {atom_type: fetch_rows([atom_type], limit) for atom_type in atom_types}
        rows = []
        seen: set[str] = set()
        for offset in range(limit):
            for atom_type in atom_types:
                bucket = buckets[atom_type]
                if offset >= len(bucket):
                    continue
                row = bucket[offset]
                record_id = str(row["record_id"])
                if record_id in seen:
                    continue
                rows.append(row)
                seen.add(record_id)
                if len(rows) >= limit:
                    return [EvidenceRecord.from_row(dict(item)) for item in rows]
        return [EvidenceRecord.from_row(dict(item)) for item in rows]

    rows = fetch_rows(atom_types, limit)
    return [EvidenceRecord.from_row(dict(row)) for row in rows]


def _image_atom_records(index: SourceIndex, question: str, lanes: list[str], *, limit: int) -> list[EvidenceRecord]:
    media_lanes = [lane for lane in lanes if lane == "media"]
    if not media_lanes:
        return []
    q = question.lower()
    if _wants_image_gaps(question):
        atom_types = ["image_gap"]
    elif _wants_image_asset_metadata(question):
        atom_types = ["image_asset"]
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
    source_filter = ""
    if "mosquito alert" in q or "mosquito_alert" in q:
        source_filter = """
              AND (
                json_extract(p.payload_json, '$.source') = 'mosquito_alert_gbif'
                OR json_extract(p.payload_json, '$.input_source') = 'mosquito_alert_gbif'
                OR json_extract(p.payload_json, '$.upstream_source') = 'mosquito_alert_gbif'
              )
        """
    elif "inaturalist" in q or "inat" in q:
        source_filter = """
              AND (
                json_extract(p.payload_json, '$.source') = 'inaturalist_api'
                OR json_extract(p.payload_json, '$.input_source') = 'inaturalist_api'
                OR json_extract(p.payload_json, '$.upstream_source') = 'inaturalist_api'
              )
        """
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
              {source_filter}
            ORDER BY
              CASE
                WHEN json_extract(p.payload_json, '$.verification_status')='verified' THEN 0
                ELSE 1
              END,
              CASE json_extract(p.payload_json, '$.atom_type')
                WHEN 'image_asset' THEN 0
                WHEN 'image_label' THEN 1
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

    named_video_repository = _video_discovery_repository(plan.question) if plan.answer_shape == "media" else None
    if named_video_repository and not all_records:
        source_id = _video_repository_source_id(named_video_repository)
        if source_id:
            for record in _source_records(index, source_id, ["media", "behavior"], limit=limit):
                all_records.append(record)
                seen_record_ids.add(record.record_id)
        if not all_records:
            for record in _video_atom_records(index, f"{plan.question} discovery", list(plan.lanes), limit=limit):
                all_records.append(record)
                seen_record_ids.add(record.record_id)
        if not all_records:
            return source_gap(plan, "The Ask Insects video discovery lane has no matching records for that repository.")

    if plan.answer_shape == "genomics":
        if _wants_snp_variation(plan.question):
            if _source_count(index, NCBI_SNP_VARIATION_SOURCE_ID) == 0:
                return source_gap(plan, "The Ask Insects NCBI dbSNP variation audit lane is not installed in this source index.")
            for record in _source_records(index, NCBI_SNP_VARIATION_SOURCE_ID, ["genome_features"], limit=limit):
                if record.record_id in seen_record_ids:
                    continue
                all_records.append(record)
                seen_record_ids.add(record.record_id)
        uniprot_exact_terms = _uniprot_exact_terms(plan.question)
        uniprot_records = _uniprot_direct_records(index, plan.question, limit=limit)
        if uniprot_exact_terms and not uniprot_records:
            return source_gap(plan, "The Ask Insects UniProt lane has no matching record for the requested accession or identifier.")
        for record in uniprot_records:
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        for record in _vectorbase_auxiliary_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "expression":
        for record in _expression_computed_gap_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "literature" and _wants_olfaction_literature(plan.question):
        if _source_count(index, AEDES_OLFACTION_LITERATURE_SOURCE_ID) == 0:
            return source_gap(plan, "The Ask Insects Aedes olfaction literature audit lane is not installed in this source index.")
        olfaction_records = _source_search_records(
            index,
            AEDES_OLFACTION_LITERATURE_SOURCE_ID,
            "literature",
            plan.search_query,
            limit=max(limit * 20, 50),
        )
        if not olfaction_records:
            olfaction_records = _source_records(index, AEDES_OLFACTION_LITERATURE_SOURCE_ID, ["literature"], limit=limit)
        for record in olfaction_records:
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "literature" and _wants_crossref_literature_audit(plan.question):
        if _source_count(index, AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID) == 0:
            return source_gap(plan, "The Ask Insects Aedes Crossref literature audit lane is not installed in this source index.")
        crossref_records = _source_search_records(
            index,
            AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID,
            "literature",
            plan.search_query,
            limit=max(limit * 20, 50),
        )
        if not crossref_records:
            crossref_records = _source_records(index, AEDES_CROSSREF_LITERATURE_AUDIT_SOURCE_ID, ["literature"], limit=limit)
        for record in crossref_records:
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "literature" and _wants_mosquito_repellent_literature(plan.question):
        if _source_count(index, MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID) == 0:
            return source_gap(plan, "The Ask Insects mosquito repellent literature lane is not installed in this source index.")
        repellent_records = _source_search_records(
            index,
            MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID,
            "literature",
            plan.search_query,
            limit=max(limit * 20, 50),
        )
        if not repellent_records:
            repellent_records = _source_records(index, MOSQUITO_REPELLENT_LITERATURE_SOURCE_ID, ["literature"], limit=limit)
        for record in repellent_records:
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        if _source_count(index, MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID) > 0:
            external_records: list[EvidenceRecord] = []
            preferred_external_lanes = _mosquito_repellent_external_preferred_lanes(plan.question)
            if preferred_external_lanes:
                external_records.extend(
                    _source_records(
                        index,
                        MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
                        preferred_external_lanes,
                        limit=max(limit * 5, 20),
                    )
                )
            for lane in ("literature", "datasets", "patents"):
                external_records.extend(
                    _source_search_records(
                        index,
                        MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
                        lane,
                        plan.search_query,
                        limit=max(limit * 20, 50),
                    )
                )
            if not external_records:
                external_records = _source_records(
                    index,
                    MOSQUITO_REPELLENT_EXTERNAL_DISCOVERY_SOURCE_ID,
                    ["literature", "datasets", "patents"],
                    limit=limit,
                )
            for record in external_records:
                if record.record_id in seen_record_ids:
                    continue
                all_records.append(record)
                seen_record_ids.add(record.record_id)

    if plan.answer_shape == "public_health":
        for record in _opendatasus_surveillance_records(index, plan.question, limit=limit):
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        for record in _ncvbdc_surveillance_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        for record in _who_surveillance_records(index, plan.question, limit=limit):
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        for record in _paho_surveillance_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)
        for record in _cdc_surveillance_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "vector_competence":
        for record in _vector_competence_assay_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "resistance":
        for record in _resistance_table_row_records(index, plan.question, limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "resistance" and any(
        term in plan.question.lower()
        for term in (
            "malaria threats",
            "who database",
            "global database",
            "who resistance database",
            "who insecticide resistance database",
        )
    ):
        for record in _source_records(index, WHO_MALARIA_THREATS_RESISTANCE_SOURCE_ID, ["resistance"], limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "resistance" and any(
        term in plan.question.lower()
        for term in (
            "who",
            "world health organization",
            "guidance",
            "method",
            "methods",
            "bioassay",
            "bioassays",
            "discriminating concentration",
            "discriminating concentrations",
        )
    ):
        for record in _source_records(index, AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID, ["resistance"], limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "identity" and not any(
        term in plan.question.lower() for term in ("pathogen", "dengue", "zika", "chikungunya", "yellow fever", "mayaro", "west nile")
    ) and any(
        term in plan.question.lower() for term in ("taxonomy", "taxonomic", "synonym", "synonyms", "stegomyia", "mosquito taxonomic inventory", "mti", "wrbu")
    ):
        for record in _source_records(index, AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID, ["taxonomy"], limit=limit):
            if record.record_id in seen_record_ids:
                continue
            all_records.append(record)
            seen_record_ids.add(record.record_id)

    if plan.answer_shape == "ecology":
        q = plan.question.lower()
        if "source-grade" in q or ("evidence" in q and "ecology" in q):
            for source_id in (
                OCCURRENCE_ECOLOGY_SOURCE_ID,
                OBSERVATION_CLIMATE_SOURCE_ID,
                AEDES_WORLDCLIM_SOURCE_ID,
                HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID,
                VECTORBYTE_ABUNDANCE_SOURCE_ID,
                "vectornet_aedes_surveillance",
            ):
                for record in _source_records(index, source_id, ["ecology"], limit=limit):
                    if record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
        if _wants_vectorbyte_abundance(plan.question):
            for lane in ("observations", "ecology"):
                for record in _source_records(index, VECTORBYTE_ABUNDANCE_SOURCE_ID, [lane], limit=max(limit * 10, 25)):
                    if record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
        if any(term in q for term in ("climate-linked", "climate linked", "climate join", "observation climate", "bioclim", "joined")) and any(
            term in q for term in ("observation", "observations", "occurrence", "country", "coordinates", "temperature", "precipitation")
        ):
            matched_observation_climate = False
            for search_query in _search_queries(plan.question):
                query_records = index.search(search_query, lane="ecology", limit=max(limit * 20, 50))
                for record in query_records:
                    if record.source != OBSERVATION_CLIMATE_SOURCE_ID or record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
                    matched_observation_climate = True
                    if len([item for item in all_records if item.source == OBSERVATION_CLIMATE_SOURCE_ID]) >= limit:
                        break
            if not matched_observation_climate:
                for record in _source_records(index, OBSERVATION_CLIMATE_SOURCE_ID, ["ecology"], limit=limit):
                    if record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
        if any(term in q for term in ("dataverse", "suitability", "transmission risk", "dengue transmission")):
            matched_dataverse = False
            for search_query in (f"Harvard Dataverse {plan.question}", f"Aedes aegypti suitability {plan.question}", plan.question):
                query_records = index.search(search_query, lane="ecology", limit=max(limit * 20, 50))
                for record in query_records:
                    if record.source != HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID or record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
                    matched_dataverse = True
                    if len([item for item in all_records if item.source == HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID]) >= limit:
                        break
                if matched_dataverse:
                    break
            if not matched_dataverse:
                for record in _source_records(index, HARVARD_DATAVERSE_SUITABILITY_SOURCE_ID, ["ecology"], limit=limit):
                    if record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
        if any(term in q for term in ("worldclim", "climate", "precipitation", "temperature", "suitability")):
            matched_worldclim = False
            focus_query = " ".join(
                token
                for token in re.findall(r"[A-Za-z0-9]+", plan.question)
                if token.lower()
                not in {
                    "aedes",
                    "aegypti",
                    "and",
                    "annual",
                    "climate",
                    "for",
                    "mean",
                    "precipitation",
                    "sample",
                    "samples",
                    "show",
                    "temperature",
                    "the",
                    "worldclim",
                }
            )
            search_queries = [f"WorldClim {focus_query}".strip()] if focus_query else []
            search_queries.extend([f"WorldClim {plan.question}", plan.question])
            for search_query in search_queries:
                query_records = index.search(search_query, lane="ecology", limit=max(limit * 20, 50))
                for record in query_records:
                    if record.source != AEDES_WORLDCLIM_SOURCE_ID or record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
                    matched_worldclim = True
                    if len([item for item in all_records if item.source == AEDES_WORLDCLIM_SOURCE_ID]) >= limit:
                        break
                if matched_worldclim:
                    break
            if not matched_worldclim:
                for record in _source_records(index, AEDES_WORLDCLIM_SOURCE_ID, ["ecology"], limit=limit):
                    if record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
        if any(term in q for term in ("global compendium", "compendium", "occurrence compendium")):
            matched_compendium = False
            for search_query in _search_queries(plan.question):
                query_records = index.search(search_query, lane="observations", limit=max(limit * 20, 50))
                for record in query_records:
                    if record.source != AEDES_GLOBAL_COMPENDIUM_SOURCE_ID or record.record_id in seen_record_ids:
                        continue
                    all_records.append(record)
                    seen_record_ids.add(record.record_id)
                    matched_compendium = True
                    if len([item for item in all_records if item.source == AEDES_GLOBAL_COMPENDIUM_SOURCE_ID]) >= limit:
                        break
                if matched_compendium:
                    break
            if not matched_compendium:
                for record in _source_records(index, AEDES_GLOBAL_COMPENDIUM_SOURCE_ID, ["observations"], limit=limit):
                    if record.record_id in seen_record_ids:
                        continue
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
        if _wants_video_gaps(plan.question) or _wants_video_discovery(plan.question) or named_video_repository:
            media_records = [
                record
                for record in all_records
                if record.lane == "media"
                and (record.media_url or any(term in f"{record.title} {record.text}".lower() for term in ("video gap", "video discovery sweep")))
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
        if _wants_literature_fulltext(plan.question):
            literature_records = _fulltext_literature_records(index, plan.question, limit=limit)
        elif _wants_mosquito_repellent_literature(plan.question):
            literature_records = [record for record in all_records if record.lane in {"literature", "datasets", "patents"}]
        else:
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

    if plan.answer_shape == "expression":
        all_records = _prioritize_expression_records(plan.question, all_records)

    if plan.answer_shape == "neurobiology":
        all_records = _prioritize_neurobiology_records(plan.question, all_records)

    if plan.answer_shape == "resistance":
        all_records = _prioritize_resistance_records(plan.question, all_records)

    if plan.answer_shape == "behavior":
        all_records = _prioritize_behavior_records(plan.question, all_records)

    if plan.answer_shape == "traits":
        all_records = _prioritize_trait_records(plan.question, all_records)

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
