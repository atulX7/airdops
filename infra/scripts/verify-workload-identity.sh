#!/bin/bash
# Verify Workload Identity Federation Setup

set -e

PROJECT_ID="project-f3c8a334-a3f2-4f66-a06"
PROJECT_NUMBER="890841479962"
SA_EMAIL="github-actions@${PROJECT_ID}.iam.gserviceaccount.com"
GITHUB_REPO="neelam53yadav/aird"

echo "=== Verifying Workload Identity Federation Setup ==="
echo ""

# 1. Check Workload Identity Pool
echo "1. Checking Workload Identity Pool..."
POOL_EXISTS=$(gcloud iam workload-identity-pools describe github-pool \
  --project=${PROJECT_ID} \
  --location="global" \
  --format="value(name)" 2>/dev/null || echo "")

if [ -n "$POOL_EXISTS" ]; then
  echo "✅ Pool exists: $POOL_EXISTS"
else
  echo "❌ Pool does not exist!"
  exit 1
fi
echo ""

# 2. Check OIDC Provider
echo "2. Checking OIDC Provider..."
PROVIDER_EXISTS=$(gcloud iam workload-identity-pools providers describe github-provider \
  --project=${PROJECT_ID} \
  --location="global" \
  --workload-identity-pool=github-pool \
  --format="value(name)" 2>/dev/null || echo "")

if [ -n "$PROVIDER_EXISTS" ]; then
  echo "✅ Provider exists: $PROVIDER_EXISTS"
  
  # Check provider details
  PROVIDER_STATE=$(gcloud iam workload-identity-pools providers describe github-provider \
    --project=${PROJECT_ID} \
    --location="global" \
    --workload-identity-pool=github-pool \
    --format="value(state)" 2>/dev/null)
  
  if [ "$PROVIDER_STATE" = "ACTIVE" ]; then
    echo "✅ Provider is ACTIVE"
  else
    echo "⚠️  Provider state: $PROVIDER_STATE"
  fi
else
  echo "❌ Provider does not exist!"
  exit 1
fi
echo ""

# 3. Check Service Account
echo "3. Checking Service Account..."
SA_EXISTS=$(gcloud iam service-accounts describe ${SA_EMAIL} \
  --project=${PROJECT_ID} \
  --format="value(email)" 2>/dev/null || echo "")

if [ -n "$SA_EXISTS" ]; then
  echo "✅ Service account exists: $SA_EXISTS"
else
  echo "❌ Service account does not exist!"
  exit 1
fi
echo ""

# 4. Check Service Account IAM Policy (Workload Identity User binding)
echo "4. Checking Service Account IAM Policy..."
IAM_BINDING=$(gcloud iam service-accounts get-iam-policy ${SA_EMAIL} \
  --project=${PROJECT_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GITHUB_REPO}" \
  --format="value(bindings.role)" 2>/dev/null || echo "")

if [ "$IAM_BINDING" = "roles/iam.workloadIdentityUser" ]; then
  echo "✅ Service account has Workload Identity User role"
  echo "✅ Binding allows: ${GITHUB_REPO}"
else
  echo "❌ Service account IAM binding not found or incorrect!"
  echo "   Expected: roles/iam.workloadIdentityUser"
  echo "   Found: $IAM_BINDING"
  exit 1
fi
echo ""

# 5. Check Service Account Permissions
echo "5. Checking Service Account Project Permissions..."
PERMISSIONS=$(gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${SA_EMAIL}" \
  --format="value(bindings.role)" 2>/dev/null | sort -u)

if [ -n "$PERMISSIONS" ]; then
  echo "✅ Service account has the following roles:"
  echo "$PERMISSIONS" | while read role; do
    echo "   - $role"
  done
else
  echo "⚠️  No project-level permissions found for service account"
fi
echo ""

# 6. Summary
echo "=== Summary ==="
echo ""
echo "Workload Identity Provider Path:"
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo ""
echo "Service Account:"
echo "${SA_EMAIL}"
echo ""
echo "Repository Restriction:"
echo "${GITHUB_REPO}"
echo ""
echo "✅ All checks passed! Workload Identity Federation is correctly configured."
echo ""
echo "Next steps:"
echo "1. Add VM_USERNAME secret to GitHub"
echo "2. Add VM_SSH_KEY secret to GitHub"
echo "3. Push code to trigger workflows"







