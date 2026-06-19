#!/bin/bash
# Script to fix NEXTAUTH_SECRET mismatch between frontend and backend
# This ensures both services use the same secret for NextAuth token encryption/decryption

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 Fixing NEXTAUTH_SECRET Mismatch"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Default deployment path
DEPLOY_PATH="${DEPLOY_PATH:-/opt/primedata}"

# Check if .env file exists
ENV_FILE="${DEPLOY_PATH}/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    echo "Please create it based on env.production.example"
    exit 1
fi

echo "📄 Found .env file at: $ENV_FILE"
echo ""

# Check current NEXTAUTH_SECRET value
CURRENT_SECRET=$(grep "^NEXTAUTH_SECRET=" "$ENV_FILE" | cut -d '=' -f2- | tr -d '"' || echo "")

if [ -z "$CURRENT_SECRET" ] || [ "$CURRENT_SECRET" = "YOUR_NEXTAUTH_SECRET_64_CHARS_MIN" ] || [ "$CURRENT_SECRET" = "REPLACE_WITH_64_CHAR_RANDOM_STRING_FOR_PRODUCTION_USE_ONLY" ]; then
    echo "⚠️  NEXTAUTH_SECRET is not set or using default value"
    echo ""
    echo "Generating a new secure secret..."
    NEW_SECRET=$(openssl rand -base64 48 | tr -d "=+/" | cut -c1-64)
    echo ""
    echo "✅ Generated new secret (64 characters)"
    echo ""
    
    # Update .env file
    if grep -q "^NEXTAUTH_SECRET=" "$ENV_FILE"; then
        # Replace existing value
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s|^NEXTAUTH_SECRET=.*|NEXTAUTH_SECRET=${NEW_SECRET}|" "$ENV_FILE"
        else
            # Linux
            sed -i "s|^NEXTAUTH_SECRET=.*|NEXTAUTH_SECRET=${NEW_SECRET}|" "$ENV_FILE"
        fi
    else
        # Add new line
        echo "NEXTAUTH_SECRET=${NEW_SECRET}" >> "$ENV_FILE"
    fi
    
    echo "✅ Updated .env file with new NEXTAUTH_SECRET"
    echo ""
    echo "⚠️  IMPORTANT: Users will need to clear browser cookies and sign in again"
    echo "   Old tokens were encrypted with a different secret"
    echo ""
else
    echo "✅ NEXTAUTH_SECRET is already set"
    echo "   Length: ${#CURRENT_SECRET} characters"
    echo "   First 10 chars: ${CURRENT_SECRET:0:10}..."
    echo ""
    echo "Verifying it's the same in both services..."
    
    # Check backend container
    BACKEND_SECRET=$(docker exec primedata-backend printenv NEXTAUTH_SECRET 2>/dev/null || echo "")
    FRONTEND_SECRET=$(docker exec primedata-frontend printenv NEXTAUTH_SECRET 2>/dev/null || echo "")
    
    if [ -n "$BACKEND_SECRET" ] && [ -n "$FRONTEND_SECRET" ]; then
        if [ "$BACKEND_SECRET" = "$FRONTEND_SECRET" ] && [ "$BACKEND_SECRET" = "$CURRENT_SECRET" ]; then
            echo "✅ All services have matching NEXTAUTH_SECRET"
        else
            echo "❌ Mismatch detected!"
            echo "   .env file: ${CURRENT_SECRET:0:10}..."
            echo "   Backend:   ${BACKEND_SECRET:0:10}..."
            echo "   Frontend:  ${FRONTEND_SECRET:0:10}..."
            echo ""
            echo "Restarting services to sync secrets..."
            NEW_SECRET="$CURRENT_SECRET"
        fi
    else
        echo "⚠️  Could not verify container secrets (containers may not be running)"
        echo "   Will restart services to ensure sync"
        NEW_SECRET="$CURRENT_SECRET"
    fi
fi

# Restart services to pick up the secret
echo ""
echo "🔄 Restarting services to apply NEXTAUTH_SECRET..."
cd "$DEPLOY_PATH"

# Determine Docker command
if docker ps > /dev/null 2>&1; then
    DOCKER_CMD="docker"
else
    DOCKER_CMD="sudo docker"
fi

# Determine Docker Compose command
if $DOCKER_CMD compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="$DOCKER_CMD compose"
elif command -v docker-compose > /dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    DOCKER_COMPOSE_CMD="sudo docker-compose"
fi

# Restart backend and frontend
echo "   Restarting backend..."
$DOCKER_COMPOSE_CMD -f infra/docker-compose.prod.yml restart backend || true

echo "   Restarting frontend..."
$DOCKER_COMPOSE_CMD -f infra/docker-compose.prod.yml restart frontend || true

echo ""
echo "✅ Services restarted"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Clear browser cookies for the site"
echo "2. Sign in again (tokens will be encrypted with the new secret)"
echo "3. Verify authentication works"
echo ""
echo "The NEXTAUTH_SECRET is now synchronized between frontend and backend."
echo ""

