# Ask Insects Hosted VM Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Ask Monarch-style hosted Ask Insects system: hosted ingest plus hosted query on a Google VM with server-local SQLite artifacts.

**Architecture:** Add a small standard-library HTTP API around the existing Ask Insects source index. The API reads and writes server-local artifacts, while the local CLI gains a hosted mode that sends authenticated requests to that API. Deployment scripts create/update a Google Compute Engine VM and run the API under systemd.

**Tech Stack:** Python standard library, SQLite, `argparse`, `urllib`, `http.server`, `unittest`, Google Cloud CLI, systemd, Google Compute Engine VM with persistent disk.

---

## File Structure

- Modify `askinsects/records.py`: add optional source payloads to `EvidenceRecord`.
- Modify `askinsects/index.py`: add `record_payloads` table and payload writes.
- Modify `askinsects/sources/inaturalist.py`: attach raw observation/photo payloads to normalized records.
- Create `askinsects/hosted.py`: hosted client config, authenticated request helper, and hosted command helpers.
- Create `askinsects/server.py`: hosted HTTP server, auth, JSON routing, safe ingest staging, and read endpoints.
- Modify `askinsects/cli.py`: add `configure`, `--hosted` mode, and `ingest-inaturalist`.
- Create `tests/test_hosted_client.py`: config and hosted request behavior.
- Create `tests/test_server.py`: API auth, read routes, SQL, ask, and ingest behavior.
- Modify existing tests for payload-table coverage.
- Modify `scripts/verify_complete.py`: include hosted tests and required files.
- Create `deploy/systemd/ask-insects.service`: systemd service template.
- Create `scripts/deploy_gce_vm.sh`: VM creation/firewall/bootstrap.
- Create `scripts/deploy_gce_app.sh`: copy repo, install service, restart API, and run smoke checks.
- Modify `README.md`, `docs/source-lanes.md`, `docs/querying-ask-insects.md`, and `config/source-map.yaml`: document hosted VM and server-local artifacts.

---

### Task 1: Preserve Raw iNaturalist Payloads In SQLite

**Files:**
- Modify: `askinsects/records.py`
- Modify: `askinsects/index.py`
- Modify: `askinsects/sources/inaturalist.py`
- Modify: `tests/test_inaturalist_source.py`
- Modify: `tests/test_index.py`

- [ ] **Step 1: Write failing tests for payload preservation**

Add assertions in `tests/test_inaturalist_source.py`:

```python
self.assertEqual(observation.payload["raw_observation"]["id"], 12345)
self.assertEqual(observation.payload["raw_photo"]["id"], 99)
self.assertEqual(media.payload["raw_observation"]["id"], 12345)
self.assertEqual(media.payload["raw_photo"]["id"], 99)
```

Add `test_payloads_are_queryable_from_sqlite` in `tests/test_index.py`:

```python
def test_payloads_are_queryable_from_sqlite(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "source_index.sqlite"
        index = SourceIndex(db_path)
        index.initialize()
        index.upsert_records([
            sample_record(payload={
                "raw_observation": {"id": 12345, "place_guess": "Rio de Janeiro, Brazil"},
                "raw_photo": {"id": 99, "url": "https://static.inaturalist.org/photos/99/medium.jpg"},
            })
        ])

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT record_id, source, lane, json_extract(payload_json, '$.raw_observation.id') AS observation_id
            FROM record_payloads
            WHERE record_id = ?
            """,
            ("obs:1",),
        ).fetchone()

        self.assertEqual(row, ("obs:1", "mosquito_v1_fixtures", "observations", 12345))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_inaturalist_source tests.test_index -v
```

Expected: failure because `EvidenceRecord` has no `payload` field and SQLite has no `record_payloads` table.

- [ ] **Step 3: Implement payload storage**

Add `payload: dict[str, Any] | None = None` to `EvidenceRecord`.

Add `record_payloads` to `SCHEMA` in `askinsects/index.py`:

```sql
CREATE TABLE IF NOT EXISTS record_payloads (
  record_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  lane TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  FOREIGN KEY(record_id) REFERENCES records(record_id)
);
CREATE INDEX IF NOT EXISTS idx_record_payloads_source ON record_payloads(source);
CREATE INDEX IF NOT EXISTS idx_record_payloads_lane ON record_payloads(lane);
```

In `SourceIndex.upsert_records`, write payload rows when `record.payload` is present.

In `askinsects/sources/inaturalist.py`, set payloads on observation and media records:

```python
payload={
    "raw_observation": observation,
    "raw_photo": photo,
    "query_url": query_url,
}
```

- [ ] **Step 4: Verify payload tests pass**

Run:

```bash
python3 -m unittest tests.test_inaturalist_source tests.test_index -v
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/records.py askinsects/index.py askinsects/sources/inaturalist.py tests/test_inaturalist_source.py tests/test_index.py
git commit -m "feat: store source payloads in sqlite"
```

---

### Task 2: Add Hosted Client Config And Request Helpers

**Files:**
- Create: `askinsects/hosted.py`
- Create: `tests/test_hosted_client.py`

- [ ] **Step 1: Write failing hosted client tests**

Create `tests/test_hosted_client.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from askinsects.hosted import HostedConfig, load_config, save_config, hosted_request


class HostedClientTests(unittest.TestCase):
    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            save_config(HostedConfig(url="https://ask-insects.example", token="secret"), path=path)
            loaded = load_config(path=path)
            self.assertEqual(loaded.url, "https://ask-insects.example")
            self.assertEqual(loaded.token, "secret")

    def test_hosted_request_sends_bearer_token_and_json(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request)

            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc, tb):
                    return False
                def read(self):
                    return json.dumps({"ok": True}).encode("utf-8")

            return Response()

        payload = hosted_request(
            HostedConfig(url="https://ask-insects.example/", token="secret"),
            "POST",
            "/ask",
            {"question": "hello"},
            urlopen_fn=fake_urlopen,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(calls[0].headers["Authorization"], "Bearer secret")
        self.assertEqual(calls[0].headers["Content-type"], "application/json")
        self.assertEqual(calls[0].full_url, "https://ask-insects.example/ask")
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python3 -m unittest tests.test_hosted_client -v
```

Expected: import failure because `askinsects.hosted` does not exist.

- [ ] **Step 3: Implement `askinsects/hosted.py`**

Implement:

```python
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
    path.write_text(json.dumps({"url": config.url, "token": config.token}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": detail}
        return parsed
```

- [ ] **Step 4: Verify hosted client tests pass**

Run:

```bash
python3 -m unittest tests.test_hosted_client -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/hosted.py tests/test_hosted_client.py
git commit -m "feat: add hosted client config"
```

---

### Task 3: Add Hosted HTTP API

**Files:**
- Create: `askinsects/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing server tests**

Create `tests/test_server.py` with direct handler helper tests:

```python
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.server import dispatch_request


class ServerTests(unittest.TestCase):
    def test_auth_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            response = dispatch_request(
                "GET",
                "/health",
                None,
                headers={},
                artifact_dir=Path(tmpdir),
                token="secret",
            )
            self.assertEqual(response.status, 401)
            self.assertFalse(response.payload["ok"])

    def test_health_summary_sources_and_sql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            headers = {"Authorization": "Bearer secret"}

            health = dispatch_request("GET", "/health", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertTrue(health.payload["ok"])
            self.assertEqual(health.payload["db_path"], str(artifact_dir / "source_index.sqlite"))

            summary = dispatch_request("GET", "/summary", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertEqual(summary.payload["record_count"], 7)

            sql = dispatch_request(
                "POST",
                "/sql",
                {"sql": "select source, count(*) as n from records group by source"},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
            )
            self.assertTrue(sql.payload["ok"])
            self.assertEqual(sql.payload["rows"][0]["n"], 7)

    def test_ingest_inaturalist_uses_staging_then_activates(self):
        calls = []

        def fake_builder(**kwargs):
            calls.append(kwargs)
            artifact_dir = kwargs["artifact_dir"]
            build_fixture_index(artifact_dir=artifact_dir)
            return {"ok": True, "record_count": 7}

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            headers = {"Authorization": "Bearer secret"}
            response = dispatch_request(
                "POST",
                "/ingest/inaturalist",
                {"species": ["Aedes aegypti"], "observation_limit": 10, "page_size": 10, "delay_seconds": 0},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
                build_source_index_fn=fake_builder,
            )
            self.assertTrue(response.payload["ok"])
            self.assertEqual(calls[0]["inaturalist_species"], ["Aedes aegypti"])
            self.assertTrue((artifact_dir / "source_index.sqlite").exists())
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_server -v
```

Expected: import failure because `askinsects.server` does not exist.

- [ ] **Step 3: Implement server routing**

Implement `askinsects/server.py` with:

- `Response(status: int, payload: dict[str, object])`
- `authorized(headers, token)`
- `dispatch_request(method, path, payload, headers, artifact_dir, token, build_source_index_fn=build_source_index)`
- `run_server(host, port, artifact_dir, token)`
- `main()` with `argparse`

Endpoint behavior:

```text
GET /health -> db/status existence, summary when possible, artifact path
GET /summary -> SourceIndex.summary()
GET /sources -> source_status.json sources
POST /ask -> answer_question(question, artifact_dir, limit)
POST /search -> SourceIndex.search(query, lane, limit)
POST /sql -> SourceIndex.sql(sql, limit)
POST /ingest/inaturalist -> build in staging dir, then replace active artifact dir only after success
```

Use `shutil.rmtree` and `Path.replace` for the staging activation:

```python
staging = artifact_dir.parent / f".{artifact_dir.name}.staging"
if staging.exists():
    shutil.rmtree(staging)
result = build_source_index_fn(
    include_fixtures=True,
    include_gbif=False,
    include_inaturalist=True,
    artifact_dir=staging,
    inaturalist_species=species,
    observation_limit=observation_limit,
    page_size=page_size,
    delay_seconds=delay_seconds,
)
backup = artifact_dir.parent / f".{artifact_dir.name}.previous"
if backup.exists():
    shutil.rmtree(backup)
if artifact_dir.exists():
    artifact_dir.replace(backup)
staging.replace(artifact_dir)
if backup.exists():
    shutil.rmtree(backup)
```

- [ ] **Step 4: Verify server tests pass**

Run:

```bash
python3 -m unittest tests.test_server -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/server.py tests/test_server.py
git commit -m "feat: add hosted Ask Insects API"
```

---

### Task 4: Wire Hosted Mode Into The CLI

**Files:**
- Modify: `askinsects/cli.py`
- Create: `tests/test_cli_hosted.py`

- [ ] **Step 1: Write failing CLI hosted tests**

Create `tests/test_cli_hosted.py` with a fake hosted request function:

```python
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from askinsects.cli import main


class HostedCliTests(unittest.TestCase):
    def run_cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(list(args))
        return code, output.getvalue()

    def test_configure_writes_hosted_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            with patch("askinsects.cli.HOSTED_CONFIG_PATH", path):
                code, output = self.run_cli("configure", "--url", "https://ask-insects.example", "--token", "secret")
            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertTrue(payload["ok"])
            self.assertTrue(path.exists())

    def test_hosted_health_uses_remote_request(self):
        calls = []

        def fake_request(config, method, path, payload=None):
            calls.append((method, path, payload))
            return {"ok": True, "hosted": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value.url = "https://ask-insects.example"
            load_config.return_value.token = "secret"
            code, output = self.run_cli("health", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ("GET", "/health", None))
        self.assertTrue(json.loads(output)["hosted"])
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_cli_hosted -v
```

Expected: failure because CLI has no hosted mode.

- [ ] **Step 3: Implement CLI hosted mode**

In `askinsects/cli.py`:

- add `configure`
- add `--hosted` to `health`, `summary`, `sources`, `ask`, `search`, and `sql`
- add `ingest-inaturalist`
- call `hosted_request(load_config(), method, path, payload)` when hosted

For local commands, preserve existing behavior.

- [ ] **Step 4: Verify CLI hosted tests pass**

Run:

```bash
python3 -m unittest tests.test_cli_hosted -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add askinsects/cli.py tests/test_cli_hosted.py
git commit -m "feat: add hosted CLI mode"
```

---

### Task 5: Add VM Deployment Scripts

**Files:**
- Create: `deploy/systemd/ask-insects.service`
- Create: `scripts/deploy_gce_vm.sh`
- Create: `scripts/deploy_gce_app.sh`
- Modify: `scripts/verify_complete.py`

- [ ] **Step 1: Write static deployment tests**

Create `tests/test_deploy_files.py`:

```python
from pathlib import Path
import unittest


class DeployFilesTests(unittest.TestCase):
    def test_systemd_service_runs_hosted_server(self):
        text = Path("deploy/systemd/ask-insects.service").read_text(encoding="utf-8")
        self.assertIn("ASK_INSECTS_TOKEN", text)
        self.assertIn("python3 -m askinsects.server", text)
        self.assertIn("/home/josh/ask-insects", text)

    def test_deploy_scripts_use_gcloud_compute(self):
        vm = Path("scripts/deploy_gce_vm.sh").read_text(encoding="utf-8")
        app = Path("scripts/deploy_gce_app.sh").read_text(encoding="utf-8")
        self.assertIn("gcloud compute instances", vm)
        self.assertIn("gcloud compute ssh", app)
        self.assertIn("ask-insects", vm)
        self.assertIn("systemctl restart ask-insects", app)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_deploy_files -v
```

Expected: file-not-found failures.

- [ ] **Step 3: Create systemd service**

Create `deploy/systemd/ask-insects.service`:

```ini
[Unit]
Description=Ask Insects hosted source service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=josh
WorkingDirectory=/home/josh/ask-insects
EnvironmentFile=/home/josh/ask-insects/.env
ExecStart=/usr/bin/python3 -m askinsects.server --host 0.0.0.0 --port 8080 --artifact-dir /home/josh/ask-insects/artifacts/mosquito-v1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Create VM deployment script**

Create `scripts/deploy_gce_vm.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT="${ASK_INSECTS_GCP_PROJECT:-$(gcloud config get-value project)}"
ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
MACHINE_TYPE="${ASK_INSECTS_MACHINE_TYPE:-e2-small}"
IMAGE_FAMILY="${ASK_INSECTS_IMAGE_FAMILY:-debian-12}"
IMAGE_PROJECT="${ASK_INSECTS_IMAGE_PROJECT:-debian-cloud}"
TAGS="${ASK_INSECTS_TAGS:-ask-insects}"

gcloud config set project "$PROJECT" >/dev/null

if ! gcloud compute instances describe "$VM" --zone "$ZONE" >/dev/null 2>&1; then
  gcloud compute instances create "$VM" \
    --zone "$ZONE" \
    --machine-type "$MACHINE_TYPE" \
    --image-family "$IMAGE_FAMILY" \
    --image-project "$IMAGE_PROJECT" \
    --boot-disk-size "30GB" \
    --tags "$TAGS"
fi

if ! gcloud compute firewall-rules describe ask-insects-8080 >/dev/null 2>&1; then
  gcloud compute firewall-rules create ask-insects-8080 \
    --allow tcp:8080 \
    --target-tags "$TAGS" \
    --description "Allow Ask Insects hosted API"
fi

gcloud compute instances describe "$VM" --zone "$ZONE" --format='value(networkInterfaces[0].accessConfigs[0].natIP)'
```

- [ ] **Step 5: Create app deployment script**

Create `scripts/deploy_gce_app.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
REMOTE_DIR="${ASK_INSECTS_REMOTE_DIR:-/home/josh/ask-insects}"
TOKEN="${ASK_INSECTS_TOKEN:?Set ASK_INSECTS_TOKEN before deploying}"

tar --exclude='.git' --exclude='.worktrees' --exclude='.superpowers' --exclude='artifacts' -czf /tmp/ask-insects-deploy.tgz .
gcloud compute scp /tmp/ask-insects-deploy.tgz "$VM:/tmp/ask-insects-deploy.tgz" --zone "$ZONE"

gcloud compute ssh "$VM" --zone "$ZONE" --command "
  set -euo pipefail
  sudo apt-get update
  sudo apt-get install -y python3
  mkdir -p '$REMOTE_DIR'
  tar -xzf /tmp/ask-insects-deploy.tgz -C '$REMOTE_DIR'
  printf 'ASK_INSECTS_TOKEN=%s\n' '$TOKEN' > '$REMOTE_DIR/.env'
  sudo cp '$REMOTE_DIR/deploy/systemd/ask-insects.service' /etc/systemd/system/ask-insects.service
  sudo systemctl daemon-reload
  sudo systemctl enable ask-insects
  sudo systemctl restart ask-insects
"
```

- [ ] **Step 6: Add deployment files to verification gate**

Add these to `REQUIRED_FILES` in `scripts/verify_complete.py`:

```python
"deploy/systemd/ask-insects.service",
"scripts/deploy_gce_vm.sh",
"scripts/deploy_gce_app.sh",
"tests/test_deploy_files.py",
"tests/test_hosted_client.py",
"tests/test_server.py",
"tests/test_cli_hosted.py",
```

Add hosted tests to `UNIT_TEST_MODULES`.

- [ ] **Step 7: Verify deployment tests pass**

Run:

```bash
python3 -m unittest tests.test_deploy_files -v
```

Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add deploy/systemd/ask-insects.service scripts/deploy_gce_vm.sh scripts/deploy_gce_app.sh scripts/verify_complete.py tests/test_deploy_files.py
git commit -m "feat: add GCE deployment scripts"
```

---

### Task 6: Update Docs And Source Map

**Files:**
- Modify: `README.md`
- Modify: `docs/source-lanes.md`
- Modify: `docs/querying-ask-insects.md`
- Modify: `config/source-map.yaml`

- [ ] **Step 1: Add hosted docs**

Update `README.md` with:

```markdown
## Hosted Ask Insects

Hosted V1 follows the Ask Monarch VM pattern. The parsed SQLite index and raw source artifacts live on the Google VM under `/home/josh/ask-insects/artifacts/mosquito-v1/`.
```

Update `docs/querying-ask-insects.md` with hosted CLI examples:

```bash
python3 -m askinsects configure --url http://<vm-ip>:8080 --token "$ASK_INSECTS_TOKEN"
python3 -m askinsects health --hosted
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil"
```

Update `config/source-map.yaml` with a hosted artifact boundary:

```yaml
hosted:
  provider: google_compute_engine
  vm_name: ask-insects
  remote_root: /home/josh/ask-insects
  artifact_dir: /home/josh/ask-insects/artifacts/mosquito-v1
  sqlite_index: /home/josh/ask-insects/artifacts/mosquito-v1/source_index.sqlite
```

- [ ] **Step 2: Run docs grep checks**

Run:

```bash
rg -n "Hosted Ask Insects|/home/josh/ask-insects|ingest-inaturalist|record_payloads" README.md docs config
```

Expected: hosted shape and payload table are documented.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/source-lanes.md docs/querying-ask-insects.md config/source-map.yaml
git commit -m "docs: document hosted Ask Insects"
```

---

### Task 7: Local Verification

**Files:**
- No source changes expected.

- [ ] **Step 1: Run all unit tests**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run completion gate**

Run:

```bash
python3 scripts/verify_complete.py
```

Expected:

```text
verify_complete ok
```

- [ ] **Step 3: Start hosted server locally**

Run:

```bash
ASK_INSECTS_TOKEN=dev-token python3 -m askinsects.server --host 127.0.0.1 --port 8765 --artifact-dir artifacts/mosquito-v1
```

Expected: server starts and waits for requests.

- [ ] **Step 4: Configure local CLI against local hosted server**

In another shell:

```bash
python3 -m askinsects configure --url http://127.0.0.1:8765 --token dev-token
python3 -m askinsects health --hosted
```

Expected: hosted health returns JSON with `"ok": true`.

- [ ] **Step 5: Run hosted smoke ingest locally**

Run:

```bash
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 2 --page-size 2 --delay-seconds 0
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil" --json --limit 2
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
```

Expected: hosted ingest writes local server artifacts and hosted ask/sql return iNaturalist rows.

- [ ] **Step 6: Commit verification-only doc updates if needed**

If command examples required correction, commit those docs:

```bash
git add README.md docs/querying-ask-insects.md
git commit -m "docs: correct hosted verification commands"
```

---

### Task 8: GCE Deployment

**Files:**
- No source changes expected unless deployment reveals a script bug.

- [ ] **Step 1: Create a token**

Run:

```bash
export ASK_INSECTS_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
```

Expected: `ASK_INSECTS_TOKEN` is set in the current shell.

- [ ] **Step 2: Create or verify the VM**

Run:

```bash
scripts/deploy_gce_vm.sh
```

Expected: prints the VM external IP.

- [ ] **Step 3: Deploy the app**

Run:

```bash
scripts/deploy_gce_app.sh
```

Expected: systemd service is installed and restarted on the VM.

- [ ] **Step 4: Configure the CLI against the VM**

Run:

```bash
VM_IP="$(gcloud compute instances describe ask-insects --zone "${ASK_INSECTS_GCP_ZONE:-us-central1-a}" --format='value(networkInterfaces[0].accessConfigs[0].natIP)')"
python3 -m askinsects configure --url "http://${VM_IP}:8080" --token "$ASK_INSECTS_TOKEN"
```

Expected: config writes successfully.

- [ ] **Step 5: Run hosted health**

Run:

```bash
python3 -m askinsects health --hosted
```

Expected: hosted health returns ok and a server-local `db_path`.

- [ ] **Step 6: Run hosted ingest smoke**

Run:

```bash
python3 -m askinsects ingest-inaturalist --hosted --species "Aedes aegypti" --observation-limit 10 --page-size 10 --delay-seconds 0
```

Expected: hosted response reports `ok: true` and iNaturalist source counts.

- [ ] **Step 7: Run hosted query smoke**

Run:

```bash
python3 -m askinsects ask --hosted "show mosquito observations with images in Brazil" --json --limit 3
python3 -m askinsects sql --hosted "select source, lane, count(*) as n from records group by source, lane"
```

Expected: responses come from hosted SQLite and include provenance.

- [ ] **Step 8: Commit deployment script fixes if needed**

If deployment required script edits, run tests and commit:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
git add scripts deploy README.md docs tests askinsects
git commit -m "fix: harden hosted deployment"
```

