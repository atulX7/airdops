"""
Artifacts API router for listing and accessing stored data.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from primedata.core.scope import ensure_product_access, ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.storage.minio_client import minio_client
from primedata.storage.paths import raw_prefix
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/artifacts", tags=["Artifacts"])
logger = logging.getLogger(__name__)


class ArtifactInfo(BaseModel):
    name: str
    size: int
    last_modified: str
    url: str
    content_type: Optional[str] = None


class RawArtifactsResponse(BaseModel):
    artifacts: List[ArtifactInfo]
    total_files: int
    total_bytes: int
    prefix: str


@router.get("/raw", response_model=RawArtifactsResponse)
async def list_raw_artifacts(
    request: Request,
    product_id: UUID = Query(..., description="Product ID"),
    version: Optional[int] = Query(None, description="Version number (defaults to latest)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List raw artifacts for a product and version.
    """
    # Get the product
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Ensure user has access to the product
    ensure_product_access(db, request, product_id)

    # Determine version
    if version is None:
        version = product.current_version

    # Generate prefix
    prefix = raw_prefix(product.workspace_id, product_id, version)

    # Also include artifacts (M3: validation summary and trust report)
    artifacts_prefix = f"ws/{product.workspace_id}/prod/{product_id}/v/{version}/artifacts/"

    # List objects from MinIO
    try:
        objects = minio_client.list_objects("primedata-raw", prefix)

        artifacts = []
        total_bytes = 0

        # Process raw artifacts
        for obj in objects:
            # Generate presigned URL
            presigned_url = minio_client.presign("primedata-raw", obj["name"], expiry=3600)

            if presigned_url:
                artifacts.append(
                    ArtifactInfo(
                        name=obj["name"].split("/")[-1],  # Just the filename
                        size=obj["size"],
                        last_modified=obj["last_modified"] if obj["last_modified"] else "",
                        url=presigned_url,
                        content_type=obj.get("content_type"),
                    )
                )
                total_bytes += obj["size"]

        # Add artifacts from primedata-exports bucket (M3: validation summary and trust report)
        try:
            artifact_objects = minio_client.list_objects("primedata-exports", artifacts_prefix)
            for obj in artifact_objects:
                presigned_url = minio_client.presign("primedata-exports", obj["name"], expiry=3600)
                if presigned_url:
                    artifacts.append(
                        ArtifactInfo(
                            name=obj["name"].split("/")[-1],  # Just the filename
                            size=obj["size"],
                            last_modified=obj["last_modified"] if obj["last_modified"] else "",
                            url=presigned_url,
                            content_type=obj.get("content_type"),
                        )
                    )
                    total_bytes += obj["size"]
        except Exception as e:
            logger.warning(f"Failed to list artifacts from exports bucket: {e}")

        return RawArtifactsResponse(artifacts=artifacts, total_files=len(artifacts), total_bytes=total_bytes, prefix=prefix)

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list artifacts: {str(e)}")
