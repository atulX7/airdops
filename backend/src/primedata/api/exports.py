"""
Export bundle API endpoints for PrimeData.

This module provides endpoints for creating and managing export bundles
that contain chunked data, embeddings, and provenance information.
"""

import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.scope import ensure_product_access
from ..core.security import get_current_user
from ..db.database import get_db
from ..db.models import Product, Workspace
from ..indexing.qdrant_client import QdrantClient
from ..storage.minio_client import minio_client
from ..storage.paths import chunk_prefix, embed_prefix, export_prefix

router = APIRouter()


class ExportBundleResponse(BaseModel):
    """Response model for export bundle information."""

    id: str
    product_id: str
    version: int
    bundle_name: str
    size_bytes: int
    created_at: str
    download_url: Optional[str] = None


class CreateExportRequest(BaseModel):
    """Request model for creating an export bundle."""

    version: Optional[Union[int, str]] = None  # None means current version, "prod" means promoted version


class CreateExportResponse(BaseModel):
    """Response model for export creation."""

    bundle_id: str
    bundle_name: str
    size_bytes: int
    created_at: str
    download_url: str


@router.post("/{product_id}/create", response_model=CreateExportResponse)
async def create_export_bundle(
    product_id: str,
    request_body: CreateExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create an export bundle for a product.

    Args:
        product_id: ID of the product to export
        request_body: Export creation request with optional version
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user

    Returns:
        Export bundle information with download URL
    """
    try:
        from uuid import UUID

        # Ensure user has access to the product
        product = ensure_product_access(db, request, UUID(product_id))

        # Determine version to export
        if request_body.version is None:
            # Use current version
            version = product.current_version
        elif request_body.version == "prod":
            # Use promoted version
            version = product.promoted_version or product.current_version
        elif isinstance(request_body.version, int):
            # Use specified version
            version = request_body.version
        else:
            # Invalid version format
            raise HTTPException(status_code=400, detail="Invalid version format. Use integer, 'prod', or null")

        if not version:
            raise HTTPException(status_code=400, detail="No version available for export")

        # Get workspace
        workspace = db.query(Workspace).filter(Workspace.id == product.workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Create export bundle
        try:
            bundle_info = await _create_export_bundle(
                workspace_id=str(workspace.id), product_id=product_id, version=version, product_name=product.name
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create export bundle: {str(e)}")

        return CreateExportResponse(
            bundle_id=bundle_info["bundle_id"],
            bundle_name=bundle_info["bundle_name"],
            size_bytes=bundle_info["size_bytes"],
            created_at=bundle_info["created_at"],
            download_url=bundle_info["download_url"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create export bundle: {str(e)}")


@router.get("", response_model=List[ExportBundleResponse])
async def list_export_bundles(
    request: Request,
    product_id: str = Query(..., description="Product ID to list exports for"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List export bundles for a product.

    Args:
        product_id: ID of the product to list exports for
        request: FastAPI request object
        db: Database session
        current_user: Current authenticated user

    Returns:
        List of export bundles with download URLs
    """
    try:
        from uuid import UUID

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))

        # Get workspace
        workspace = db.query(Workspace).filter(Workspace.id == product.workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # List export bundles from MinIO
        # Use a general prefix to find all exports for this product
        export_prefix_path = f"ws/{workspace.id}/prod/{product_id}/"
        export_objects = minio_client.list_objects("primedata-exports", export_prefix_path)

        bundles = []
        for obj in export_objects:
            if obj.get("name", "").endswith(".zip"):
                # Extract bundle information from object name
                bundle_name = os.path.basename(obj["name"])
                bundle_id = bundle_name.replace(".zip", "")

                # Try to extract version from bundle name or use current version as fallback
                version = product.current_version
                if "v" in bundle_id:
                    try:
                        # Extract version from bundle name like "bundle-20250126_123456-v7"
                        version_part = bundle_id.split("-v")[-1]
                        version = int(version_part)
                    except (ValueError, IndexError):
                        # If extraction fails, use current version
                        version = product.current_version

                # Generate presigned download URL
                download_url = minio_client.presign("primedata-exports", obj["name"], expiry=3600)  # 1 hour

                bundles.append(
                    ExportBundleResponse(
                        id=bundle_id,
                        product_id=product_id,
                        version=version,
                        bundle_name=bundle_name,
                        size_bytes=obj.get("size", 0),
                        created_at=obj.get("last_modified", "").replace("T", " ").replace("+00:00", ""),
                        download_url=download_url,
                    )
                )

        # Sort by creation date (newest first)
        bundles.sort(key=lambda x: x.created_at, reverse=True)

        return bundles

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list export bundles: {str(e)}")


async def _create_export_bundle(workspace_id: str, product_id: str, version: int, product_name: str) -> Dict[str, Any]:
    """
    Create an export bundle containing chunked data, embeddings, and provenance.

    Args:
        workspace_id: Workspace ID
        product_id: Product ID
        version: Version to export
        product_name: Name of the product

    Returns:
        Bundle information including ID, name, size, and download URL
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    bundle_id = f"bundle-{timestamp}-v{version}"
    bundle_name = f"{bundle_id}.zip"

    # Create temporary directory for bundle assembly
    with tempfile.TemporaryDirectory() as temp_dir:
        bundle_path = Path(temp_dir) / bundle_name

        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Gather chunked data (JSONL format)
            await _add_chunked_data(zip_file, workspace_id, product_id, version)

            # 2. Gather embedding data (Parquet format)
            await _add_embedding_data(zip_file, workspace_id, product_id, version)

            # 3. Create provenance.json
            await _add_provenance_info(zip_file, workspace_id, product_id, version, product_name)

            # 4. Add Qdrant collection info if available
            await _add_qdrant_info(zip_file, workspace_id, product_id, version)

        # Upload bundle to MinIO
        # Use a general export path for this product
        bundle_key = f"ws/{workspace_id}/prod/{product_id}/exports/{bundle_name}"

        with open(bundle_path, "rb") as f:
            bundle_data = f.read()
            minio_client.put_object("primedata-exports", bundle_key, bundle_data)

        # Get bundle size
        bundle_size = bundle_path.stat().st_size

        # Generate presigned download URL
        download_url = minio_client.presign("primedata-exports", bundle_key, expiry=3600)  # 1 hour

        return {
            "bundle_id": bundle_id,
            "bundle_name": bundle_name,
            "size_bytes": bundle_size,
            "created_at": datetime.utcnow().isoformat(),
            "download_url": download_url,
        }


async def _add_chunked_data(zip_file: zipfile.ZipFile, workspace_id: str, product_id: str, version: int):
    """Add chunked data in JSONL format to the export bundle."""
    try:
        chunk_prefix_path = chunk_prefix(workspace_id, product_id, version)
        chunk_objects = minio_client.list_objects("primedata-chunk", chunk_prefix_path)

        if chunk_objects:
            # Create JSONL file with all chunks
            jsonl_content = []
            for obj in chunk_objects:
                chunk_data = minio_client.get_object("primedata-chunk", obj["name"])
                if chunk_data:
                    chunk_info = json.loads(chunk_data)
                    jsonl_content.append(chunk_info)

            # Write JSONL content
            jsonl_content_str = "\n".join(json.dumps(item) for item in jsonl_content)
            zip_file.writestr("chunks.jsonl", jsonl_content_str)

    except Exception as e:
        # Add empty file if chunks not available
        zip_file.writestr("chunks.jsonl", "")


async def _add_embedding_data(zip_file: zipfile.ZipFile, workspace_id: str, product_id: str, version: int):
    """Add embedding data in Parquet format to the export bundle."""
    try:
        embed_prefix_path = embed_prefix(workspace_id, product_id, version)
        embed_objects = minio_client.list_objects("primedata-embed", embed_prefix_path)

        if embed_objects:
            # Create a simple JSON representation of embeddings
            # In a real implementation, you'd want to use proper Parquet format
            embedding_data = []
            for obj in embed_objects:
                embed_data = minio_client.get_object("primedata-embed", obj["name"])
                if embed_data:
                    embed_info = json.loads(embed_data)
                    embedding_data.append(embed_info)

            # Write embeddings as JSON (for now)
            embeddings_json = json.dumps(embedding_data, indent=2)
            zip_file.writestr("embeddings.json", embeddings_json)

    except Exception as e:
        # Add empty file if embeddings not available
        zip_file.writestr("embeddings.json", "[]")


async def _add_provenance_info(zip_file: zipfile.ZipFile, workspace_id: str, product_id: str, version: int, product_name: str):
    """Add provenance information to the export bundle."""
    provenance = {
        "export_info": {
            "product_id": product_id,
            "product_name": product_name,
            "workspace_id": workspace_id,
            "version": version,
            "exported_at": datetime.utcnow().isoformat(),
            "export_type": "full_bundle",
        },
        "data_sources": {"chunks": "chunks.jsonl", "embeddings": "embeddings.json"},
        "metadata": {"created_by": "primedata_export_api", "api_version": "1.0", "bundle_format": "zip"},
    }

    zip_file.writestr("provenance.json", json.dumps(provenance, indent=2))


async def _add_qdrant_info(zip_file: zipfile.ZipFile, workspace_id: str, product_id: str, version: int):
    """Add Qdrant collection information to the export bundle."""
    try:
        # Get Qdrant collection info
        qdrant_client = QdrantClient()
        collection_name = f"ws_{workspace_id}_prod_{product_id}_v{version}"

        qdrant_info = {
            "collection_name": collection_name,
            "collection_info": "Collection metadata would be included here",
            "note": "Full Qdrant snapshot not included in this bundle",
        }

        zip_file.writestr("qdrant_info.json", json.dumps(qdrant_info, indent=2))

    except Exception as e:
        # Add minimal info if Qdrant not available
        qdrant_info = {
            "collection_name": f"ws_{workspace_id}_prod_{product_id}_v{version}",
            "status": "unavailable",
            "error": str(e),
        }
        zip_file.writestr("qdrant_info.json", json.dumps(qdrant_info, indent=2))
