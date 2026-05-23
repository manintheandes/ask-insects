from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex
from .planner import QueryPlan, plan_question
from .records import EvidenceRecord


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
        "answer": f"I do not see enough indexed mosquito evidence for this question yet. {reason}",
        "evidence": [],
        "source_gap": {
            "lane": lane,
            "reason": reason,
            "checked_lanes": list(plan.lanes),
        },
    }


def _answer_text(plan: QueryPlan, records: list[EvidenceRecord]) -> str:
    if plan.answer_shape == "identity":
        return f"From the local mosquito index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "evidence":
        return f"I found {len(records)} indexed mosquito evidence record(s) matching the question."
    if plan.answer_shape == "action":
        return f"The local mosquito index supports this next step: {records[0].text}"
    if plan.answer_shape == "literature":
        return f"From the local mosquito literature index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "media":
        return f"I found {len(records)} indexed mosquito media record(s)."
    return f"I found {len(records)} indexed mosquito record(s)."


def _search_queries(question: str) -> list[str]:
    queries = [question]
    species_match = re.search(r"\b(Aedes|Culex|Anopheles)\s+[a-z]+\b", question, flags=re.IGNORECASE)
    if species_match:
        queries.append(species_match.group(0))
    if "host seeking" in question.lower():
        queries.append("host seeking")
    for term in ("Brazil", "mosquito"):
        if term.lower() in question.lower():
            queries.append(term)
    return list(dict.fromkeys(queries))


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
        return source_gap(plan, "The mosquito V1 source index has not been built yet.")

    all_records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()
    for lane in plan.lanes:
        for search_query in _search_queries(plan.search_query):
            query_records = index.search(search_query, lane=lane, limit=limit)
            for record in query_records:
                if record.record_id in seen_record_ids:
                    continue
                all_records.append(record)
                seen_record_ids.add(record.record_id)
            if query_records:
                break

    if plan.answer_shape == "media":
        media_records = [record for record in all_records if record.media_url and record.lane == "media"]
        if not media_records:
            return source_gap(plan, "The mosquito V1 index has no matching moving-image media records.")
        all_records = media_records

    if not all_records:
        return source_gap(plan, "No matching local records were found in the checked lanes.")

    evidence = [record_to_evidence(record) for record in all_records[:limit]]
    return {
        "ok": True,
        "answer_shape": plan.answer_shape,
        "answer": _answer_text(plan, all_records),
        "evidence": evidence,
        "source_gap": None,
    }
