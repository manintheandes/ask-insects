#!/usr/bin/env bash
set -euo pipefail

ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
DATA_DIR="${ASK_INSECTS_REMOTE_DIR:-/home/josh/ask-insects}"
RUNTIME_ROOT="${ASK_INSECTS_REMOTE_RUNTIME_ROOT:-/home/josh/ask-insects-runtime}"
CURRENT_LINK="${ASK_INSECTS_REMOTE_CURRENT_LINK:-/home/josh/ask-insects-current}"
TOKEN="${ASK_INSECTS_TOKEN:?Set ASK_INSECTS_TOKEN before deploying}"
REFRESH_SOURCES="${ASK_INSECTS_DEPLOY_REFRESH_SOURCES:-0}"
RELEASE_ID="${ASK_INSECTS_RELEASE_ID:-$(git rev-parse --verify HEAD)}"
if [[ "$REFRESH_SOURCES" != "0" && "$REFRESH_SOURCES" != "1" ]]; then
  echo "ASK_INSECTS_DEPLOY_REFRESH_SOURCES must be 0 or 1" >&2
  exit 2
fi
if [[ "${#RELEASE_ID}" -ne 40 || "$RELEASE_ID" == *[!0-9a-f]* ]]; then
  echo "ASK_INSECTS_RELEASE_ID must be a full lowercase Git commit SHA" >&2
  exit 2
fi
RUNTIME_DIR="${RUNTIME_ROOT}-${RELEASE_ID}"
ARCHIVE="/tmp/ask-insects-deploy.tgz"

rm -f "$ARCHIVE"
tar \
  --exclude='.git' \
  --exclude='.worktrees' \
  --exclude='.superpowers' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='._*' \
  --exclude='artifacts' \
  --exclude='demo-recordings' \
  -czf "$ARCHIVE" .
gcloud compute scp "$ARCHIVE" "$VM:/tmp/ask-insects-deploy.tgz" --zone "$ZONE"

gcloud compute ssh "$VM" --zone "$ZONE" --command "
  set -euo pipefail
  sudo apt-get update
  sudo apt-get install -y python3 python3-h5py python3-pil curl ffmpeg poppler-utils
  rm -rf '$RUNTIME_DIR'
  mkdir -p '$RUNTIME_DIR' '$DATA_DIR'
  tar -xzf /tmp/ask-insects-deploy.tgz -C '$RUNTIME_DIR'
  printf '%s\n' '$RELEASE_ID' > '$RUNTIME_DIR/.deployed-revision'
  printf 'ASK_INSECTS_TOKEN=%s\nASK_INSECTS_RELEASE_ID=%s\n' \
    '$TOKEN' '$RELEASE_ID' > '$DATA_DIR/.env'
  chmod 600 '$DATA_DIR/.env'
  if [[ '$REFRESH_SOURCES' == '1' ]]; then
    python3 '$RUNTIME_DIR/scripts/ingest_plutella_xylostella_literature.py' \
      --artifact-dir '$DATA_DIR/artifacts/mosquito-v1'
    python3 '$RUNTIME_DIR/scripts/ingest_human_repellent_testing_guidance.py' \
      --artifact-dir '$DATA_DIR/artifacts/mosquito-v1'
    python3 '$RUNTIME_DIR/scripts/ingest_aedes_primary_behavior_evidence.py' \
      --artifact-dir '$DATA_DIR/artifacts/mosquito-v1'
    python3 '$RUNTIME_DIR/scripts/ingest_swd_primary_field_evidence.py' \
      --artifact-dir '$DATA_DIR/artifacts/mosquito-v1'
  fi
  if [[ -e '$CURRENT_LINK' && ! -L '$CURRENT_LINK' ]]; then
    rm -rf '$CURRENT_LINK'
  fi
  ln -sfn '$RUNTIME_DIR' '$CURRENT_LINK'
  sudo cp '$RUNTIME_DIR/deploy/systemd/ask-insects.service' /etc/systemd/system/ask-insects.service
  sudo rm -rf /etc/systemd/system/ask-insects.service.d
  sudo systemctl daemon-reload
  sudo systemctl enable ask-insects
  sudo systemctl restart ask-insects
  curl --retry 30 --retry-delay 1 --retry-connrefused --max-time 10 -fsS \
    -H 'Authorization: Bearer $TOKEN' \
    http://127.0.0.1:8080/health \
    | python3 -c \"import json,sys; payload=json.load(sys.stdin); assert payload.get('runtime_revision') == '$RELEASE_ID'\"
  MAIN_PID=\$(systemctl show --property MainPID --value ask-insects)
  test -n \"\$MAIN_PID\"
  test \"\$(readlink -f /proc/\$MAIN_PID/cwd)\" = '$RUNTIME_DIR'
  test \"\$(cat '$RUNTIME_DIR/.deployed-revision')\" = '$RELEASE_ID'
  if [[ '$REFRESH_SOURCES' == '1' ]]; then
    curl --max-time 600 -fsS -X POST \
      -H 'Authorization: Bearer $TOKEN' \
      -H 'Content-Type: application/json' \
      --data '{}' \
      http://127.0.0.1:8080/ingest/insect-intelligence-programs >/dev/null
  fi
  curl --max-time 10 -fsS \
    -H 'Authorization: Bearer $TOKEN' \
    http://127.0.0.1:8080/health \
    | python3 -c \"import json,sys; payload=json.load(sys.stdin); assert payload.get('runtime_revision') == '$RELEASE_ID'\"
"
