from __future__ import annotations

import argparse
import json
from pathlib import Path

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def render_answer(payload: dict[str, object]) -> str:
    lines = [str(payload["answer"]), ""]
    evidence = payload.get("evidence") or []
    if evidence:
        lines.append("Evidence:")
        for item in evidence:
            provenance = item["provenance"]
            lines.append(f"- {item['title']} [{item['source']} {item['record_id']}]")
            lines.append(f"  locator: {provenance['locator']}")
    gap = payload.get("source_gap")
    if gap:
        lines.append("Source gap:")
        lines.append(f"- lane: {gap['lane']}")
        lines.append(f"- reason: {gap['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask-insects")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("summary")
    sub.add_parser("sources")

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=5)
    ask.add_argument("--json", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("lane")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    sql = sub.add_parser("sql")
    sql.add_argument("sql")
    sql.add_argument("--limit", type=int, default=100)

    args = parser.parse_args(argv)
    artifact_dir = Path(args.artifact_dir)
    index = SourceIndex(artifact_dir / "source_index.sqlite")

    if args.command == "health":
        db_exists = (artifact_dir / "source_index.sqlite").exists()
        status_exists = (artifact_dir / "source_status.json").exists()
        emit({"ok": db_exists and status_exists, "db_exists": db_exists, "status_exists": status_exists})
        return 0
    if args.command == "summary":
        emit(index.summary())
        return 0
    if args.command == "sources":
        emit({"sources": ["mosquito_v1_fixtures"], "artifact_dir": artifact_dir.as_posix()})
        return 0
    if args.command == "ask":
        payload = answer_question(args.question, artifact_dir=artifact_dir, limit=args.limit)
        if args.json:
            emit(payload)
        else:
            print(render_answer(payload))
        return 0 if payload.get("ok") else 2
    if args.command == "search":
        rows = [record.to_row() for record in index.search(args.query, lane=args.lane, limit=args.limit)]
        emit({"ok": True, "rows": rows})
        return 0
    if args.command == "sql":
        emit({"ok": True, "rows": index.sql(args.sql, limit=args.limit)})
        return 0
    parser.error("unknown command")
    return 1
