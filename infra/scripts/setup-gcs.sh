#!/bin/bash
# Setup GCS buckets and permissions for PrimeData

set -e

PROJECT_ID="${GCP_PROJECT_ID:-project-f3c8a334-a3f2-4f66-a06}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_EMAIL}"

echo "Setting up GCS buckets for PrimeData..."

# Buckets (already created, but verify)
BUCKETS=(
  "primedata-raw"
  "primedata-processed"
  "primedata-exports"
)

# Verify buckets exist
for bucket in "${BUCKETS[@]}"; do
  if gsutil ls -b "gs://${bucket}" > /dev/null 2>&1; then
    echo "✓ Bucket ${bucket} exists"
  else
    echo "✗ Bucket ${bucket} does not exist. Creating..."
    gsutil mb -p "${PROJECT_ID}" -l US "gs://${bucket}"
  fi
done

# Grant service account permissions
if [ -n "${SERVICE_ACCOUNT}" ]; then
  echo "Granting permissions to service account: ${SERVICE_ACCOUNT}"
  
  for bucket in "${BUCKETS[@]}"; do
    gsutil iam ch "serviceAccount:${SERVICE_ACCOUNT}:roles/storage.objectAdmin" "gs://${bucket}"
    echo "✓ Granted objectAdmin to ${bucket}"
  done
else
  echo "No service account provided. Skipping IAM setup."
fi

echo "GCS setup completed!"







