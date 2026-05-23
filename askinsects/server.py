from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Callable

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR, build_source_index
from .index import SourceIndex


@dataclass(frozen=True)
class Response:
    status: int
    payload: dict[str, object]


def json_response(status: int, payload: dict[str, object]) -> Response:
    return Response(status=status, payload=payload)


def is_authorized(headers: object, token: str) -> bool:
    if not token:
        return False
    auth = headers.get("Authorization") if hasattr(headers, "get") else None
    return auth == f"Bearer {token}"


def read_sources(artifact_dir: Path) -> list[str]:
    status_path = artifact_dir / "source_status.json"
    if not status_path.exists():
        return []
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    sources = payload.get("sources")
    if isinstance(sources, list) and all(isinstance(source, str) for source in sources):
        return sources
    source_id = payload.get("source_id")
    if isinstance(source_id, str):
        return [source_id]
    return []


def health_payload(artifact_dir: Path) -> dict[str, object]:
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    payload: dict[str, object] = {
        "ok": db_path.exists() and status_path.exists(),
        "db_exists": db_path.exists(),
        "status_exists": status_path.exists(),
        "db_path": str(db_path),
        "artifact_dir": str(artifact_dir),
        "sources": read_sources(artifact_dir),
    }
    if db_path.exists():
        try:
            payload.update(SourceIndex(db_path).summary())
        except sqlite3.Error as exc:
            payload["ok"] = False
            payload["error"] = str(exc)
    return payload


def activate_staging_artifact(staging: Path, artifact_dir: Path) -> None:
    backup = artifact_dir.parent / f".{artifact_dir.name}.previous"
    if backup.exists():
        shutil.rmtree(backup)
    if artifact_dir.exists():
        artifact_dir.replace(backup)
    staging.replace(artifact_dir)
    if backup.exists():
        shutil.rmtree(backup)


def ingest_inaturalist(
    payload: dict[str, object],
    *,
    artifact_dir: Path,
    build_source_index_fn: Callable[..., dict[str, object]],
) -> dict[str, object]:
    species_value = payload.get("species") or ["Aedes aegypti"]
    if isinstance(species_value, str):
        species = [species_value]
    elif isinstance(species_value, list) and all(isinstance(item, str) for item in species_value):
        species = species_value
    else:
        raise ValueError("species must be a string or list of strings")

    observation_limit = int(payload.get("observation_limit", 10))
    page_size = int(payload.get("page_size", 200))
    delay_seconds = float(payload.get("delay_seconds", 0))
    place = payload.get("place")
    if place is not None and not isinstance(place, str):
        raise ValueError("place must be a string")

    staging = artifact_dir.parent / f".{artifact_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    result = build_source_index_fn(
        include_fixtures=True,
        include_gbif=False,
        include_inaturalist=True,
        artifact_dir=staging,
        inaturalist_species=species,
        inaturalist_place=place,
        observation_limit=observation_limit,
        page_size=page_size,
        delay_seconds=delay_seconds,
    )
    if not result.get("ok"):
        shutil.rmtree(staging, ignore_errors=True)
        return {"ok": False, "error": "hosted ingest failed", "result": result}
    activate_staging_artifact(staging, artifact_dir)
    result["activated_artifact_dir"] = str(artifact_dir)
    return result


def dispatch_request(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    *,
    headers: object,
    artifact_dir: Path,
    token: str,
    build_source_index_fn: Callable[..., dict[str, object]] = build_source_index,
) -> Response:
    if not is_authorized(headers, token):
        return json_response(401, {"ok": False, "error": "unauthorized"})

    index = SourceIndex(artifact_dir / "source_index.sqlite")
    try:
        if method == "GET" and path == "/health":
            return json_response(200, health_payload(artifact_dir))
        if method == "GET" and path == "/summary":
            return json_response(200, index.summary())
        if method == "GET" and path == "/sources":
            return json_response(200, {"ok": True, "sources": read_sources(artifact_dir), "artifact_dir": str(artifact_dir)})
        if method == "POST" and path == "/ask":
            body = payload or {}
            question = str(body.get("question", ""))
            limit = int(body.get("limit", 5))
            return json_response(200, answer_question(question, artifact_dir=artifact_dir, limit=limit))
        if method == "POST" and path == "/search":
            body = payload or {}
            query = str(body.get("query", ""))
            lane_value = body.get("lane")
            lane = str(lane_value) if lane_value is not None else None
            limit = int(body.get("limit", 10))
            rows = [record.to_row() for record in index.search(query, lane=lane, limit=limit)]
            return json_response(200, {"ok": True, "rows": rows})
        if method == "POST" and path == "/sql":
            body = payload or {}
            sql = str(body.get("sql", ""))
            limit = int(body.get("limit", 100))
            return json_response(200, {"ok": True, "rows": index.sql(sql, limit=limit)})
        if method == "POST" and path == "/ingest/inaturalist":
            result = ingest_inaturalist(payload or {}, artifact_dir=artifact_dir, build_source_index_fn=build_source_index_fn)
            status = 200 if result.get("ok") else 500
            return json_response(status, result)
    except (sqlite3.Error, ValueError) as exc:
        return json_response(400, {"ok": False, "error": str(exc)})
    except Exception as exc:
        return json_response(500, {"ok": False, "error": str(exc)})

    return json_response(404, {"ok": False, "error": f"unknown route: {method} {path}"})


class AskInsectsHandler(BaseHTTPRequestHandler):
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    token: str = ""

    def _read_payload(self) -> dict[str, object] | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return None
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _send(self, response: Response) -> None:
        body = json.dumps(response.payload, sort_keys=True).encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        response = dispatch_request(
            "GET",
            self.path.split("?", 1)[0],
            None,
            headers=self.headers,
            artifact_dir=self.artifact_dir,
            token=self.token,
        )
        self._send(response)

    def do_POST(self) -> None:
        try:
            payload = self._read_payload()
            response = dispatch_request(
                "POST",
                self.path.split("?", 1)[0],
                payload,
                headers=self.headers,
                artifact_dir=self.artifact_dir,
                token=self.token,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            response = json_response(400, {"ok": False, "error": str(exc)})
        self._send(response)


def run_server(host: str, port: int, artifact_dir: Path, token: str) -> None:
    handler = type("ConfiguredAskInsectsHandler", (AskInsectsHandler,), {"artifact_dir": artifact_dir, "token": token})
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask-insects-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    args = parser.parse_args(argv)

    token = os.environ.get("ASK_INSECTS_TOKEN", "")
    if not token:
        raise SystemExit("ASK_INSECTS_TOKEN is required")
    run_server(args.host, args.port, Path(args.artifact_dir), token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
