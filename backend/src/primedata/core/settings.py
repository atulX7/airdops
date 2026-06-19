"""
Application settings and configuration.
"""

import json
import os
from typing import List, Optional, Union

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for pydantic v1
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Environment
    ENV: str = "development"

    # Database Configuration
    # Option 1: Full DATABASE_URL (preferred - simplest)
    # Option 2: Individual components (fallback - more flexible, allows database name from secrets)
    DATABASE_URL: Optional[str] = None  # Primary: full connection string
    
    # Individual components (used if DATABASE_URL not set)
    # ⚠️ WARNING: All components must be set via environment variables or .env file!
    # Values are read from Settings instance attributes (loaded from .env or environment)
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_HOST: str = "localhost"  # Default fallback
    POSTGRES_PORT: int = 5432  # Default fallback
    POSTGRES_DB: Optional[str] = None  # ⚠️ MUST be set via POSTGRES_DB environment variable or .env file!
    
    def get_database_url(self) -> str:
        """
        Get database URL, constructing from components if DATABASE_URL not set.
        
        Priority:
        1. DATABASE_URL from settings (loaded from .env or environment)
        2. Construct from POSTGRES_* components (if all set)
        3. Raise error if insufficient configuration
        """
        # Read DATABASE_URL from settings (loaded from .env or environment)
        if self.DATABASE_URL:
            return self.DATABASE_URL
        
        # Otherwise, construct from individual components
        user = self.POSTGRES_USER
        password = self.POSTGRES_PASSWORD
        host = self.POSTGRES_HOST
        port = self.POSTGRES_PORT
        db_name = self.POSTGRES_DB
        
        if not all([user, password, db_name]):
            missing = []
            if not user:
                missing.append("POSTGRES_USER")
            if not password:
                missing.append("POSTGRES_PASSWORD")
            if not db_name:
                missing.append("POSTGRES_DB")
            raise ValueError(
                f"Database configuration required! Either set DATABASE_URL, "
                f"or set all of: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB. "
                f"Missing environment variables: {', '.join(missing)}. "
                f"See backend/env.example for configuration template."
            )
        
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"

    # CORS - can be set via environment variable as JSON array or comma-separated string
    # Example: CORS_ORIGINS='["http://localhost:3000","https://airdops.com"]'
    # Or: CORS_ORIGINS=http://localhost:3000,https://airdops.com
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000", "https://airdops.com", "https://www.airdops.com"]

    # Authentication (no-auth mode)
    LOCAL_AUTH_BYPASS: bool = True
    JWT_ISSUER: str = "https://api.local/auth"
    JWT_AUDIENCE: str = "primedata-api"


    # Storage Configuration
    USE_GCS: bool = False  # Set to True to use GCS instead of MinIO

    # MinIO Configuration (for local development)
    # ⚠️ WARNING: Default credentials are for local dev only. Set MINIO_SECRET_KEY environment variable for production!
    # BaseSettings automatically reads from environment variables matching these field names
    MINIO_HOST: str = "localhost:9000"
    # ⚠️ WARNING: Default contains placeholder. Set MINIO_ACCESS_KEY environment variable for production!
    MINIO_ACCESS_KEY: str = "changeme"
    MINIO_SECRET_KEY: str = "CHANGE_ME"
    MINIO_SECURE: bool = False

    # GCS Configuration (for production, uses Application Default Credentials)
    GCS_PROJECT_ID: Optional[str] = None  # GCP Project ID (optional, for reference)

    # Qdrant Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334

    # Airflow Configuration
    AIRFLOW_URL: str = "http://localhost:8080"
    AIRFLOW_USERNAME: Optional[str] = None
    AIRFLOW_PASSWORD: Optional[str] = None
    AIRFLOW_HOST: str = "localhost"  # For internal service communication
    AIRFLOW_PORT: int = 8080

    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = None  # OpenAI API key for embedding models

    # AIRD Configuration (M0)
    AIRD_PLAYBOOK_DIR: str = ""  # Path to playbook directory (empty = auto-detect)
    AIRD_SCORING_WEIGHTS_PATH: str = ""  # Path to scoring weights JSON (empty = auto-detect)

    # Playground reranking pipeline
    RERANKER_NAME: str = "BAAI/bge-reranker-base"  # Cross-encoder model; fallback to MiniLM if GPU unavailable
    RERANK_TOP_K: int = 5  # Number of results to return after reranking
    DENSE_RETRIEVAL_TOP_K: int = 50  # Dense (Qdrant) retrieval candidate count
    BM25_TOP_K: int = 50  # Optional BM25 retrieval candidate count when available
    USE_BM25: bool = False  # Enable BM25 retrieval and merge with dense (requires sparse index)

    # Email Configuration (SMTP)
    SMTP_ENABLED: bool = False  # Set to True to enable email sending
    SMTP_HOST: str = "smtp.gmail.com"  # SMTP server hostname
    SMTP_PORT: int = 587  # SMTP server port (587 for TLS, 465 for SSL, 25 for plain)
    SMTP_USE_TLS: bool = True  # Use TLS encryption
    SMTP_USE_SSL: bool = False  # Use SSL encryption (alternative to TLS)
    SMTP_USERNAME: Optional[str] = None  # SMTP username (usually your email)
    SMTP_PASSWORD: Optional[str] = None  # SMTP password or app-specific password
    SMTP_FROM_EMAIL: str = "noreply@primedata.com"  # From email address
    SMTP_TO_EMAIL: Optional[str] = None  # Recipient email for contact/feedback forms (defaults to SMTP_USERNAME if not set)
    FRONTEND_URL: str = "https://airdops.com"  # Frontend URL for email links

    class Config:
        env_file = [".env.local", ".env"]  # Try .env.local first, then .env
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env (for backward compatibility during migration)


# Global settings instance
_settings: Settings = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
        # Parse CORS_ORIGINS from environment if it's a string
        cors_origins_env = os.getenv("CORS_ORIGINS")
        if cors_origins_env:
            try:
                # Try parsing as JSON array first
                parsed = json.loads(cors_origins_env)
                if isinstance(parsed, list):
                    _settings.CORS_ORIGINS = parsed
                else:
                    # If JSON but not a list, treat as single value
                    _settings.CORS_ORIGINS = [str(parsed)]
            except (json.JSONDecodeError, ValueError):
                # If not JSON, treat as comma-separated string
                origins_list = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
                if origins_list:
                    _settings.CORS_ORIGINS = origins_list
                else:
                    # Single value
                    _settings.CORS_ORIGINS = [cors_origins_env.strip()]
        # Ensure CORS_ORIGINS is always a list
        if isinstance(_settings.CORS_ORIGINS, str):
            _settings.CORS_ORIGINS = [_settings.CORS_ORIGINS]

        # Debug logging (remove in production if needed)
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"CORS_ORIGINS configured: {_settings.CORS_ORIGINS}")
    return _settings
