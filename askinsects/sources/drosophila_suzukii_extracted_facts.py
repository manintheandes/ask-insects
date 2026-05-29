from __future__ import annotations

from askinsects.sources.extracted_facts import ExtractedFactsProfile, FactFamily


DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID = "drosophila_suzukii_extracted_facts"
INPUT_DROSOPHILA_SUZUKII_LITERATURE_SOURCE_ID = "drosophila_suzukii_core"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"


DROSOPHILA_SUZUKII_FACT_FAMILIES: tuple[FactFamily, ...] = (
    FactFamily(
        fact_type="behavior",
        lane="behavior",
        context_terms=(
            "behavior",
            "behaviour",
            "oviposition",
            "host preference",
            "choice assay",
            "attraction",
            "avoidance",
            "flight",
            "locomotor",
            "feeding",
            "mating",
            "trap",
        ),
        field_terms={
            "behavior_type": ("oviposition", "host preference", "attraction", "avoidance", "flight", "feeding", "mating"),
            "assay": ("choice assay", "bioassay", "olfactometer", "trap", "arena", "cage", "field trial"),
            "stimulus": ("fruit", "odor", "yeast", "sugar", "vinegar", "volatile", "cue", "stimulus"),
            "life_stage": ("adult", "larva", "larvae", "pupa", "female", "male"),
            "response_metric": ("preference", "landing", "visit", "count", "eggs", "oviposition rate", "duration"),
        },
    ),
    FactFamily(
        fact_type="crop_damage",
        lane="crop_damage",
        context_terms=(
            "crop damage",
            "damage",
            "infestation",
            "fruit damage",
            "host fruit",
            "berry",
            "cherry",
            "blueberry",
            "raspberry",
            "strawberry",
            "wine grape",
        ),
        field_terms={
            "host_crop": ("cherry", "blueberry", "raspberry", "strawberry", "blackberry", "grape", "peach", "plum", "berry"),
            "damage_metric": ("damage", "infestation", "infested", "larvae per fruit", "percent infested", "yield loss"),
            "life_stage": ("egg", "larva", "larvae", "adult"),
            "location": ("field", "orchard", "vineyard", "farm", "crop"),
        },
    ),
    FactFamily(
        fact_type="management",
        lane="management",
        context_terms=(
            "management",
            "control",
            "monitoring",
            "trap",
            "bait",
            "sanitation",
            "exclusion netting",
            "mass trapping",
            "attract and kill",
            "insecticide",
        ),
        field_terms={
            "control_method": ("sanitation", "netting", "mass trapping", "bait", "attract and kill", "spray", "insecticide", "biocontrol"),
            "monitoring": ("trap", "lure", "bait", "monitoring", "threshold"),
            "efficacy_metric": ("reduction", "mortality", "capture", "infestation", "control", "efficacy"),
            "crop_context": ("cherry", "blueberry", "raspberry", "strawberry", "berry", "grape", "orchard", "vineyard"),
        },
    ),
    FactFamily(
        fact_type="resistance",
        lane="resistance",
        context_terms=(
            "resistance",
            "insecticide resistance",
            "susceptibility",
            "mortality",
            "lc50",
            "knockdown",
            "spinosad",
            "pyrethroid",
            "malathion",
        ),
        field_terms={
            "insecticide": ("spinosad", "pyrethroid", "malathion", "acetamiprid", "lambda-cyhalothrin", "zeta-cypermethrin"),
            "assay": ("bioassay", "dose response", "exposure", "diagnostic dose", "vial assay"),
            "response_metric": ("mortality", "lc50", "ld50", "knockdown", "survival", "resistance ratio"),
            "population": ("field population", "strain", "colony", "population"),
        },
    ),
    FactFamily(
        fact_type="biocontrol",
        lane="biocontrol",
        context_terms=(
            "biological control",
            "biocontrol",
            "parasitoid",
            "predator",
            "pathogen",
            "entomopathogenic",
            "ganaspis",
            "pachycrepoideus",
            "trichopria",
            "leptopilina",
        ),
        field_terms={
            "agent": ("parasitoid", "ganaspis", "pachycrepoideus", "trichopria", "leptopilina", "predator", "pathogen"),
            "target_stage": ("egg", "larva", "larvae", "pupa", "adult"),
            "effect_metric": ("parasitism", "mortality", "emergence", "attack rate", "suppression"),
            "assay": ("choice assay", "no-choice", "field release", "laboratory", "cage"),
        },
    ),
    FactFamily(
        fact_type="ecology",
        lane="ecology",
        context_terms=(
            "ecology",
            "distribution",
            "range",
            "phenology",
            "seasonality",
            "climate",
            "temperature",
            "overwintering",
            "landscape",
        ),
        field_terms={
            "distribution": ("distribution", "range", "spread", "invasion", "occurrence"),
            "seasonality": ("season", "phenology", "overwintering", "spring", "summer", "autumn", "winter"),
            "climate": ("temperature", "humidity", "climate", "degree-day", "thermal"),
            "habitat": ("forest", "orchard", "vineyard", "hedgerow", "wild host", "crop"),
            "sampling": ("trap", "survey", "monitoring", "capture", "collection"),
        },
    ),
    FactFamily(
        fact_type="genomics",
        lane="genomics",
        context_terms=(
            "genome",
            "transcriptome",
            "rna-seq",
            "rnaseq",
            "gene expression",
            "protein",
            "proteome",
            "assembly",
            "annotation",
        ),
        field_terms={
            "data_type": ("genome", "transcriptome", "rna-seq", "gene expression", "proteome", "protein", "assembly"),
            "accession": ("bioproject", "biosample", "sra", "genbank", "ncbi", "uniprot"),
            "method": ("sequencing", "assembly", "annotation", "differential expression", "proteomics"),
            "tissue_or_stage": ("adult", "larva", "larvae", "antenna", "ovary", "male", "female"),
        },
    ),
)


DROSOPHILA_SUZUKII_EXTRACTED_FACTS_PROFILE = ExtractedFactsProfile(
    source_id=DROSOPHILA_SUZUKII_EXTRACTED_FACTS_SOURCE_ID,
    input_literature_source_id=INPUT_DROSOPHILA_SUZUKII_LITERATURE_SOURCE_ID,
    species_name=SPECIES,
    label=f"{SPECIES} ({COMMON_NAME})",
    record_prefix="swd_extracted_fact",
    raw_subdir="drosophila_suzukii_extracted_facts",
    fact_families=DROSOPHILA_SUZUKII_FACT_FAMILIES,
)
