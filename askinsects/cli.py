from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR
from .hosted import CONFIG_PATH as HOSTED_CONFIG_PATH
from .hosted import HostedConfig, hosted_request, load_config, save_config
from .index import SourceIndex
from .voxels import read_voxel_value


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def cli_error(error: str, *, lane: str, artifact_dir: Path) -> dict[str, object]:
    return {
        "ok": False,
        "error": error,
        "answer": error,
        "evidence": [],
        "source_gap": {
            "lane": lane,
            "reason": f"The mosquito_v1 source index is missing or unavailable for lane '{lane}'.",
            "artifact_dir": artifact_dir.as_posix(),
        },
    }


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


def normalize_search_lane(lane: str) -> str:
    if lane == "papers":
        return "literature"
    return lane


def indexed_sources(artifact_dir: Path) -> list[str]:
    status_path = artifact_dir / "source_status.json"
    if not status_path.exists():
        return ["mosquito_v1_fixtures"]
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["mosquito_v1_fixtures"]
    sources = payload.get("sources")
    if isinstance(sources, list) and all(isinstance(source, str) for source in sources):
        return sources
    source_id = payload.get("source_id")
    if isinstance(source_id, str):
        return [source_id]
    return ["mosquito_v1_fixtures"]


def emit_hosted(method: str, path: str, payload: dict[str, object] | None = None, *, timeout: int = 120) -> dict[str, object]:
    result = hosted_request(load_config(), method, path, payload, timeout=timeout)
    emit(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask-insects")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    configure = sub.add_parser("configure")
    configure.add_argument("--url", required=True)
    configure.add_argument("--token", required=True)

    health = sub.add_parser("health")
    health.add_argument("--hosted", action="store_true")

    summary = sub.add_parser("summary")
    summary.add_argument("--hosted", action="store_true")

    sources = sub.add_parser("sources")
    sources.add_argument("--hosted", action="store_true")

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=5)
    ask.add_argument("--json", action="store_true")
    ask.add_argument("--hosted", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("lane")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--hosted", action="store_true")

    sql = sub.add_parser("sql")
    sql.add_argument("sql")
    sql.add_argument("--limit", type=int, default=100)
    sql.add_argument("--hosted", action="store_true")

    voxel = sub.add_parser("voxel")
    voxel.add_argument("record_id")
    voxel.add_argument("--x", type=int, required=True)
    voxel.add_argument("--y", type=int, required=True)
    voxel.add_argument("--z", type=int, required=True)

    ingest_inaturalist = sub.add_parser("ingest-inaturalist")
    ingest_inaturalist.add_argument("--hosted", action="store_true")
    ingest_inaturalist.add_argument("--species", action="append", default=[])
    ingest_inaturalist.add_argument("--place")
    ingest_inaturalist.add_argument("--observation-limit", type=int, default=10)
    ingest_inaturalist.add_argument("--page-size", type=int, default=200)
    ingest_inaturalist.add_argument("--delay-seconds", type=float, default=0.0)

    ingest_gbif = sub.add_parser("ingest-gbif")
    ingest_gbif.add_argument("--hosted", action="store_true")
    ingest_gbif.add_argument("--species", action="append", default=[])
    ingest_gbif.add_argument("--occurrence-limit", type=int, default=3)
    ingest_gbif.add_argument("--occurrence-page-size", type=int, default=300)
    ingest_gbif.add_argument("--occurrence-workers", type=int, default=1)
    ingest_gbif.add_argument("--delay-seconds", type=float, default=0.0)

    ingest_irmapper = sub.add_parser("ingest-irmapper")
    ingest_irmapper.add_argument("--hosted", action="store_true")
    ingest_irmapper.add_argument("--species", default="Aedes aegypti")

    args = parser.parse_args(argv)
    artifact_dir = Path(args.artifact_dir)
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    db_path = artifact_dir / "source_index.sqlite"

    if args.command == "configure":
        save_config(HostedConfig(url=args.url, token=args.token), path=HOSTED_CONFIG_PATH)
        emit({"ok": True, "config_path": HOSTED_CONFIG_PATH.as_posix(), "url": args.url})
        return 0
    if args.command == "health":
        if args.hosted:
            payload = emit_hosted("GET", "/health")
            return 0 if payload.get("ok") else 2
        db_exists = db_path.exists()
        status_exists = (artifact_dir / "source_status.json").exists()
        emit({"ok": db_exists and status_exists, "db_exists": db_exists, "status_exists": status_exists})
        return 0
    if args.command == "summary":
        if args.hosted:
            payload = emit_hosted("GET", "/summary")
            return 0 if payload.get("ok", True) is not False else 2
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane="mosquito_v1", artifact_dir=artifact_dir))
            return 2
        try:
            emit(index.summary())
        except sqlite3.Error as exc:
            emit(cli_error(str(exc), lane="mosquito_v1", artifact_dir=artifact_dir))
            return 2
        return 0
    if args.command == "sources":
        if args.hosted:
            payload = emit_hosted("GET", "/sources")
            return 0 if payload.get("ok", True) is not False else 2
        emit({"sources": indexed_sources(artifact_dir), "artifact_dir": artifact_dir.as_posix()})
        return 0
    if args.command == "ask":
        if args.hosted:
            payload = hosted_request(load_config(), "POST", "/ask", {"question": args.question, "limit": args.limit})
        else:
            try:
                payload = answer_question(args.question, artifact_dir=artifact_dir, limit=args.limit)
            except sqlite3.Error as exc:
                payload = cli_error(str(exc), lane="mosquito_v1", artifact_dir=artifact_dir)
            gap = payload.get("source_gap") or {}
            if not payload.get("ok") and isinstance(gap, dict) and "index has not been built" in str(gap.get("reason")):
                payload = cli_error(
                    "missing mosquito_v1 source index",
                    lane=str(gap.get("lane", "mosquito_v1")),
                    artifact_dir=artifact_dir,
                )
        if args.json:
            emit(payload)
        elif args.hosted and "answer" not in payload:
            emit(payload)
        else:
            print(render_answer(payload))
        return 0 if payload.get("ok") else 2
    if args.command == "search":
        if args.hosted:
            payload = emit_hosted("POST", "/search", {"lane": normalize_search_lane(args.lane), "query": args.query, "limit": args.limit})
            return 0 if payload.get("ok") else 2
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane=args.lane, artifact_dir=artifact_dir))
            return 2
        lane = normalize_search_lane(args.lane)
        try:
            rows = [record.to_row() for record in index.search(args.query, lane=lane, limit=args.limit)]
        except sqlite3.Error as exc:
            emit(cli_error(str(exc), lane=args.lane, artifact_dir=artifact_dir))
            return 2
        emit({"ok": True, "rows": rows})
        return 0
    if args.command == "sql":
        if args.hosted:
            payload = emit_hosted("POST", "/sql", {"sql": args.sql, "limit": args.limit})
            return 0 if payload.get("ok") else 2
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane="sql", artifact_dir=artifact_dir))
            return 2
        try:
            emit({"ok": True, "rows": index.sql(args.sql, limit=args.limit)})
        except (sqlite3.Error, ValueError) as exc:
            emit(cli_error(str(exc), lane="sql", artifact_dir=artifact_dir))
            return 2
        return 0
    if args.command == "voxel":
        if not db_path.exists():
            emit(cli_error("missing mosquito_v1 source index", lane="neurobiology", artifact_dir=artifact_dir))
            return 2
        try:
            emit(read_voxel_value(index_path=db_path, record_id=args.record_id, x=args.x, y=args.y, z=args.z))
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            emit(cli_error(str(exc), lane="neurobiology", artifact_dir=artifact_dir))
            return 2
        return 0
    if args.command == "ingest-inaturalist":
        if not args.hosted:
            from scripts.ingest_inaturalist_observations import ingest_inaturalist_observations

            payload = ingest_inaturalist_observations(
                artifact_dir=artifact_dir,
                species=args.species or ["Aedes aegypti"],
                place=args.place,
                observation_limit=args.observation_limit,
                page_size=args.page_size,
                delay_seconds=args.delay_seconds,
            )
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/inaturalist",
            {
                "species": args.species or ["Aedes aegypti"],
                "place": args.place,
                "observation_limit": args.observation_limit,
                "page_size": args.page_size,
                "delay_seconds": args.delay_seconds,
            },
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-gbif":
        if not args.hosted:
            emit({"ok": False, "error": "ingest-gbif currently requires --hosted; use scripts/build_source_index.py for local ingest"})
            return 2
        payload = emit_hosted(
            "POST",
            "/ingest/gbif",
            {
                "species": args.species or ["Aedes aegypti"],
                "occurrence_limit": args.occurrence_limit,
                "occurrence_page_size": args.occurrence_page_size,
                "occurrence_workers": args.occurrence_workers,
                "delay_seconds": args.delay_seconds,
            },
            timeout=7200,
        )
        return 0 if payload.get("ok") else 2
    if args.command == "ingest-irmapper":
        if not args.hosted:
            from scripts.ingest_irmapper import ingest_irmapper

            payload = ingest_irmapper(artifact_dir=artifact_dir, species=args.species)
            emit(payload)
            return 0 if payload.get("ok") else 2
        payload = emit_hosted(
            "POST",
            "/ingest/irmapper",
            {"species": args.species},
            timeout=3600,
        )
        return 0 if payload.get("ok") else 2
    parser.error("unknown command")
    return 1
