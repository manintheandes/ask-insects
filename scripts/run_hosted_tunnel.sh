#!/usr/bin/env bash
set -euo pipefail

GCLOUD_BIN="${ASK_INSECTS_GCLOUD_BIN:-}"
if [[ -z "$GCLOUD_BIN" ]]; then
  GCLOUD_BIN="$(command -v gcloud || true)"
fi
if [[ -z "$GCLOUD_BIN" || ! -x "$GCLOUD_BIN" ]]; then
  echo "gcloud is required to open the Ask Insects tunnel" >&2
  exit 1
fi

PROJECT="${ASK_INSECTS_GCP_PROJECT:-$($GCLOUD_BIN config get-value project 2>/dev/null)}"
ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
LOCAL_PORT="${ASK_INSECTS_LOCAL_PORT:-18080}"
REMOTE_PORT="${ASK_INSECTS_REMOTE_PORT:-8080}"

exec "$GCLOUD_BIN" compute ssh "$VM" \
  --project "$PROJECT" \
  --zone "$ZONE" \
  -- \
  -N \
  -T \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}"
