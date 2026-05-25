from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    question: str
    answer_shape: str
    lanes: tuple[str, ...]
    search_query: str


def plan_question(question: str) -> QueryPlan:
    q = question.lower()
    video_motion_terms = (
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
    )
    if any(term in q for term in video_motion_terms):
        return QueryPlan(question, "behavior", ("behavior", "media"), question)
    video_media_terms = (
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
        "gap",
        "gaps",
        "failed",
        "failure",
        "discovery",
    )
    if any(term in q for term in video_media_terms):
        return QueryPlan(question, "media", ("media",), question)
    if any(term in q for term in ("paper", "papers", "literature", "study", "studies", "research")):
        return QueryPlan(question, "literature", ("literature", "taxonomy", "observations"), question)
    if any(
        term in q
        for term in (
            "public health",
            "guidance",
            "guidelines",
            "prevention",
            "prevent",
            "recommendation",
            "recommendations",
            "fact sheet",
            "factsheet",
            "surveillance",
            "outbreak",
            "vector control",
            "intervention",
            "incidence",
            "epidemic",
            "paho",
            "plisa",
            "cdc",
            "ecdc",
            "world health organization",
            "case fatality",
            "cases",
            "deaths",
        )
    ):
        return QueryPlan(question, "public_health", ("public_health", "observations", "literature", "taxonomy"), question)
    if any(
        term in q
        for term in (
            "vector competence",
            "transmission competence",
            "vector competence assay",
            "assay context",
            "infection rate",
            "dissemination rate",
            "transmission rate",
            "dose",
            "midgut",
            "saliva",
            "salivary gland",
            "extrinsic incubation",
            "pathogen",
            "pathogens",
            "dengue",
            "zika",
            "chikungunya",
            "yellow fever",
        )
    ):
        return QueryPlan(question, "vector_competence", ("vector_competence", "literature", "taxonomy"), question)
    if any(
        term in q
        for term in (
            "insecticide resistance",
            "pyrethroid resistance",
            "metabolic resistance",
            "resistance marker",
            "resistance markers",
            "kdr",
            "knockdown resistance",
            "susceptibility",
            "bioassay",
            "resistance mutation",
            "vgsc",
            "vssc",
        )
    ):
        return QueryPlan(question, "resistance", ("resistance", "genes", "proteins", "literature", "taxonomy"), question)
    if any(
        term in q
        for term in (
            "mendeley",
            "osf",
            "flighttrackai",
            "flight tracking",
            "behavior",
            "host seeking",
            "host-seeking",
            "blood feeding",
            "biting behavior",
            "oviposition",
            "mating",
            "mate recognition",
            "wing flash",
            "flight tone",
            "flight tones",
            "wingbeat",
            "hearing",
            "locomotory",
            "temperature gradient",
            "temperature gradients",
            "temperature regime",
            "response rate",
            "supplement table",
            "supplementary table",
            "larval behavior",
            "repellent",
            "attractant",
        )
    ):
        return QueryPlan(question, "behavior", ("behavior", "neurobiology", "literature", "taxonomy"), question)
    if any(
        term in q
        for term in (
            "larval habitat",
            "breeding site",
            "ecology",
            "climate",
            "rainfall",
            "seasonality",
            "seasonal",
            "range",
            "distribution",
            "where",
            "country",
            "countries",
            "month",
            "monthly",
            "environmental suitability",
            "land use",
        )
    ):
        return QueryPlan(question, "ecology", ("ecology", "observations", "literature", "taxonomy"), question)
    neurobiology_terms = (
        "brain",
        "brains",
        "neuron",
        "neurons",
        "neural",
        "neurobiology",
        "neuroanatomy",
        "glia",
        "antennal lobe",
        "mushroom body",
        "connectome",
        "single-nucleus",
        "single nucleus",
        "snrna",
        "snrna-seq",
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
        "olfactory sensory neuron",
        "olfactory sensory neurons",
    )
    if any(term in q for term in neurobiology_terms):
        return QueryPlan(
            question,
            "neurobiology",
            ("neurobiology", "proteins", "transcripts", "genes", "literature", "taxonomy"),
            question,
        )
    genomics_terms = (
        "aael",
        "assembly",
        "barcode",
        "barcodes",
        "bold",
        "coi",
        "coi-5p",
        "codon",
        "codons",
        "codon usage",
        "dna barcode",
        "dna barcodes",
        "genome",
        "gene",
        "genes",
        "biosample",
        "biosamples",
        "sample",
        "samples",
        "strain",
        "strains",
        "isolate",
        "isolates",
        "sra",
        "transcript",
        "transcript sequence",
        "transcripts",
        "cds",
        "coding sequence",
        "coding sequences",
        "go annotation",
        "go term",
        "gene ontology",
        "id event",
        "id events",
        "identifier event",
        "identifier history",
        "linkout",
        "ncbi linkout",
        "protein",
        "proteins",
        "receptor",
        "receptors",
        "odorant",
        "gustatory",
        "ionotropic",
        "orco",
        "cytochrome p450",
        "sodium channel",
        "insecticide resistance",
        "vectorbase",
        "veupathdb",
    )
    if any(term in q for term in genomics_terms):
        if any(term in q for term in ("barcode", "barcodes", "bold", "coi", "coi-5p")):
            lanes = ("dna_barcodes", "genes", "proteins", "literature", "taxonomy")
        elif any(
            term in q
            for term in (
                "codon",
                "codons",
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
            lanes = ("genome_features", "genes", "proteins", "transcripts", "genome_assemblies", "literature", "taxonomy")
        elif any(term in q for term in ("receptor", "receptors", "odorant", "gustatory", "ionotropic", "orco")):
            lanes = ("proteins", "transcripts", "genome_features", "genes", "genome_assemblies", "literature", "taxonomy")
        elif any(term in q for term in ("biosample", "biosamples", "sample", "samples", "strain", "strains", "isolate", "isolates", "sra")):
            lanes = ("biosamples", "genome_assemblies", "genes", "transcripts", "proteins", "literature", "taxonomy")
        elif "assembly" in q or "genome" in q:
            lanes = ("genome_assemblies", "genes", "transcripts", "proteins", "genome_features", "literature", "taxonomy")
        else:
            lanes = ("genes", "proteins", "transcripts", "genome_features", "genome_assemblies", "literature", "taxonomy")
        return QueryPlan(
            question,
            "genomics",
            lanes,
            question,
        )
    if "what should" in q or "inspect next" in q or "take action" in q or "next step" in q:
        return QueryPlan(question, "action", ("action_notes", "literature", "observations"), question)
    if "observation" in q or "image" in q or "photo" in q or "show" in q:
        return QueryPlan(question, "evidence", ("observations", "media", "literature"), question)
    return QueryPlan(question, "identity", ("taxonomy", "literature", "observations"), question)
