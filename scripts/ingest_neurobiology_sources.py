#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_ARTIFACT_DIR = Path.home() / ".local/share/ask-insects/sources/neurobiology"
GEO_RAW_URL = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE160nnn/GSE160740/suppl/GSE160740_RAW.tar"
SRA_RUNINFO_URL = "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc=SRP290992"
MOSQUITOBRAINS_DOWNLOADS_URL = "https://www.mosquitobrains.org/downloads-and-links"
ZENODO_API_URL = "https://zenodo.org/api/records/14890013"
AEDES_PUBLIC_REPO_API_URL = "https://api.github.com/repos/htem/aedes_public"
AEDES_PUBLIC_CSVS_API_URL = "https://api.github.com/repos/htem/aedes_public/contents/csvs"
AEDES_PUBLIC_README_URL = "https://raw.githubusercontent.com/htem/aedes_public/main/README.md"
CATMAID_BASE_URL = "https://radagast.hms.harvard.edu/catmaidaedes"
CATMAID_PROJECTS_URL = f"{CATMAID_BASE_URL}/projects/"
CATMAID_STACKS_URL = f"{CATMAID_BASE_URL}/1/stacks"
CATMAID_STACK_1_INFO_URL = f"{CATMAID_BASE_URL}/1/stack/1/info"
CATMAID_ANNOTATIONS_URL = f"{CATMAID_BASE_URL}/1/annotations/"
CATMAID_VOLUMES_URL = f"{CATMAID_BASE_URL}/1/volumes/"
CATMAID_SKELETONS_URL = f"{CATMAID_BASE_URL}/1/skeletons/"
CATMAID_SKELETON_NODECOUNT_URLS = {
    "skeletons_nodecount_gt_1": f"{CATMAID_SKELETONS_URL}?nodecount_gt=1",
    "skeletons_nodecount_gt_10": f"{CATMAID_SKELETONS_URL}?nodecount_gt=10",
    "skeletons_nodecount_gt_100": f"{CATMAID_SKELETONS_URL}?nodecount_gt=100",
}
USER_AGENT = "ask-insects-neurobiology-ingest/1.0 (+https://github.com/openai/codex)"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_md5(checksum: object) -> str | None:
    if not isinstance(checksum, str):
        return None
    if checksum.startswith("md5:"):
        return checksum.removeprefix("md5:")
    return None


def is_complete(path: Path, *, size: int | None = None, checksum: str | None = None) -> bool:
    if not path.exists():
        return False
    if size is not None and path.stat().st_size != size:
        return False
    if checksum and md5(path) != checksum:
        return False
    return True


def download(url: str, path: Path, *, size: int | None = None, checksum: str | None = None) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_complete(path, size=size, checksum=checksum):
        return {"ok": True, "path": path.as_posix(), "status": "already_present", "bytes": path.stat().st_size}

    part_path = path.with_suffix(path.suffix + ".part")
    if part_path.exists():
        part_path.unlink()

    try:
        with urllib.request.urlopen(request(url), timeout=120) as response, part_path.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
    except urllib.error.URLError as exc:
        if part_path.exists():
            part_path.unlink()
        return {"ok": False, "url": url, "path": path.as_posix(), "error": str(exc)}

    part_path.replace(path)
    if size is not None and path.stat().st_size != size:
        return {
            "ok": False,
            "url": url,
            "path": path.as_posix(),
            "error": f"downloaded size {path.stat().st_size} did not match expected size {size}",
        }
    if checksum and md5(path) != checksum:
        return {"ok": False, "url": url, "path": path.as_posix(), "error": "md5 checksum mismatch"}
    return {"ok": True, "path": path.as_posix(), "status": "downloaded", "bytes": path.stat().st_size}


def fetch_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(request(url), timeout=120) as response:
        payload = response.read().decode("utf-8")
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{url} did not return a JSON object")
    return loaded


def fetch_json_payload(url: str) -> object:
    with urllib.request.urlopen(request(url), timeout=120) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(request(url), timeout=120) as response:
        return response.read().decode("utf-8", errors="replace")


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "download"


def dropbox_download_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(html.unescape(url))
    query = urllib.parse.parse_qs(parsed.query)
    query["dl"] = ["1"]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query, doseq=True), parsed.fragment))


def dropbox_links(page: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"<a[^>]+href=[\"'](?P<url>https://www\.dropbox\.com/[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", page, re.I | re.S):
        url = html.unescape(match.group("url"))
        label = re.sub(r"<[^>]+>", " ", match.group("label"))
        label = html.unescape(re.sub(r"\s+", " ", label)).strip() or Path(urllib.parse.urlsplit(url).path).name
        links.append((label, url))
    if links:
        return links
    return [(Path(urllib.parse.urlsplit(url).path).name, html.unescape(url)) for url in sorted(set(re.findall(r"https://www\.dropbox\.com/[^\"']+", page)))]


def ingest(artifact_dir: Path, *, download_dropbox: bool = True) -> dict[str, object]:
    manifest: dict[str, object] = {
        "ok": True,
        "generated_at": utc_now(),
        "artifact_dir": artifact_dir.as_posix(),
        "downloads": [],
        "gaps": [],
    }
    downloads = manifest["downloads"]
    gaps = manifest["gaps"]
    assert isinstance(downloads, list)
    assert isinstance(gaps, list)

    geo_path = artifact_dir / "geo" / "GSE160740" / "GSE160740_RAW.tar"
    downloads.append({"source": "geo", "url": GEO_RAW_URL, **download(GEO_RAW_URL, geo_path)})
    sra_runinfo_path = artifact_dir / "geo" / "SRP290992_runinfo.csv"
    downloads.append({"source": "sra", "url": SRA_RUNINFO_URL, **download(SRA_RUNINFO_URL, sra_runinfo_path)})

    zenodo_dir = artifact_dir / "zenodo" / "14890013"
    zenodo_dir.mkdir(parents=True, exist_ok=True)
    zenodo_record = fetch_json(ZENODO_API_URL)
    write_json(zenodo_dir / "record.json", zenodo_record)
    downloads.append({"source": "zenodo", "url": ZENODO_API_URL, "path": (zenodo_dir / "record.json").as_posix(), "ok": True, "status": "downloaded"})
    for file_payload in zenodo_record.get("files", []):
        if not isinstance(file_payload, dict):
            continue
        key = str(file_payload.get("key", "unknown"))
        url = str(file_payload.get("links", {}).get("self", ""))
        if not url:
            gaps.append({"source": "zenodo", "reason": "missing_file_url", "key": key})
            continue
        size = file_payload.get("size")
        size_int = int(size) if isinstance(size, int) else None
        result = download(
            url,
            zenodo_dir / key,
            size=size_int,
            checksum=expected_md5(file_payload.get("checksum")),
        )
        downloads.append({"source": "zenodo", "key": key, "url": url, **result})
        if not result.get("ok"):
            gaps.append({"source": "zenodo", "reason": "download_failed", "key": key, "error": result.get("error")})

    mosquito_dir = artifact_dir / "mosquitobrains"
    mosquito_dir.mkdir(parents=True, exist_ok=True)
    page = fetch_text(MOSQUITOBRAINS_DOWNLOADS_URL)
    page_path = mosquito_dir / "downloads-and-links.html"
    page_path.write_text(page, encoding="utf-8")
    downloads.append({"source": "mosquitobrains", "url": MOSQUITOBRAINS_DOWNLOADS_URL, "path": page_path.as_posix(), "ok": True, "status": "downloaded"})

    links = dropbox_links(page)
    if not links:
        gaps.append({"source": "mosquitobrains", "reason": "no_dropbox_links_found", "url": MOSQUITOBRAINS_DOWNLOADS_URL})
    elif not download_dropbox:
        for label, url in links:
            gaps.append({"source": "mosquitobrains", "reason": "dropbox_download_skipped", "label": label, "url": url})
    else:
        for label, url in links:
            out_path = mosquito_dir / "downloads" / f"{slug(label)}.zip"
            result = download(dropbox_download_url(url), out_path)
            downloads.append({"source": "mosquitobrains", "label": label, "url": url, **result})
            if not result.get("ok"):
                gaps.append({"source": "mosquitobrains", "reason": "dropbox_download_failed", "label": label, "url": url, "error": result.get("error")})

    connectome_dir = artifact_dir / "connectome" / "aedes_public"
    connectome_dir.mkdir(parents=True, exist_ok=True)
    try:
        repo_payload = fetch_json(AEDES_PUBLIC_REPO_API_URL)
        write_json(connectome_dir / "repo.json", repo_payload)
        downloads.append(
            {
                "source": "connectome",
                "url": AEDES_PUBLIC_REPO_API_URL,
                "path": (connectome_dir / "repo.json").as_posix(),
                "ok": True,
                "status": "downloaded",
            }
        )
        readme_text = fetch_text(AEDES_PUBLIC_README_URL)
        readme_path = connectome_dir / "README.md"
        readme_path.write_text(readme_text, encoding="utf-8")
        downloads.append(
            {
                "source": "connectome",
                "url": AEDES_PUBLIC_README_URL,
                "path": readme_path.as_posix(),
                "ok": True,
                "status": "downloaded",
            }
        )
        catmaid_dir = connectome_dir / "catmaid"
        catmaid_dir.mkdir(parents=True, exist_ok=True)
        for label, url, filename in (
            ("catmaid_projects", CATMAID_PROJECTS_URL, "projects.json"),
            ("catmaid_stacks", CATMAID_STACKS_URL, "stacks.json"),
            ("catmaid_stack_1_info", CATMAID_STACK_1_INFO_URL, "stack_1_info.json"),
            ("catmaid_annotations", CATMAID_ANNOTATIONS_URL, "annotations.json"),
            ("catmaid_volumes", CATMAID_VOLUMES_URL, "volumes.json"),
            ("catmaid_skeletons", CATMAID_SKELETONS_URL, "skeletons.json"),
        ):
            payload = fetch_json_payload(url)
            path = catmaid_dir / filename
            write_json(path, payload)
            downloads.append(
                {
                    "source": "connectome",
                    "key": label,
                    "url": url,
                    "path": path.as_posix(),
                    "ok": True,
                    "status": "downloaded",
                }
            )
        for label, url in CATMAID_SKELETON_NODECOUNT_URLS.items():
            payload = fetch_json_payload(url)
            path = catmaid_dir / f"{label}.json"
            write_json(path, payload)
            downloads.append(
                {
                    "source": "connectome",
                    "key": label,
                    "url": url,
                    "path": path.as_posix(),
                    "ok": True,
                    "status": "downloaded",
                }
            )
        csv_items = fetch_json_payload(AEDES_PUBLIC_CSVS_API_URL)
        if not isinstance(csv_items, list):
            gaps.append({"source": "connectome", "reason": "github_csv_listing_not_list", "url": AEDES_PUBLIC_CSVS_API_URL})
        else:
            for item in csv_items:
                if not isinstance(item, dict) or item.get("type") != "file":
                    continue
                name = str(item.get("name", ""))
                download_url = str(item.get("download_url", ""))
                if not name.endswith(".csv") or not download_url:
                    continue
                result = download(download_url, connectome_dir / "csvs" / name)
                downloads.append({"source": "connectome", "key": name, "url": download_url, **result})
                if not result.get("ok"):
                    gaps.append({"source": "connectome", "reason": "github_csv_download_failed", "key": name, "error": result.get("error")})
    except (urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        gaps.append({"source": "connectome", "reason": "github_metadata_fetch_failed", "error": str(exc)})

    manifest["ok"] = not any(isinstance(item, dict) and not item.get("ok", False) for item in downloads)
    write_json(artifact_dir / "manifest.json", manifest)
    return manifest


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Aedes aegypti neurobiology raw sources for Ask Insects.")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--skip-dropbox", action="store_true", help="Preserve MosquitoBrains links but do not download Dropbox folder ZIPs.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    manifest = ingest(Path(args.artifact_dir), download_dropbox=not args.skip_dropbox)
    print(json.dumps(manifest, sort_keys=True))
    return 0 if manifest.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
