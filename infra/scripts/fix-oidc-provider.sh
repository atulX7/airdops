#!/bin/bash
# Fix OIDC Provider for GitHub Actions
# The provider creation failed due to attribute mapping issue

set -e

PROJECT_ID="project-f3c8a334-a3f2-4f66-a06"
PROJECT_NUMBER="890841479962"

echo "Fixing OIDC Provider..."

# Delete existing provider if it exists (in case it was partially created)
gcloud iam workload-identity-pools providers delete github-provider \
  --project=${PROJECT_ID} \
  --location="global" \
  --workload-identity-pool=github-pool \
  --quiet 2>/dev/null || echo "Provider doesn't exist or already deleted"

# Create OIDC Provider with correct attribute mapping
# GitHub Actions provides these claims: sub, repository, actor, etc.
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=${PROJECT_ID} \
  --location="global" \
  --workload-identity-pool=github-pool \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
  --issuer-uri="https://token.actions.githubusercontent.com"

echo ""
echo "✅ OIDC Provider created successfully!"
echo ""
echo "Workload Identity Provider:"
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"







