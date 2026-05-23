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
    if any(term in q for term in ("paper", "papers", "literature", "study", "studies", "research")):
        return QueryPlan(question, "literature", ("literature", "taxonomy", "observations"), question)
    if "what should" in q or "inspect next" in q or "take action" in q or "next step" in q:
        return QueryPlan(question, "action", ("action_notes", "literature", "observations"), question)
    if "observation" in q or "image" in q or "photo" in q or "show" in q:
        return QueryPlan(question, "evidence", ("observations", "media", "literature"), question)
    return QueryPlan(question, "identity", ("taxonomy", "literature", "observations"), question)
