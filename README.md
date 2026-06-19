# AirdOps: Enterprise AI-Ready Data Platform

**Local data tooling for ingestion, trust metrics, evaluation and experimentation.**

AirdOps (local edition) focuses on four core capabilities that you can run locally: data ingestion, trust metrics (quality scoring), evaluation tooling, and an interactive playground for experimentation. This repository is not deployed to a public production instance — you must set it up and run it locally (see Getting Started).


## Features (current)

- Ingestion: connectors and file uploads for bringing data into the system
- Trust Metrics: multi-dimensional data quality and AI trust scoring (15+ metrics)
- Evaluation: run evaluations, generate reports and metrics for datasets
- Playground: interactive UI for exploring, querying, and prototyping with ingested data
- Local-first: intended for local development and testing — no public production instance


## Demo Video

[![Demo Video](https://img.youtube.com/vi/QLyesqhu2do/hqdefault.jpg)](https://www.youtube.com/watch?v=QLyesqhu2do&t=22s)


---

## Table of Contents

1. [Platform Overview](#platform-overview)
2. [Architecture & Technology Stack](#architecture--technology-stack)
3. [Core Capabilities](#core-capabilities)
4. [Getting Started](#getting-started)
5. [Technical Documentation](#technical-documentation)
6. [Deployment Guide](#deployment-guide)
7. [API Reference](#api-reference)
8. [Enterprise Features](#enterprise-features)

---

## Platform Overview

### What is AirdOps?

AirdOps is an enterprise-grade data processing platform that transforms unstructured and structured data sources into AI-ready formats. The platform handles the complete data lifecycle—from ingestion and preprocessing to vectorization and quality assessment—enabling organizations to build production-ready RAG (Retrieval-Augmented Generation) applications and AI systems with confidence.

### Key Value Propositions

- **AI-Ready Data Pipeline**: Automated ingestion, preprocessing, chunking, embedding, and indexing workflows
- **Quality Assurance**: 15+ dimensional quality scoring with automated optimization recommendations
- **Enterprise Architecture**: Microservices design with scalable, containerized components
- **Production-Ready**: Built-in monitoring, error handling, and compliance features

### Deployment

This repository is intended for local development and testing. There is no public production instance for this edition — you should run the stack locally (see Getting Started / Quick Local Setup & Run). The repository includes Docker Compose manifests and local env examples to help bring up required services.

---

## Architecture & Technology Stack

### System Architecture

AirdOps follows a **microservices architecture** with clear separation of concerns:

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
                            │ HTTPS/REST API
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
│ Task         │  │ Quality      │  │ MinIO
│ Scheduling   │  │ Scoring      │  │ (Objects)    │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Technology Stack

#### Frontend
- **Framework**: Next.js 13+ (App Router)
- **Language**: TypeScript
- **UI Library**: React 18+ with custom components
- **Authentication**: NextAuth.js (Google OAuth, Email/Password)
- **Styling**: Tailwind CSS
- **Build**: Docker multi-stage builds with standalone output

#### Backend
- **Framework**: FastAPI 0.104+
- **Language**: Python 3.11+ (compatible with 3.12)
- **Database ORM**: SQLAlchemy 2.0.23
- **Migrations**: Alembic 1.12.1

#### Data Processing
- **Orchestration**: Apache Airflow 2.x
- **Vector Database**: Qdrant 1.16.2+
- **Object Storage**: MinIO
- **Embedding Models**:
  - OpenAI: `text-embedding-3-small` (1536 dim), `text-embedding-3-large` (3072 dim)
  - Open Source: MiniLM, MPNet, BGE, GTE, E5, Instructor (384-1024 dim)
- **ML Libraries**: Sentence Transformers 2.7+, OpenAI SDK 1.0+

#### Database
- **Primary**: PostgreSQL 13+ (metadata, users, products, configurations, S3 paths for large content)
- **Vector**: Qdrant (embeddings, chunk metadata, search indices)
- **Object**: MinIO (raw files, processed data, artifacts, large JSON/YAML/text content)
  - Enterprise hierarchical structure: `ws/{workspace_id}/prod/{product_id}/v/{version}/...`
  - Hybrid storage: Small data in DB, large data in S3 with path references

---

## Core Capabilities

### 1. Data Ingestion & Connectors

AirdOps supports multiple data source types with extensible connector architecture:

#### Supported Data Sources

- **Web Scraping**: URL-based content extraction with configurable depth
- **File System**: Local and remote folder synchronization
- **Cloud Storage**:
  - AWS S3 (via boto3)
  - Azure Blob Storage (via azure-storage-blob)
  - Google Cloud Storage (via google-cloud-storage)
- **Google Drive**: Direct integration with Google Drive API
- **File Uploads**: Direct browser-based file upload (PDF, TXT, DOCX, etc.)

#### Connector Features

- **Incremental Sync**: Track changes and sync only new/updated files
- **Metadata Preservation**: Maintain file metadata, timestamps, and structure
- **Error Handling**: Robust retry logic and error reporting
- **Progress Tracking**: Real-time sync status and file counts

### 2. Data Processing Pipeline

The AIRD (AI-Ready Data) pipeline consists of modular stages orchestrated by Apache Airflow:

#### Pipeline Stages

1. **Ingestion Stage**
   - Connects to data sources
   - Downloads/uploads files to object storage
   - Creates metadata records in database
   - Tracks file status and versions

2. **Preprocessing Stage**
   - Text normalization and cleaning
   - OCR error correction (optional)
   - Metadata extraction
   - Content type detection
   - Playbook-based transformations

3. **Chunking Stage**
   - Intelligent document chunking
   - Multiple strategies: fixed-size, semantic, recursive
   - Configurable overlap and size limits
   - Section-aware chunking for structured documents

4. **Scoring Stage**
   - 15+ dimensional quality metrics
   - Trust score calculation
   - Security assessment (PII detection)
   - Metadata completeness evaluation
   - Knowledge base readiness scoring

5. **Embedding Generation**
   - Model-agnostic embedding pipeline
   - Adaptive batch sizing based on model dimensions
   - Supports OpenAI and open-source models
   - Dimension validation and error handling

6. **Vector Indexing**
   - Qdrant collection management
   - Metadata-rich payload storage
   - Access control list (ACL) integration
   - Efficient bulk indexing operations

7. **Quality Validation**
   - Enterprise data quality rules (7 rule types)
   - Violation detection and reporting
   - Compliance checking
   - Policy evaluation

8. **Artifact Generation**
   - Validation summaries (CSV)
   - Trust reports (PDF)
   - Fingerprint JSON files
   - Export-ready bundles

### 3. AI Readiness Assessment

#### Quality Metrics (15+ Dimensions)

**Core Metrics**:
- **AI Trust Score**: Aggregated quality indicator (0-100)
- **Quality Score**: Content quality and structure
- **Completeness**: Data coverage and gaps
- **Security Score**: PII detection and redaction effectiveness
- **Metadata Presence**: Completeness of metadata fields
- **Knowledge Base Readiness**: Suitability for RAG applications

**Advanced Metrics**:
- Chunk coverage analysis
- Duplicate rate tracking
- Content structure validation
- Language detection and validation
- Format compliance

#### Optimization Recommendations

The platform provides actionable recommendations to improve data quality:

- **Quality Normalization**: Enhanced text cleaning (+15-25% improvement)
- **Error Correction**: OCR and typo fixes (+5-10% improvement)
- **Metadata Extraction**: Automated metadata enrichment (+5-15% improvement)
- **Chunk Overlap Optimization**: Context preservation improvements (+3-7% improvement)
- **Playbook Selection**: Content-type-specific preprocessing strategies

**Impact**: Organizations achieving >85% quality scores see **4x efficiency gains** in AI applications compared to 70-85% quality data.

### 4. Vectorization & Embeddings

#### Supported Embedding Models

**OpenAI Models** (requires API key):
- `text-embedding-3-small`: 1536 dimensions
- `text-embedding-3-large`: 3072 dimensions

**Open-Source Models** (via Sentence Transformers):
- **MiniLM**: 384 dimensions (`minilm`, `minilm-l12`)
- **MPNet**: 768 dimensions (`mpnet-base-v2`)
- **BGE Models**: 384/768/1024 dimensions (`bge-small-en`, `bge-base-en`, `bge-large-en`)
- **E5 Models**: 384/768/1024 dimensions (`e5-small`, `e5-base`, `e5-large`)
- **GTE Models**: 384/768/1024 dimensions (`gte-small`, `gte-base`, `gte-large`)
- **Instructor Models**: 768 dimensions (`instructor-base`, `instructor-large`)
- **Multilingual Models**: Various dimensions for non-English content

#### Embedding Configuration

- **Adaptive Batching**: Automatically adjusts batch sizes based on model dimensions
  - 1024+ dim: Batch size 3
  - 768+ dim: Batch size 10
  - <768 dim: Batch size 32
- **Dimension Validation**: Ensures query and index embeddings use compatible dimensions
- **Model Versioning**: Tracks embedding model versions for compatibility

### 5. Enterprise Data Quality Management

#### Data Quality Rule Types

1. **Required Fields**: Ensures critical fields are present
2. **Max Duplicate Rate**: Prevents excessive duplication
3. **Min Chunk Coverage**: Ensures adequate content coverage
4. **Bad Extensions**: Blocks problematic file types
5. **Max File Size**: Controls file size limits
6. **Content Validation**: Validates content quality and structure
7. **Custom Rules**: User-defined validation logic

#### Quality Management Features

- **Real-time Evaluation**: Rules evaluated during pipeline execution
- **Violation Tracking**: Comprehensive violation reporting with severity levels
- **Audit Trail**: Complete history of rule changes with user attribution
- **Compliance Reporting**: Regulatory compliance status tracking
- **Database-First Architecture**: ACID-compliant rule management

### 6. Policy Evaluation System

Policy evaluation serves as a quality gate to ensure data meets production standards:

#### Policy Thresholds (Configurable)

| Metric | Default Threshold | Purpose |
|--------|------------------|---------|
| **AI Trust Score** | ≥ 50% | Overall quality indicator |
| **Security Score** | ≥ 90% | PII handling compliance |
| **Metadata Presence** | ≥ 80% | Metadata completeness |
| **Knowledge Base Ready** | ≥ 50% | RAG application suitability |

#### Policy Status

- **PASSED**: All metrics meet thresholds → Product status: `READY`
- **FAILED**: One or more metrics below thresholds → Product status: `FAILED_POLICY`
- **WARNINGS**: Passes but suboptimal → Product status: `READY_WITH_WARNINGS`

---

## Getting Started

### Prerequisites

- **Python**: 3.11+ (3.12 compatible)
- **Node.js**: 18+
- **Docker**: 20.10+ and Docker Compose 2.0+
- **Git**: 2.30+
- **System Resources**:
  - RAM: Minimum 8GB, Recommended 16GB+
  - Storage: Minimum 10GB free space
  - CPU: 4+ cores recommended

### Quick Start (Local Development)

Follow these steps to run the repository locally. This edition is local-first — install Docker Desktop and use the provided `Makefile` targets to bring up services and start the app.

1) Install prerequisites

- Install Docker Desktop (Docker Engine + Docker Compose) and ensure it is running.
- Install Python 3.11+, Node.js 18+, and Git.

2) Clone and install dependencies

```bash
git clone https://github.com/neelam53yadav/airdops.git
cd aird

# Create Python virtual environment
python -m venv venv
source venv/bin/activate   # On Windows (PowerShell/CMD): venv\Scripts\activate

# Install backend and frontend deps via Makefile
make install
```

3) Configure environment files

You must update environment files for each component before starting services:

- Backend: `backend/.env` or `backend/.env.local` (copy from `backend/env.example`)
- Frontend: `ui/.env.local` (copy from `ui/.env.local.example` or `ui/.env` if present)
- Infrastructure (Docker services): `infra/.env` (copy from `infra/services.example.env`)

Examples:

Windows (PowerShell/CMD):

```powershell
copy backend\env.example backend\.env
copy ui\.env.local.example ui\.env.local  # if example exists
copy infra\services.example.env infra\.env
```

Unix/macOS:

```bash
cp backend/env.example backend/.env
cp ui/.env.local.example ui/.env.local   # if example exists
cp infra/services.example.env infra/.env
```

Edit the three files (`backend/.env`, `ui/.env.local`, `infra/.env`) and fill values for database, MinIO, Qdrant and secrets (JWT / NEXTAUTH_SECRET). Use the "Configuration" section below for expected variables.

4) Start local services and app (use Makefile targets)

```bash
# Start Docker services (Postgres, MinIO, Qdrant, etc.)
make services

# Run DB migrations
make migrate

# Start backend server (loads backend/.env.local or backend/.env)
make backend

# In a separate terminal, start frontend
make frontend
```

Notes:
- `make setup` runs install + services + migrations in one go.
- Use `make stop` to bring services down and `make clean` to remove volumes.
- Use `make backend-env` and `make frontend-env` to sanity-check which env files are loaded by the Makefile.



## Quick Troubleshooting

- Backend not starting: check `backend/.env` and ensure DB and Qdrant URLs are reachable.
- Docker Compose failures: run `docker-compose -f infra/docker-compose.yml --env-file infra/.env ps` and inspect logs with `docker-compose logs -f SERVICE`.
- Frontend auth issues: ensure `ui/.env.local` contains a valid `NEXTAUTH_SECRET` and `NEXT_PUBLIC_API_URL` points to the backend.
- Alembic errors: ensure the `DATABASE_URL` in `backend/.env` matches a running Postgres instance and credentials are correct.

If you want, I can also add a small GIF or upload a demo MP4 to `docs/` and wire the thumbnail and link for you.

### Configuration

#### Required Environment Variables

**Backend (`backend/.env`)**:
```env
# Database
DATABASE_URL=postgresql://primedata:password@localhost:5432/primedata

# Object Storage (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_SECURE=false

# Vector Database (Qdrant)
QDRANT_URL=http://localhost:6333

# Authentication
JWT_SECRET_KEY=<generate-64-char-secret>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# CORS
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]

```

**Frontend (`ui/.env.local`)**:
```env
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Infrastructure (`infra/.env`)**:
```env
# PostgreSQL
POSTGRES_USER=primedata
POSTGRES_PASSWORD=<secure-password>
POSTGRES_DB=primedata

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<secure-password>

# Airflow
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=<secure-password>
AIRFLOW_SECRET_KEY=<generate-secret>
```

---

**AirdOps** - Enterprise AI-Ready Data Platform
*Transform data into production-ready AI applications with confidence.*
