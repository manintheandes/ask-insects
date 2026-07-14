from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


CONFIG_PATH = Path.home() / ".config" / "ask-insects" / "config.json"


@dataclass(frozen=True)
class HostedConfig:
    url: str
    token: str


def save_config(config: HostedConfig, *, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"url": config.url, "token": config.token}, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def load_config(*, path: Path = CONFIG_PATH) -> HostedConfig:
    env_url = os.environ.get("ASK_INSECTS_URL")
    env_token = os.environ.get("ASK_INSECTS_TOKEN")
    if env_url and env_token:
        return HostedConfig(url=env_url, token=env_token)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HostedConfig(url=str(payload["url"]), token=str(payload["token"]))


def hosted_request(
    config: HostedConfig,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    *,
    urlopen_fn: Callable[..., object] = urlopen,
    timeout: int = 120,
    max_response_bytes: int | None = None,
) -> dict[str, object]:
    url = config.url.rstrip("/") + "/" + path.lstrip("/")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
        },
    )

    def read_response(response: object) -> bytes:
        if max_response_bytes is None:
            return response.read()
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        headers = getattr(response, "headers", None)
        content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
        if content_length not in {None, ""}:
            try:
                declared_length = int(content_length)
            except (TypeError, ValueError) as exc:
                raise ValueError("hosted Ask Insects returned an invalid Content-Length") from exc
            if declared_length > max_response_bytes:
                raise ValueError("hosted Ask Insects response exceeds the configured byte limit")
        raw = response.read(max_response_bytes + 1)
        if len(raw) > max_response_bytes:
            raise ValueError("hosted Ask Insects response exceeds the configured byte limit")
        return raw

    try:
        with urlopen_fn(request, timeout=timeout) as response:
            result = json.loads(read_response(response).decode("utf-8"))
    except HTTPError as exc:
        detail = read_response(exc).decode("utf-8")
        try:
            result = json.loads(detail)
        except json.JSONDecodeError:
            result = {"ok": False, "error": detail}
        if isinstance(result, dict):
            result = dict(result)
            result["ok"] = False
            result.setdefault("error", f"hosted Ask Insects returned HTTP {exc.code}")
    if not isinstance(result, dict):
        return {"ok": False, "error": "hosted Ask Insects returned non-object JSON"}
    return result
