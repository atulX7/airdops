"""
Database configuration and session management.
"""

from primedata.core.settings import get_settings
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get settings
settings = get_settings()

# Get database URL (constructed from components if needed)
database_url = settings.get_database_url()

# Create database engine
engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300, echo=settings.ENV == "development")

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
