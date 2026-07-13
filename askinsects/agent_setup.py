from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SKILL_DIR = REPO_ROOT / "skills" / "askinsects"
DEFAULT_SKILL_DESTINATION = Path.home() / ".codex" / "skills" / "askinsects"


def skill_manifest(path: Path) -> dict[str, str]:
    root = Path(path)
    if not (root / "SKILL.md").is_file():
        raise ValueError(f"Ask Insects skill is missing SKILL.md: {root}")
    manifest: dict[str, str] = {}
    for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = file_path.relative_to(root).as_posix()
        manifest[relative] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return manifest


def _manifest_digest(manifest: dict[str, str]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def install_askinsects_skill(
    *,
    destination: Path = DEFAULT_SKILL_DESTINATION,
    source: Path = REPO_SKILL_DIR,
) -> dict[str, object]:
    source_path = Path(source).resolve()
    destination_path = Path(destination).expanduser().resolve()
    source_manifest = skill_manifest(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{destination_path.name}.install-", dir=destination_path.parent)
    )
    staged_skill = staging_root / destination_path.name
    backup = destination_path.parent / f".{destination_path.name}.backup-{uuid.uuid4().hex}"
    moved_existing = False
    activated_new = False
    try:
        shutil.copytree(source_path, staged_skill)
        if skill_manifest(staged_skill) != source_manifest:
            raise RuntimeError("staged Ask Insects skill does not match the repository source")
        if destination_path.exists() or destination_path.is_symlink():
            os.replace(destination_path, backup)
            moved_existing = True
        os.replace(staged_skill, destination_path)
        activated_new = True
    except Exception:
        if activated_new:
            _remove_path(destination_path)
        if moved_existing and backup.exists():
            os.replace(backup, destination_path)
        raise
    finally:
        _remove_path(staging_root)

    if moved_existing:
        _remove_path(backup)
    installed_manifest = skill_manifest(destination_path)
    verified = installed_manifest == source_manifest
    return {
        "ok": verified,
        "verified": verified,
        "source": source_path.as_posix(),
        "destination": destination_path.as_posix(),
        "file_count": len(installed_manifest),
        "digest": _manifest_digest(installed_manifest),
    }
