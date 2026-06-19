"""
Integration tests for Playground search: mandatory filters and product isolation.

Ensures that:
- Every search uses mandatory filters: workspace_id, product_id, version, collection_id.
- A query for product A never returns chunks from product B.

Note: These tests require a database that supports UUID (e.g. PostgreSQL). They are skipped
when using SQLite (default in-memory) unless TEST_DATABASE_URL is set to a Postgres URL.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from fastapi import Request
from sqlalchemy.orm import Session

from primedata.db.models import Product, PipelineRun, PipelineRunStatus, User, Workspace
from primedata.api.playground import query_playground, PlaygroundQuery

# Skip entire module when using SQLite (UUID type not supported)
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
requires_pg = pytest.mark.skipif(
    TEST_DB_URL.startswith("sqlite"),
    reason="Playground isolation tests require PostgreSQL (UUID support); set TEST_DATABASE_URL",
)


def _make_point(product_id: str, workspace_id: str, version: int, collection_id: str, chunk_label: str):
    return {
        "id": f"{product_id}_{chunk_label}",
        "score": 0.9,
        "payload": {
            "chunk_id": f"chunk-{chunk_label}",
            "text": f"Content for {chunk_label}",
            "filename": "doc.pdf",
            "source_file": "doc.pdf",
            "page": 1,
            "section": "general",
            "product_id": product_id,
            "workspace_id": workspace_id,
            "version": version,
            "collection_id": collection_id,
        },
    }


def _filter_points_by_conditions(points: list, filter_conditions: dict, limit: int):
    """Simulate Qdrant: return only points whose payload matches all filter_conditions."""
    if not filter_conditions:
        return points[:limit]
    out = []
    for p in points:
        payload = p.get("payload", {})
        match = True
        for key, value in filter_conditions.items():
            if payload.get(key) != value:
                match = False
                break
        if match:
            out.append(p)
        if len(out) >= limit:
            break
    return out


@pytest.fixture
def workspace_and_user(db_session: Session):
    from primedata.db.models import WorkspaceMember, WorkspaceRole
    user = User(email="playground-test@example.com", name="Test", auth_provider="simple", is_active=True)
    db_session.add(user)
    db_session.flush()
    workspace = Workspace(name="Playground Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER)
    db_session.add(member)
    db_session.commit()
    db_session.refresh(workspace)
    db_session.refresh(user)
    return workspace, user


@pytest.fixture
def product_a(db_session: Session, workspace_and_user):
    workspace, user = workspace_and_user
    product = Product(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        name="ProductA",
        status="draft",
        current_version=1,
        playbook_id="TECH",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


@pytest.fixture
def product_b(db_session: Session, workspace_and_user):
    workspace, user = workspace_and_user
    product = Product(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        name="ProductB",
        status="draft",
        current_version=1,
        playbook_id="TECH",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


@pytest.fixture
def pipeline_run_a(db_session: Session, product_a):
    run = PipelineRun(
        product_id=product_a.id,
        version=1,
        status=PipelineRunStatus.SUCCESS,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


@pytest.fixture
def mock_request(workspace_and_user):
    _, user = workspace_and_user
    req = MagicMock(spec=Request)
    req.state.user = {"sub": str(user.id)}
    return req


@requires_pg
def test_playground_search_mandatory_filters(
    db_session: Session,
    product_a: Product,
    pipeline_run_a,
    mock_request: Request,
):
    """Playground search must send workspace_id, product_id, version, collection_id to Qdrant."""
    collection_name = f"ws_{product_a.workspace_id}__producta__v_1"
    call_args = {}

    def capture_search(collection_name_, query_vector, limit=10, score_threshold=None, filter_conditions=None):
        call_args["collection_name"] = collection_name_
        call_args["filter_conditions"] = filter_conditions
        return []

    with patch("primedata.api.playground.QdrantClient") as MockQdrant:
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.find_collection_name.return_value = collection_name
        mock_client.get_collection_info.return_value = {"config": {"vector_size": 384}}
        mock_client.search_points.side_effect = capture_search
        mock_client.scroll_points.return_value = {"points": [], "next_page_offset": None}
        MockQdrant.return_value = mock_client

        with patch("primedata.api.playground.get_latest_successful_pipeline_version", return_value=1):
            with patch("primedata.api.playground.EmbeddingGenerator") as MockEmb:
                MockEmb.return_value.embed.return_value = [0.1] * 384
                inst = MockEmb.return_value
                inst.get_model_info.return_value = {"model_type": "test", "fallback_mode": False}

                query_data = PlaygroundQuery(
                    product_id=str(product_a.id),
                    query="test query",
                    top_k=5,
                    use="current",
                )
                response = query_playground(
                    query_data=query_data,
                    request=mock_request,
                    current_user=mock_request.state.user,
                    db=db_session,
                )

    assert response.total_results == 0
    assert "filter_conditions" in call_args
    fc = call_args["filter_conditions"]
    assert fc is not None
    assert "workspace_id" in fc
    assert "product_id" in fc
    assert "version" in fc
    assert "collection_id" in fc
    assert fc["product_id"] == str(product_a.id)
    assert fc["collection_id"] == collection_name


@requires_pg
def test_playground_query_product_a_never_returns_product_b_chunks(
    db_session: Session,
    product_a: Product,
    product_b: Product,
    pipeline_run_a,
    mock_request: Request,
):
    """A query for product A must never return chunks belonging to product B."""
    ws_id = str(product_a.workspace_id)
    coll_a = f"ws_{product_a.workspace_id}__producta__v_1"
    coll_b = f"ws_{product_b.workspace_id}__productb__v_1"

    # Points for product A and product B (as if both were in the same collection - worst case)
    points_pool = [
        _make_point(str(product_a.id), ws_id, 1, coll_a, "a1"),
        _make_point(str(product_a.id), ws_id, 1, coll_a, "a2"),
        _make_point(str(product_b.id), ws_id, 1, coll_b, "b1"),
        _make_point(str(product_b.id), ws_id, 1, coll_b, "b2"),
    ]

    def search_points(collection_name_, query_vector, limit=10, score_threshold=None, filter_conditions=None):
        filtered = _filter_points_by_conditions(points_pool, filter_conditions, limit)
        return filtered

    with patch("primedata.api.playground.QdrantClient") as MockQdrant:
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.find_collection_name.return_value = coll_a
        mock_client.get_collection_info.return_value = {"config": {"vector_size": 384}}
        mock_client.search_points.side_effect = search_points
        mock_client.scroll_points.return_value = {"points": [], "next_page_offset": None}
        MockQdrant.return_value = mock_client

        with patch("primedata.api.playground.get_latest_successful_pipeline_version", return_value=1):
            with patch("primedata.api.playground.EmbeddingGenerator") as MockEmb:
                MockEmb.return_value.embed.return_value = [0.1] * 384
                inst = MockEmb.return_value
                inst.get_model_info.return_value = {"model_type": "test", "fallback_mode": False}

                query_data = PlaygroundQuery(
                    product_id=str(product_a.id),
                    query="test query",
                    top_k=10,
                    use="current",
                )
                response = query_playground(
                    query_data=query_data,
                    request=mock_request,
                    current_user=mock_request.state.user,
                    db=db_session,
                )

    # All returned results must belong to product A (mandatory filter ensures B is excluded)
    product_b_id = str(product_b.id)
    for r in response.results:
        pid = r.meta.get("product_id")
        assert pid is not None, "result meta should include product_id"
        assert pid != product_b_id, "query for product A must never return chunks from product B"
        assert pid == str(product_a.id), "every chunk must belong to the queried product A"
