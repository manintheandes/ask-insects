#!/usr/bin/env bash
set -euo pipefail

PROJECT="${ASK_INSECTS_GCP_PROJECT:-$(gcloud config get-value project)}"
ZONE="${ASK_INSECTS_GCP_ZONE:-us-central1-a}"
VM="${ASK_INSECTS_VM:-ask-insects}"
MACHINE_TYPE="${ASK_INSECTS_MACHINE_TYPE:-e2-small}"
IMAGE_FAMILY="${ASK_INSECTS_IMAGE_FAMILY:-debian-12}"
IMAGE_PROJECT="${ASK_INSECTS_IMAGE_PROJECT:-debian-cloud}"
TAGS="${ASK_INSECTS_TAGS:-ask-insects}"
ALLOWED_SOURCE_RANGES="${ASK_INSECTS_ALLOWED_SOURCE_RANGES:?Set ASK_INSECTS_ALLOWED_SOURCE_RANGES to trusted CIDRs}"

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

if gcloud compute firewall-rules describe ask-insects-8080 >/dev/null 2>&1; then
  gcloud compute firewall-rules update ask-insects-8080 \
    --source-ranges "$ALLOWED_SOURCE_RANGES"
else
  gcloud compute firewall-rules create ask-insects-8080 \
    --allow tcp:8080 \
    --target-tags "$TAGS" \
    --source-ranges "$ALLOWED_SOURCE_RANGES" \
    --description "Allow Ask Insects hosted API"
fi

gcloud compute instances describe "$VM" --zone "$ZONE" --format='value(networkInterfaces[0].accessConfigs[0].natIP)'
