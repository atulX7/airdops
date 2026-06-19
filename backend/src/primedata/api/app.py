"""
FastAPI application for PrimeData API.
"""

import asyncio
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from primedata.api.acl import router as acl_router  # M5
from primedata.api.ai_readiness import router as ai_readiness_router
from primedata.api.analytics import router as analytics_router
from primedata.api.artifacts import router as artifacts_router
from primedata.api.auth import router as auth_router
from primedata.api.billing import router as billing_router
from primedata.api.chat import router as chat_router
from primedata.api.contact import router as contact_router
from primedata.api.data_quality import router as data_quality_router
from primedata.api.datasources import router as datasources_router
from primedata.api.embedding_models import router as embedding_models_router
from primedata.api.exports import router as exports_router
from primedata.api.pipeline import router as pipeline_router
from primedata.api.playbooks import router as playbooks_router  # M1
from primedata.api.playground import router as playground_router
from primedata.api.products import router as products_router
from primedata.api.rag_evaluation import router as rag_evaluation_router
from primedata.api.lineage import router as lineage_router
from primedata.api.settings import router as settings_router
from primedata.api.team import router as team_router
from primedata.core.auth_middleware import AuthMiddleware
from primedata.core.settings import get_settings
from primedata.db.database import engine, get_db
from sqlalchemy import text
from sqlalchemy.orm import Session

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="AIRDops API",
    description="AI-ready data from any source",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,  # Disable automatic trailing slash redirects to prevent 307 errors
)

# Configure CORS
# Ensure CORS_ORIGINS is a list
cors_origins = settings.CORS_ORIGINS
if isinstance(cors_origins, str):
    cors_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
else:
    cors_origins = [str(o).strip() for o in cors_origins]

# Log CORS configuration for debugging
from loguru import logger

logger.info(f"Configuring CORS with origins: {cors_origins}")

# Add no-auth middleware (provides local system user)
app.add_middleware(AuthMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,  # Using Authorization header only, no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(datasources_router)
app.include_router(artifacts_router)
app.include_router(pipeline_router)
app.include_router(playground_router)
app.include_router(chat_router)  # RAG Chat endpoint
app.include_router(ai_readiness_router)
app.include_router(embedding_models_router)
app.include_router(data_quality_router)
app.include_router(exports_router, prefix="/api/v1/exports", tags=["exports"])
app.include_router(billing_router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(playbooks_router)  # M1
app.include_router(acl_router)  # M5
app.include_router(settings_router)
app.include_router(team_router)  # Team management
app.include_router(rag_evaluation_router)  # RAG Evaluation (AI-Ready metrics)
app.include_router(contact_router)  # Contact form (public endpoint)
app.include_router(lineage_router)


async def check_database() -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Database connection failed: {str(e)}"}


async def check_qdrant() -> Dict[str, Any]:
    """Check Qdrant connectivity."""
    try:
        import os

        import httpx

        # Use Docker service name or localhost for local dev
        qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        qdrant_port = os.getenv("QDRANT_PORT", "6333")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{qdrant_host}:{qdrant_port}/", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy", "message": "Qdrant is accessible"}
            else:
                return {"status": "unhealthy", "message": f"Qdrant returned status {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Qdrant connection failed: {str(e)}"}


async def check_storage() -> Dict[str, Any]:
    """Check storage connectivity (GCS or MinIO)."""
    try:
        import os

        use_gcs = os.getenv("USE_GCS", "false").lower() == "true"

        if use_gcs:
            # Check GCS by verifying bucket access
            try:
                from primedata.storage.minio_client import minio_client

                # Try to list objects in the primary bucket to verify connectivity
                buckets = ["primedata-raw", "primedata-clean", "primedata-chunk"]
                accessible_buckets = 0

                for bucket_name in buckets:
                    try:
                        # Check if bucket exists and is accessible
                        # Access the gcs_client directly (it's initialized in __init__)
                        if hasattr(minio_client, "gcs_client") and minio_client.gcs_client:
                            bucket = minio_client.gcs_client.bucket(bucket_name)
                            if bucket.exists():
                                accessible_buckets += 1
                    except Exception:
                        pass

                if accessible_buckets > 0:
                    return {
                        "status": "healthy",
                        "message": f"GCS is accessible ({accessible_buckets}/{len(buckets)} buckets accessible)",
                    }
                else:
                    return {"status": "degraded", "message": "GCS client initialized but buckets may not be accessible"}
            except Exception as e:
                return {"status": "unhealthy", "message": f"GCS connection failed: {str(e)}"}
        else:
            # Check MinIO for local development
            import httpx

            minio_host = os.getenv("MINIO_HOST", "minio")
            if ":" in minio_host:
                # If MINIO_HOST includes port, use it as-is
                minio_url = f"http://{minio_host}/minio/health/live"
            else:
                minio_url = f"http://{minio_host}:9000/minio/health/live"

            async with httpx.AsyncClient() as client:
                response = await client.get(minio_url, timeout=5.0)
                if response.status_code == 200:
                    return {"status": "healthy", "message": "MinIO is accessible"}
                else:
                    return {"status": "unhealthy", "message": f"MinIO returned status {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Storage connection failed: {str(e)}"}


async def check_airflow() -> Dict[str, Any]:
    """Check Airflow connectivity."""
    try:
        import os

        import httpx

        # Use Docker service name or localhost for local dev
        airflow_host = os.getenv("AIRFLOW_HOST", "airflow-webserver")
        airflow_port = os.getenv("AIRFLOW_PORT", "8080")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{airflow_host}:{airflow_port}/health", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy", "message": "Airflow is accessible"}
            else:
                return {"status": "unhealthy", "message": f"Airflow returned status {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Airflow connection failed: {str(e)}"}


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    # Check all services concurrently
    services = await asyncio.gather(check_database(), check_qdrant(), check_storage(), check_airflow(), return_exceptions=True)

    # Process results
    import os

    use_gcs = os.getenv("USE_GCS", "false").lower() == "true"
    storage_name = "gcs" if use_gcs else "minio"

    service_results = {
        "database": (
            services[0] if not isinstance(services[0], Exception) else {"status": "unhealthy", "message": str(services[0])}
        ),
        "qdrant": (
            services[1] if not isinstance(services[1], Exception) else {"status": "unhealthy", "message": str(services[1])}
        ),
        storage_name: (
            services[2] if not isinstance(services[2], Exception) else {"status": "unhealthy", "message": str(services[2])}
        ),
        "airflow": (
            services[3] if not isinstance(services[3], Exception) else {"status": "unhealthy", "message": str(services[3])}
        ),
    }

    # Determine overall status
    all_healthy = all(service["status"] == "healthy" for service in service_results.values())
    overall_status = "healthy" if all_healthy else "degraded"

    return {
        "status": overall_status,
        "service": "AIRDops",
        "version": "0.1.0",
        "services": service_results,
        "timestamp": asyncio.get_event_loop().time(),
    }


@app.get("/health/simple")
async def simple_health_check():
    """Simple health check endpoint (app only)."""
    return {"status": "ok", "service": "AIRDops", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
