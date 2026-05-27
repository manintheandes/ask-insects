#!/usr/bin/env bash
set -euo pipefail

ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
REMOTE_DIR="${ASK_INSECTS_REMOTE_DIR:-/home/josh/ask-insects}"
TOKEN="${ASK_INSECTS_TOKEN:?Set ASK_INSECTS_TOKEN before deploying}"
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
  sudo apt-get install -y python3 python3-h5py python3-pil ffmpeg poppler-utils
  mkdir -p '$REMOTE_DIR'
  tar -xzf /tmp/ask-insects-deploy.tgz -C '$REMOTE_DIR'
  printf 'ASK_INSECTS_TOKEN=%s\n' '$TOKEN' > '$REMOTE_DIR/.env'
  sudo cp '$REMOTE_DIR/deploy/systemd/ask-insects.service' /etc/systemd/system/ask-insects.service
  sudo systemctl daemon-reload
  sudo systemctl enable ask-insects
  sudo systemctl restart ask-insects
"
