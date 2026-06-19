#!/bin/bash

# MinIO bucket initialization script
# This script creates the required buckets for PrimeData
# ⚠️ WARNING: This script uses environment variables for MinIO credentials
# Set MINIO_ROOT_USER and MINIO_ROOT_PASSWORD environment variables!

set -e

echo "Creating MinIO buckets for PrimeData..."

# Get MinIO credentials from environment variables (with defaults for local dev)
MINIO_USER=${MINIO_ROOT_USER:-changeme}
MINIO_PASSWORD=${MINIO_ROOT_PASSWORD:-CHANGE_ME}

# Wait for MinIO to be ready
until mc alias set myminio http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD"; do
  echo "Waiting for MinIO to be ready..."
  sleep 2
done

# Create buckets
mc mb myminio/primedata-raw --ignore-existing
mc mb myminio/primedata-clean --ignore-existing
mc mb myminio/primedata-chunk --ignore-existing
mc mb myminio/primedata-embed --ignore-existing
mc mb myminio/primedata-export --ignore-existing

# Set bucket policies (public read for development)
mc anonymous set public myminio/primedata-export

echo "MinIO buckets created successfully!"
echo "Buckets:"
mc ls myminio
