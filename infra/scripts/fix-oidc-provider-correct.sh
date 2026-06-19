#!/bin/bash
# Fix OIDC Provider for GitHub Actions with correct attribute mapping

set -e

PROJECT_ID="project-f3c8a334-a3f2-4f66-a06"
PROJECT_NUMBER="890841479962"
GITHUB_REPO="neelam53yadav/aird"

echo "Fixing OIDC Provider with correct GitHub Actions mapping..."

# Delete existing provider if it exists
gcloud iam workload-identity-pools providers delete github-provider \
  --project=${PROJECT_ID} \
  --location="global" \
  --workload-identity-pool=github-pool \
  --quiet 2>/dev/null || echo "Provider doesn't exist, creating new one..."

# Create OIDC Provider with correct attribute mapping for GitHub Actions
# GitHub Actions provides: sub, repository, repository_owner, ref, sha, workflow, actor
# We only need to map google.subject, and can use assertion.repository directly in conditions
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=${PROJECT_ID} \
  --location="global" \
  --workload-identity-pool=github-pool \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub" \
  --attribute-condition="assertion.repository == '${GITHUB_REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

echo ""
echo "✅ OIDC Provider created successfully!"
echo ""
echo "Workload Identity Provider:"
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo ""
echo "This provider will only allow tokens from repository: ${GITHUB_REPO}"







