# AirdOps: Enterprise AI-Ready Data Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.16%2B-red.svg)](https://qdrant.tech/)

**Local data tooling for ingestion, trust metrics, evaluation and experimentation.**

AirdOps transforms unstructured and structured data sources into AI-ready formats. The platform handles the complete data lifecycle — from ingestion and preprocessing to vectorization and quality assessment — enabling you to build production-ready RAG (Retrieval-Augmented Generation) applications with confidence.

## Demo Video

[![Demo Video](https://img.youtube.com/vi/QLyesqhu2do/hqdefault.jpg)](https://www.youtube.com/watch?v=QLyesqhu2do&t=22s)

---

## Table of Contents

1. [Features](#features)
2. [Architecture & Technology Stack](#architecture--technology-stack)
3. [Project Structure](#project-structure)
4. [Getting Started](#getting-started)
5. [Running Tests](#running-tests)
6. [API Reference](#api-reference)
7. [Core Capabilities](#core-capabilities)
8. [Roadmap](#roadmap)
9. [Contributing](#contributing)
10. [Security](#security)
11. [License](#license)
12. [Acknowledgements](#acknowledgements)

---

## Features

- **Ingestion** — Connectors and file uploads for bringing data into the system (S3, Azure Blob, Google Drive, Web, File Upload)
- **Trust Metrics** — Multi-dimensional data quality and AI trust scoring (15+ metrics)
- **Evaluation** — RAG evaluation framework with datasets, runs, and quality gates
- **Playground** — Interactive UI for exploring, querying, and prototyping with ingested data
- **Pipeline Orchestration** — Apache Airflow DAGs for automated data processing workflows
- **Vector Search** — Qdrant-powered semantic search with reranking
- **Data Lineage** — Full traceability from raw file to vector embedding
- **Local-first** — Intended for local development and testing with Docker Compose

---

## Architecture & Technology Stack

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Layer                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Next.js Frontend (React/TypeScript)               │    │
│  │  - Server-side rendering                           │    │
│  │  - NextAuth.js authentication                      │    │
│  │  - Real-time UI updates                            │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway Layer                         │
│  ┌────────────────────────────────────────────────────┐    │
│  │  FastAPI Backend (Python 3.11+)                    │    │
│  │  - RESTful API endpoints                           │    │
│  │  - JWT authentication                              │    │
│  │  - Request validation & routing                    │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Orchestration│  │  Processing  │  │   Storage    │
│              │  │              │  │              │
│ Apache       │  │ AIRD Pipeline│  │ PostgreSQL   │
│ Airflow      │  │ Stages       │  │ (Metadata)   │
│              │  │              │  │              │
│ DAG-based    │  │ Embedding    │  │ Qdrant       │
│ Workflows    │  │ Generation   │  │ (Vectors)    │
│              │  │              │  │              │
│ Task         │  │ Quality      │  │ MinIO        │
│ Scheduling   │  │ Scoring      │  │ (Objects)    │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS |
| **Backend** | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic |
| **Orchestration** | Apache Airflow 2.x |
| **Vector DB** | Qdrant 1.16.2+ |
| **Database** | PostgreSQL 15 |
| **Object Storage** | MinIO (S3-compatible) |
| **Embeddings** | OpenAI, Sentence Transformers (MiniLM, BGE, E5, GTE, MPNet, Instructor) |
| **Containerization** | Docker & Docker Compose |

---

## Project Structure

```
airdops/
├── backend/                    # FastAPI backend
│   ├── src/primedata/
│   │   ├── api/                # REST API endpoints (18 routers)
│   │   ├── core/               # Auth, settings, security
│   │   ├── db/                 # SQLAlchemy models & database
│   │   ├── connectors/         # Data source connectors (S3, Azure, GDrive, Web)
│   │   ├── ingestion_pipeline/ # AIRD pipeline stages & DAG tasks
│   │   ├── evaluation/         # RAG evaluation framework
│   │   ├── services/           # Business logic services
│   │   ├── indexing/           # Embedding & Qdrant indexing
│   │   └── storage/            # MinIO/S3 client
│   ├── alembic/                # Database migrations
│   ├── tests/                  # Unit, integration & e2e tests
│   └── config/                 # Scoring weights & configuration
├── ui/                         # Next.js frontend
│   ├── app/                    # App Router pages
│   ├── components/             # React components
│   └── lib/                    # API client, utilities, constants
├── infra/                      # Infrastructure
│   ├── docker-compose.yml      # Service definitions
│   ├── airflow/                # Airflow DAGs & Dockerfile
│   ├── init/                   # DB init scripts, MinIO bucket setup
│   └── scripts/                # Deployment & setup scripts
├── Makefile                    # Development commands
├── run.py                      # Dev/prod wrapper script
└── LICENSE
```

---

## Getting Started

### Prerequisites

- **Python** 3.11+ (3.12 compatible)
- **Node.js** 18+
- **Docker** 20.10+ and Docker Compose 2.0+
- **Git** 2.30+
- **System Resources**: 8GB RAM minimum (16GB+ recommended), 10GB disk, 4+ CPU cores

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/atulX7/airdops.git
cd airdops

# 2. Create Python virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
make install

# 4. Configure environment files
cp backend/env.example backend/.env
cp infra/.env.example infra/.env
# Edit both files with your credentials (see Configuration below)

# 5. Start Docker services (Postgres, MinIO, Qdrant, Airflow)
make services

# 6. Run database migrations
make migrate

# 7. Start backend (Terminal 1)
make backend

# 8. Start frontend (Terminal 2)
make frontend
```

The app will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc
- **MinIO Console**: http://localhost:9001
- **Airflow UI**: http://localhost:8080

### Configuration

#### Backend (`backend/.env`)

```env
DATABASE_URL=postgresql://primedata:password@localhost:5432/primedata
MINIO_HOST=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_SECURE=false
QDRANT_HOST=localhost
QDRANT_PORT=6333
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

#### Frontend (`ui/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

#### Infrastructure (`infra/.env`)

```env
POSTGRES_USER=primedata
POSTGRES_PASSWORD=<secure-password>
POSTGRES_DB=primedata
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<secure-password>
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=<secure-password>
AIRFLOW_SECRET_KEY=<generate-secret>
```

### Makefile Commands

| Command | Description |
|---------|-------------|
| `make setup` | One-time setup: install + services + migrations |
| `make install` | Install backend and frontend dependencies |
| `make services` | Start Docker services |
| `make migrate` | Run database migrations |
| `make backend` | Start backend server |
| `make frontend` | Start frontend dev server |
| `make stop` | Stop Docker services |
| `make clean` | Stop services and remove volumes (destructive) |

### Troubleshooting

- **Backend not starting**: Verify `backend/.env` and ensure DB/Qdrant URLs are reachable.
- **Docker Compose failures**: Run `docker compose -f infra/docker-compose.yml ps` and inspect logs with `docker compose logs -f <service>`.
- **Frontend issues**: Ensure `ui/.env.local` has correct `NEXT_PUBLIC_API_URL` pointing to backend.
- **Alembic errors**: Ensure `DATABASE_URL` matches a running Postgres instance.

---

## Running Tests

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with markers
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests
pytest -m e2e           # End-to-end tests

# Run specific test file
pytest tests/test_trust_scoring.py

# Run with coverage (requires pytest-cov)
pytest --cov=primedata --cov-report=html
```

### Frontend

```bash
cd ui

# Lint
npm run lint

# Type check
npm run type-check
```

---

## API Reference

AirdOps provides auto-generated interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check (all dependencies) |
| `GET` | `/api/v1/products/` | List all products |
| `POST` | `/api/v1/products` | Create a new product |
| `POST` | `/api/v1/pipeline/run` | Trigger pipeline execution |
| `GET` | `/api/v1/pipeline/runs` | List pipeline runs |
| `POST` | `/api/v1/playground/query` | Query the RAG playground |
| `POST` | `/api/v1/chat/query` | RAG chat query |
| `GET` | `/api/v1/analytics/products/{id}/trust-metrics` | Get trust metrics |
| `GET` | `/api/v1/lineage/{id}/overview` | Get data lineage overview |
| `POST` | `/api/v1/rag-evaluation/runs` | Create evaluation run |
| `GET` | `/api/v1/embedding-models/` | List available embedding models |

---

## Core Capabilities

### Data Ingestion & Connectors

| Connector | Description |
|-----------|-------------|
| **File Upload** | Direct browser-based upload (PDF, TXT, DOCX, etc.) |
| **AWS S3** | S3-compatible storage via boto3 |
| **Azure Blob** | Azure Blob Storage integration |
| **Google Drive** | Google Drive API integration |
| **Web Scraping** | URL-based content extraction |
| **Folder Sync** | Local/remote folder synchronization |

### AIRD Pipeline Stages

1. **Ingestion** — Download files, store in object storage, create metadata records
2. **Preprocessing** — Text normalization, OCR correction, content type detection
3. **Chunking** — Intelligent document chunking (fixed-size, semantic, recursive)
4. **Scoring** — 15+ quality metrics, trust score calculation, PII detection
5. **Embedding** — Model-agnostic embedding generation (OpenAI + open-source)
6. **Indexing** — Qdrant vector indexing with ACL integration
7. **Validation** — Enterprise data quality rules, violation reporting
8. **Artifacts** — Validation summaries (CSV), trust reports (PDF), fingerprint JSON

### Domain Playbooks

Pre-configured processing strategies for specific content types:

`TECH` | `LEGAL` | `MEDICAL` | `HEALTHCARE` | `FINANCIAL` | `ACADEMIC` | `REGULATORY` | `ECOMMERCE` | `RETAIL` | `SCANNED`

### AI Trust Score (15+ Dimensions)

- AI Trust Score (aggregated 0-100)
- Quality Score, Completeness, Security Score
- Metadata Presence, Knowledge Base Readiness
- Chunk Coverage, Duplicate Rate, Content Structure
- Language Detection, Format Compliance

### Policy Evaluation

| Metric | Default Threshold | Purpose |
|--------|------------------|---------|
| AI Trust Score | >= 50% | Overall quality indicator |
| Security Score | >= 90% | PII handling compliance |
| Metadata Presence | >= 80% | Metadata completeness |
| Knowledge Base Ready | >= 50% | RAG application suitability |

### Embedding Models

**OpenAI** (requires API key): `text-embedding-3-small` (1536d), `text-embedding-3-large` (3072d)

**Open-Source** (via Sentence Transformers): MiniLM (384d), MPNet (768d), BGE (384-1024d), E5 (384-1024d), GTE (384-1024d), Instructor (768d)

---

## Roadmap

- [ ] CI/CD pipeline with GitHub Actions
- [ ] Production deployment guide (Kubernetes / Cloud Run)
- [ ] Additional connectors (Confluence, SharePoint, Notion)
- [ ] Real-time streaming pipeline support
- [ ] Multi-language embedding support
- [ ] Advanced analytics dashboard
- [ ] Plugin architecture for custom pipeline stages
- [ ] Webhook notifications for pipeline events

---

## Contributing

We welcome contributions to AirdOps! Here's how you can contribute:

1. **Fork** the repository to your account.
2. **Create a new branch** for your feature or bug fix (`git checkout -b feature/my-feature`).
3. **Implement your changes** and ensure all tests pass.
4. **Follow coding standards** — Python: PEP 8, TypeScript: ESLint.
5. **Submit a pull request** detailing your changes.
6. After review, your contributions may be merged into the main codebase.

### Development Tips

- Run `pytest` before submitting to ensure backend tests pass.
- Run `npm run lint && npm run type-check` in `ui/` for frontend validation.
- Use meaningful commit messages describing the "why" not just the "what".
- Check existing [issues](https://github.com/atulX7/airdops/issues) for things to work on.

---

## Security

If you discover a security vulnerability, please report it responsibly. **Do not open a public issue.** Instead, email [atul@xtechstacks.com](mailto:atul@xtechstacks.com) with details of the vulnerability. We will respond within 48 hours and work with you to resolve it.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

Built with these excellent open-source technologies:

- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python web framework
- [Next.js](https://nextjs.org/) — React framework for production
- [Qdrant](https://qdrant.tech/) — Vector search engine
- [Apache Airflow](https://airflow.apache.org/) — Workflow orchestration
- [PostgreSQL](https://www.postgresql.org/) — Relational database
- [MinIO](https://min.io/) — S3-compatible object storage
- [Sentence Transformers](https://www.sbert.net/) — State-of-the-art embeddings
- [SQLAlchemy](https://www.sqlalchemy.org/) — Python SQL toolkit
- [Tailwind CSS](https://tailwindcss.com/) — Utility-first CSS framework

---

**AirdOps** — Enterprise AI-Ready Data Platform
*Transform data into production-ready AI applications with confidence.*
