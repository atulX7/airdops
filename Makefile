# AIRDops Development Makefile

# Common development tasks for local setup and daily development
#
# NOTE:
# - `make backend` will load backend/.env.local (or backend/.env if .env.local doesn't exist)
# - `make services/stop/clean` uses infra/docker-compose.yml (Docker Compose)
# - If you're using Podman, keep infra services started via your existing flow (run.py dev --services-only)

# Use Python for cross-platform file checks
PYTHON := python

.PHONY: help setup dev install install-backend install-frontend \
        services migrate backend frontend stop clean \
        backend-env frontend-env print-env

# -----------------------------
# Default target
# -----------------------------
help:
	@echo AIRDops Development Commands:
	@echo.
	@echo   make setup        - One-time setup: install deps + services + migrations
	@echo   make install      - Install backend and frontend dependencies
	@echo   make services     - Start/restart Docker services only
	@echo   make migrate      - Run database migrations only
	@echo   make backend      - Start backend server (loads backend/.env.local or backend/.env)
	@echo   make frontend     - Start frontend server
	@echo   make dev          - Show instructions for running dev servers
	@echo   make stop         - Stop all Docker services
	@echo   make clean        - Stop services and remove volumes (destructive)
	@echo.
	@echo Utilities:
	@echo   make backend-env  - Print env vars from backend env file (sanity check)
	@echo   make frontend-env - Print env vars from frontend env file (sanity check)
	@echo   make print-env    - Show effective MINIO_HOST/MINIO_PORT etc (backend load)
	@echo.

# -----------------------------
# Install both backend and frontend dependencies
# -----------------------------
install: install-backend install-frontend

install-backend:
	@echo Installing backend dependencies...
	@echo.
	@$(PYTHON) -c "import os, subprocess, sys; script = 'scripts/install_backend.py'; subprocess.run([sys.executable, script] if os.path.exists(script) else [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd='backend', check=True)"
	@echo.

install-frontend:
	@echo Installing frontend dependencies...
	@echo.
	@cd ui && npm install
	@echo.
	@echo Frontend dependencies installed

# -----------------------------
# One-time setup
# -----------------------------
setup: install
	@echo.
	@echo Starting Docker services...
	@echo.
	@$(PYTHON) -c "import os, subprocess, sys; script = 'run.py'; cmd = [sys.executable, script, 'dev', '--services-only'] if os.path.exists(script) else ['docker', 'compose', 'up', '-d']; subprocess.run(cmd, cwd='infra' if not os.path.exists(script) else '.', check=True)"
	@echo.
	@echo Waiting for services to be ready...
	@$(PYTHON) -c "import time; time.sleep(10)"
	@echo.
	@echo Running database migrations...
	@echo.
	@$(MAKE) migrate
	@echo.
	@echo Setup complete!
	@echo.
	@echo Next steps:
	@echo   Terminal 1: make backend
	@echo   Terminal 2: make frontend
	@echo.

dev:
	@echo Starting development servers...
	@echo.
	@echo Run these commands in separate terminals:
	@echo.
	@echo   Terminal 1 (Backend):
	@echo     make backend
	@echo.
	@echo   Terminal 2 (Frontend):
	@echo     make frontend
	@echo.

# -----------------------------
# Start backend server (ENV LOAD WITH FALLBACK)
# -----------------------------
backend:
	@echo Starting backend server...
	@echo.
	@$(PYTHON) -c "import os; files = ['backend/.env.local', 'backend/.env']; found = any(os.path.exists(f) for f in files); print('WARNING: No backend env file found (checked backend/.env.local and backend/.env)') if not found else None"
	@$(PYTHON) start_backend.py

# -----------------------------
# Start frontend server
# -----------------------------
frontend:
	@echo Starting frontend server...
	@echo.
	@$(PYTHON) -c "import os; files = ['ui/.env.local', 'ui/.env']; found = any(os.path.exists(f) for f in files); print('WARNING: No frontend env file found (checked ui/.env.local and ui/.env)') if not found else None"
	@cd ui && npm run dev

# -----------------------------
# Docker services management
# -----------------------------
services:
	@echo Starting Docker services...
	@echo.
	@$(PYTHON) -c "import os, subprocess, sys; script = 'run.py'; cmd = [sys.executable, script, 'dev', '--services-only'] if os.path.exists(script) else ['docker', 'compose', 'up', '-d']; subprocess.run(cmd, cwd='infra' if not os.path.exists(script) else '.', check=True)"

migrate:
	@echo Running database migrations...
	@cd backend && $(PYTHON) -m alembic upgrade head

stop:
	@echo Stopping Docker services...
	@echo.
	@cd infra && docker compose down

clean:
	@echo Cleaning up Docker services and volumes...
	@echo.
	@echo WARNING: This will remove all Docker volumes and data!
	@echo Press Ctrl+C to cancel, or wait 5 seconds to continue...
	@$(PYTHON) -c "import time; time.sleep(5)"
	@cd infra && docker compose down -v
	@echo.
	@echo Cleanup complete

# -----------------------------
# Utilities (debug / sanity checks)
# -----------------------------
backend-env:
	@$(PYTHON) -c "import os; files = ['backend/.env.local', 'backend/.env']; found = next((f for f in files if os.path.exists(f)), None); print(f'Backend env file: {found}') if found else print('No backend env file found.\nChecked: backend/.env.local and backend/.env'); [print(open(f).read()) for f in files if os.path.exists(f)]"

frontend-env:
	@$(PYTHON) -c "import os; files = ['ui/.env.local', 'ui/.env']; found = next((f for f in files if os.path.exists(f)), None); print(f'Frontend env file: {found}') if found else print('No frontend env file found.\nChecked: ui/.env.local and ui/.env'); [print(open(f).read()) for f in files if os.path.exists(f)]"

print-env:
	@echo Effective backend env:
	@$(PYTHON) -c "import os; from pathlib import Path; env_files = [Path('backend/.env.local'), Path('backend/.env')]; env_file = next((f for f in env_files if f.exists()), None); env_vars = {}; [env_vars.update({k.strip(): v.strip() for k, v in [line.split('=', 1) for line in f.read_text().split('\n') if '=' in line and not line.strip().startswith('#')]}) for f in [env_file] if env_file]; os.environ.update(env_vars); print(f'  MINIO_HOST={os.getenv(\"MINIO_HOST\", \"<unset>\")}'); print(f'  MINIO_PORT={os.getenv(\"MINIO_PORT\", \"<unset>\")}'); print(f'  S3_ENDPOINT={os.getenv(\"S3_ENDPOINT\", \"<unset>\")}')"
