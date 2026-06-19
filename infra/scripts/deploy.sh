#!/bin/bash
# PrimeData Deployment Script
# This script deploys the application to the VM

set -e

VM_NAME="${VM_NAME:-primedata-beta}"
GCP_ZONE="${GCP_ZONE:-us-central1-c}"
VM_USER="${VM_USER:-$USER}"

echo "=== PrimeData Deployment Script ==="

# Get VM IP
echo "Getting VM IP..."
VM_IP=$(gcloud compute instances describe "${VM_NAME}" \
  --zone="${GCP_ZONE}" \
  --format="value(networkInterfaces[0].accessConfig[0].natIP)")

if [ -z "${VM_IP}" ]; then
  echo "Error: Could not get VM IP. Is the VM running?"
  exit 1
fi

echo "VM IP: ${VM_IP}"

# Copy files to VM
echo "Copying files to VM..."
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='venv' \
  -e "ssh -o StrictHostKeyChecking=no" \
  ./ "${VM_USER}@${VM_IP}:/opt/primedata/"

# Deploy on VM
echo "Deploying on VM..."
ssh -o StrictHostKeyChecking=no "${VM_USER}@${VM_IP}" << 'EOF'
set -e
cd /opt/primedata

# Load environment variables
if [ -f .env.production ]; then
  export $(cat .env.production | grep -v '^#' | xargs)
fi

            # Ensure Docker network exists (idempotent)
            docker network create primedata-network 2>/dev/null || echo "Network already exists"
            
            # Pull latest images (idempotent - only updates if changed)
            docker-compose -f infra/docker-compose.prod.yml pull || true
            
            # Build and start services (idempotent - up -d handles existing containers)
            docker-compose -f infra/docker-compose.prod.yml up -d --build --remove-orphans
            
            # Wait for services
            sleep 10
            
            # Run migrations (idempotent - Alembic handles this)
            docker-compose -f infra/docker-compose.prod.yml exec -T backend \
              alembic upgrade head || echo "Migration failed or already up to date"

# Show status
docker-compose -f infra/docker-compose.prod.yml ps
EOF

echo "=== Deployment completed ==="

