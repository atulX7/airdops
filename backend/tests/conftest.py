"""
Pytest configuration and fixtures for PrimeData tests.
"""

import pytest
import os
import sys
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from primedata.db.database import Base, get_db
from primedata.db.models import User, Workspace, Product, PipelineRun
from primedata.core.settings import get_settings


@pytest.fixture(scope="session")
def test_db_url():
    """Get test database URL."""
    return os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def test_engine(test_db_url):
    """Create test database engine."""
    if test_db_url.startswith("sqlite"):
        engine = create_engine(
            test_db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(test_db_url)
    return engine


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    Base.metadata.create_all(bind=test_engine)
    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user."""
    user = User(
        email="test@example.com",
        name="Test User",
        auth_provider="simple",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_workspace(db_session: Session, test_user):
    """Create a test workspace."""
    from primedata.db.models import WorkspaceMember, WorkspaceRole
    
    workspace = Workspace(
        name="Test Workspace",
    )
    db_session.add(workspace)
    db_session.flush()  # Flush to get workspace.id
    
    # Add user as workspace owner
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=test_user.id,
        role=WorkspaceRole.OWNER,
    )
    db_session.add(member)
    db_session.commit()
    db_session.refresh(workspace)
    return workspace


@pytest.fixture
def test_product(db_session: Session, test_workspace, test_user):
    """Create a test product."""
    product = Product(
        workspace_id=test_workspace.id,
        owner_user_id=test_user.id,
        name="Test Product",
        status="draft",
        current_version=0,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


@pytest.fixture
def mock_minio_client(monkeypatch):
    """Mock MinIO client for testing."""
    from unittest.mock import MagicMock
    
    mock_client = MagicMock()
    mock_client.put_bytes.return_value = True
    mock_client.get_bytes.return_value = b"test content"
    mock_client.get_json.return_value = {}
    mock_client.list_objects.return_value = []
    mock_client.presign.return_value = "https://example.com/presigned-url"
    
    monkeypatch.setattr("primedata.storage.minio_client.MinIOClient", lambda: mock_client)
    return mock_client


@pytest.fixture
def mock_qdrant_client(monkeypatch):
    """Mock Qdrant client for testing."""
    from unittest.mock import MagicMock
    
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.ensure_collection.return_value = True
    mock_client.upsert_points.return_value = True
    mock_client.search_points.return_value = []
    mock_client.list_collections.return_value = []
    mock_client.get_collection_info.return_value = {"points_count": 0, "vectors_count": 0}
    
    monkeypatch.setattr("primedata.indexing.qdrant_client.QdrantClient", lambda: mock_client)
    return mock_client




