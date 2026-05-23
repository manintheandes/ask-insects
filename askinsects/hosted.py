from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
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
    path.write_text(
        json.dumps({"url": config.url, "token": config.token}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        try:
            result = json.loads(detail)
        except json.JSONDecodeError:
            result = {"ok": False, "error": detail}
    if not isinstance(result, dict):
        return {"ok": False, "error": "hosted Ask Insects returned non-object JSON"}
    return result
