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
    if "video" in q or "moving" in q:
        return QueryPlan(question, "media", ("media",), question)
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
        "cell atlas",
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
        "assembly",
        "genome",
        "gene",
        "genes",
        "transcript",
        "transcripts",
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
    )
    if any(term in q for term in genomics_terms):
        if any(term in q for term in ("receptor", "receptors", "odorant", "gustatory", "ionotropic", "orco")):
            lanes = ("proteins", "transcripts", "genome_features", "genes", "genome_assemblies", "literature", "taxonomy")
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
    if any(term in q for term in ("paper", "papers", "literature", "study", "studies", "research")):
        return QueryPlan(question, "literature", ("literature", "taxonomy", "observations"), question)
    if "what should" in q or "inspect next" in q or "take action" in q or "next step" in q:
        return QueryPlan(question, "action", ("action_notes", "literature", "observations"), question)
    if "observation" in q or "image" in q or "photo" in q or "show" in q:
        return QueryPlan(question, "evidence", ("observations", "media", "literature"), question)
    return QueryPlan(question, "identity", ("taxonomy", "literature", "observations"), question)
