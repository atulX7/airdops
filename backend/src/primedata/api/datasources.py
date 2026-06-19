"""
DataSources API router.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from primedata.api.billing import check_billing_limits, calculate_workspace_raw_files_size_mb
from primedata.core.plan_limits import get_plan_limit
from primedata.connectors.azure_blob import AzureBlobConnector
from primedata.connectors.folder import FolderConnector
from primedata.connectors.google_drive import GoogleDriveConnector
from primedata.connectors.s3 import S3Connector
from primedata.connectors.web import WebConnector
from primedata.core.scope import ensure_product_access, ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import DataSource, DataSourceType, Product, RawFile, RawFileStatus
from primedata.ingestion_pipeline.artifact_registry import calculate_checksum
from primedata.storage.minio_client import minio_client
from primedata.storage.paths import raw_prefix, safe_filename
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/datasources", tags=["DataSources"])


class DataSourceCreateRequest(BaseModel):
    workspace_id: UUID
    product_id: UUID
    name: Optional[str] = "Unnamed Data Source"
    type: DataSourceType
    config: Dict[str, Any] = {}


class DataSourceUpdateRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    workspace_id: UUID
    product_id: UUID
    name: str
    type: DataSourceType
    config: Dict[str, Any]
    last_cursor: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str


class TestConfigRequest(BaseModel):
    type: DataSourceType
    config: Dict[str, Any]


class SyncFullRequest(BaseModel):
    version: Optional[int] = None


class SyncFullResponse(BaseModel):
    version: int
    files: int
    bytes: int
    errors: int
    duration: float
    prefix: str
    details: Dict[str, Any]


@router.post("/", response_model=DataSourceResponse)
async def create_datasource(
    request_body: DataSourceCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new data source for a product.
    """
    # Ensure user has access to the product and its workspace
    product = ensure_product_access(db, request, request_body.product_id)

    # Verify that the provided workspace_id matches the product's workspace
    if product.workspace_id != request_body.workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace ID does not match product's workspace")

    # Check billing limits for data source creation
    current_datasource_count = db.query(DataSource).filter(DataSource.product_id == request_body.product_id).count()

    if not check_billing_limits(str(product.workspace_id), "max_data_sources_per_product", current_datasource_count, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data source limit exceeded. Please upgrade your plan to add more data sources.",
        )

    # Create new data source
    datasource = DataSource(
        workspace_id=request_body.workspace_id,
        product_id=request_body.product_id,
        name=request_body.name or "Unnamed Data Source",
        type=request_body.type,
        config=request_body.config,
    )

    db.add(datasource)
    db.commit()
    db.refresh(datasource)

    return DataSourceResponse.model_validate(datasource)


@router.get("/", response_model=List[DataSourceResponse])
async def list_datasources(
    request: Request,
    product_id: Optional[UUID] = Query(None, description="Filter by product ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List data sources. If product_id is provided, filter by that product.
    Otherwise, return data sources from all accessible workspaces.
    """
    from primedata.core.scope import allowed_workspaces

    if product_id:
        # Ensure user has access to the product and get the product's workspace
        product = ensure_product_access(db, request, product_id)
        # Filter by product_id directly - ensure_product_access already verified access
        query = db.query(DataSource).filter(DataSource.product_id == product_id)
    else:
        # No product_id provided - filter by allowed workspaces
        allowed_workspace_ids = allowed_workspaces(request, db)
        query = db.query(DataSource).filter(DataSource.workspace_id.in_(allowed_workspace_ids))

    datasources = query.all()
    return [DataSourceResponse.model_validate(datasource) for datasource in datasources]


@router.get("/{datasource_id}", response_model=DataSourceResponse)
async def get_datasource(
    datasource_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Get a specific data source by ID.
    """
    # Get the data source
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    # Ensure user has access to the product
    ensure_product_access(db, request, datasource.product_id)

    return DataSourceResponse.model_validate(datasource)


@router.patch("/{datasource_id}", response_model=DataSourceResponse)
async def update_datasource(
    datasource_id: UUID,
    request_body: DataSourceUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update a data source's configuration.
    """
    # Get the data source
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    # Ensure user has access to the product
    ensure_product_access(db, request, datasource.product_id)

    # Update name if provided
    if request_body.name is not None:
        datasource.name = request_body.name

    # Update configuration
    if request_body.config is not None:
        datasource.config = request_body.config

    db.commit()
    db.refresh(datasource)

    return DataSourceResponse.model_validate(datasource)


def _test_connector_config(datasource_type: DataSourceType, config: Dict[str, Any]) -> Tuple[bool, str]:
    """Helper function to test connector configuration."""
    try:
        if datasource_type.value == "web":
            # Convert single URL to list format expected by WebConnector
            test_config = config.copy()
            if "url" in test_config and "urls" not in test_config:
                test_config["urls"] = [test_config["url"]]

            connector = WebConnector(test_config)
            success, message = connector.test_connection()
            return success, message

        elif datasource_type.value == "folder":
            # Check if this is upload mode (no path provided) or path mode
            has_path = config.get("path") or config.get("root_path")

            if not has_path:
                # Upload mode - no path needed, files will be uploaded via API
                return True, "Folder datasource configured for file uploads. Use the upload endpoint to add files."

            # Path mode - test the server-side path
            # Convert 'path' to 'root_path' format expected by FolderConnector
            test_config = config.copy()
            if "path" in test_config and "root_path" not in test_config:
                test_config["root_path"] = test_config["path"]

            # Convert 'file_types' to 'include' patterns
            if "file_types" in test_config and "include" not in test_config:
                file_types = test_config["file_types"]
                if isinstance(file_types, str):
                    # Split comma-separated file types
                    test_config["include"] = [ft.strip() for ft in file_types.split(",") if ft.strip()]
                elif isinstance(file_types, list):
                    test_config["include"] = file_types
                else:
                    test_config["include"] = ["*"]  # Default to all files

            connector = FolderConnector(test_config)
            success, message = connector.test_connection()
            return success, message

        elif datasource_type.value == "aws_s3":
            connector = S3Connector(config)
            success, message = connector.test_connection()
            return success, message

        elif datasource_type.value == "azure_blob":
            connector = AzureBlobConnector(config)
            success, message = connector.test_connection()
            return success, message

        elif datasource_type.value == "google_drive":
            connector = GoogleDriveConnector(config)
            success, message = connector.test_connection()
            return success, message

        else:
            return False, f"Test connection not supported for data source type: {datasource_type.value}"
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Test connection failed: {str(e)}")
        return False, f"Test connection failed: {str(e)}"


@router.post("/test-config", response_model=TestConnectionResponse)
async def test_config(request_body: TestConfigRequest, current_user: dict = Depends(get_current_user)):
    """
    Test connection configuration without creating a data source.
    """
    try:
        success, message = _test_connector_config(request_body.type, request_body.config)
        return TestConnectionResponse(ok=success, message=message)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Test config endpoint error: {str(e)}", exc_info=True)
        return TestConnectionResponse(ok=False, message=f"Error testing configuration: {str(e)}")


@router.post("/{datasource_id}/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    datasource_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Test connection to a data source using connector dispatch.
    """
    # Get the data source
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    # Ensure user has access to the product
    ensure_product_access(db, request, datasource.product_id)

    # Test connection using helper function
    success, message = _test_connector_config(datasource.type, datasource.config)
    return TestConnectionResponse(ok=success, message=message)


@router.post("/{datasource_id}/sync-full", response_model=SyncFullResponse)
async def sync_full(
    datasource_id: UUID,
    request_body: SyncFullRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Perform full synchronization of a data source.

    This endpoint:
    1. Syncs files from the data source to storage (GCS or MinIO)
    2. Creates RawFile records in the database
    3. Updates product version if needed
    4. Updates data source last_cursor with sync details

    For folder datasources in upload mode (no root_path), queries existing
    uploaded files from the current version and processes them for the new version.
    """
    # Get the data source
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    # Ensure user has access to the product
    ensure_product_access(db, request, datasource.product_id)

    # Get the product to determine version
    product = db.query(Product).filter(Product.id == datasource.product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Determine version
    version = request_body.version or (product.current_version or 0) + 1

    # Generate output prefix
    output_prefix = raw_prefix(datasource.workspace_id, datasource.product_id, version)

    # Dispatch to appropriate connector
    try:
        if datasource.type.value == "web":
            # Convert single URL to list format expected by WebConnector
            config = datasource.config.copy()
            if "url" in config and "urls" not in config:
                config["urls"] = [config["url"]]

            connector = WebConnector(config)
            result = connector.sync_full("primedata-raw", output_prefix)

        elif datasource.type.value == "folder":
            # Convert 'path' to 'root_path' format expected by FolderConnector
            config = datasource.config.copy()
            root_path = config.get("root_path") or config.get("path", "")

            # Special handling for upload mode (no root_path configured)
            if not root_path:
                import logging

                logger = logging.getLogger(__name__)
                logger.info(f"Folder datasource {datasource_id} in upload mode - querying existing uploaded files")

                # Query existing RawFile records for this datasource
                # Check all versions, not just current_version, since files might have been uploaded
                # before current_version was set, or to version 1 when current_version was None
                # First try current_version, then try version 1, then try any version
                current_version = product.current_version or 1

                # Try to find files in current_version first
                existing_files = (
                    db.query(RawFile).filter(RawFile.data_source_id == datasource_id, RawFile.version == current_version).all()
                )

                logger.info(f"Querying for files in version {current_version}: found {len(existing_files)} files")

                # If no files found in current_version, try version 1 (common case when product is new)
                if len(existing_files) == 0 and current_version != 1:
                    existing_files = (
                        db.query(RawFile).filter(RawFile.data_source_id == datasource_id, RawFile.version == 1).all()
                    )
                    logger.info(f"No files in version {current_version}, trying version 1: found {len(existing_files)} files")
                    if len(existing_files) > 0:
                        current_version = 1  # Update to use version 1 for the rest of the logic

                # If still no files, try any version (last resort)
                if len(existing_files) == 0:
                    logger.info("No files found in current_version or version 1, trying any version...")
                    any_version_files = (
                        db.query(RawFile)
                        .filter(RawFile.data_source_id == datasource_id)
                        .order_by(RawFile.version.desc())
                        .limit(1)
                        .all()
                    )
                    logger.info(f"Query for any version returned {len(any_version_files)} file(s)")

                    if any_version_files:
                        # Use the version of the most recent file
                        found_file = any_version_files[0]
                        current_version = found_file.version
                        logger.info(
                            f"Found file in version {current_version}: {found_file.filename} (key: {found_file.storage_key})"
                        )

                        existing_files = (
                            db.query(RawFile)
                            .filter(RawFile.data_source_id == datasource_id, RawFile.version == current_version)
                            .all()
                        )
                        logger.info(f"Query for all files in version {current_version} returned {len(existing_files)} file(s)")
                    else:
                        logger.warning(f"No files found for datasource {datasource_id} in any version!")
                        # Check if ANY files exist for this datasource at all
                        total_files = db.query(RawFile).filter(RawFile.data_source_id == datasource_id).count()
                        logger.warning(f"Total files for datasource {datasource_id}: {total_files}")

                logger.info(f"Final: Found {len(existing_files)} files uploaded to version {current_version}")

                if len(existing_files) == 0:
                    logger.warning(f"No RawFile records found for datasource {datasource_id}. Checking storage directly...")
                    # Fallback: List files directly from storage (in case files exist but RawFile records don't)
                    try:
                        storage_objects = minio_client.list_objects("primedata-raw", output_prefix)
                        logger.info(f"Found {len(storage_objects)} files in storage with prefix {output_prefix}")

                        if len(storage_objects) > 0:
                            # Convert storage objects to files_processed format
                            files_processed = []
                            total_bytes = 0

                            for obj in storage_objects:
                                object_key = obj.get("name", "")
                                if object_key.startswith(output_prefix):
                                    filename = object_key[len(output_prefix) :]
                                else:
                                    filename = Path(object_key).name

                                file_size = obj.get("size", 0)
                                files_processed.append(
                                    {
                                        "path": filename,
                                        "key": object_key,
                                        "size": file_size,
                                        "content_type": obj.get("content_type", "application/octet-stream"),
                                    }
                                )
                                total_bytes += file_size

                            logger.info(
                                f"Found {len(files_processed)} files in storage (no RawFile records). Creating result."
                            )

                            result = {
                                "files": len(files_processed),
                                "bytes": total_bytes,
                                "errors": 0,
                                "duration": 0.0,
                                "details": {
                                    "files_processed": files_processed,
                                    "files_failed": [],
                                    "files_skipped": [],
                                    "message": f"Found {len(files_processed)} files in storage (no database records found)",
                                },
                            }
                        else:
                            logger.error(
                                f"No files found in storage or database for datasource {datasource_id}. Files may not have been uploaded yet."
                            )
                            # Return empty result
                            result = {
                                "files": 0,
                                "bytes": 0,
                                "errors": 0,
                                "duration": 0.0,
                                "details": {
                                    "files_processed": [],
                                    "files_failed": [],
                                    "files_skipped": [],
                                    "message": "No files found. Please upload files first using the upload endpoint.",
                                },
                            }
                    except Exception as e:
                        logger.error(f"Error listing files from storage: {e}", exc_info=True)
                        # Return empty result
                        result = {
                            "files": 0,
                            "bytes": 0,
                            "errors": 0,
                            "duration": 0.0,
                            "details": {
                                "files_processed": [],
                                "files_failed": [],
                                "files_skipped": [],
                                "message": f"Error checking storage: {str(e)}",
                            },
                        }
                else:
                    # Convert RawFile records to sync result format
                    files_processed = []
                    total_bytes = 0

                    for raw_file in existing_files:
                        # For the new version, we need to copy the file to the new version's prefix
                        # Generate new key with new version prefix
                        old_key = raw_file.storage_key
                        # Extract filename from old key
                        old_prefix = raw_prefix(datasource.workspace_id, datasource.product_id, current_version)
                        if old_key.startswith(old_prefix):
                            filename = old_key[len(old_prefix) :]
                        else:
                            filename = Path(old_key).name

                        new_key = f"{output_prefix}{filename}"

                        # Copy file to new version location if versions differ
                        file_checksum = raw_file.file_checksum  # Use existing checksum if available
                        if version != current_version:
                            try:
                                # Copy from old location to new location
                                old_content = minio_client.get_bytes("primedata-raw", old_key)
                                if old_content:
                                    # Calculate checksum from content if not already available
                                    if not file_checksum:
                                        file_checksum = calculate_checksum(old_content, algorithm="sha256")

                                    minio_client.put_bytes(
                                        "primedata-raw",
                                        new_key,
                                        old_content,
                                        raw_file.content_type or "application/octet-stream",
                                    )
                                    logger.info(f"Copied file from {old_key} to {new_key}")
                            except Exception as e:
                                logger.warning(f"Failed to copy file {old_key} to {new_key}: {e}")
                                # Continue anyway - we'll use the old key
                                new_key = old_key
                                # If we couldn't copy, use the old file's checksum
                                file_checksum = raw_file.file_checksum

                        files_processed.append(
                            {
                                "path": raw_file.filename,  # Use filename as path
                                "key": new_key,  # Use new key for new version
                                "size": raw_file.file_size or 0,
                                "content_type": raw_file.content_type or "application/octet-stream",
                                "checksum": file_checksum,  # Include checksum in file_info
                            }
                        )
                        total_bytes += raw_file.file_size or 0

                    # Create result in the same format as connector.sync_full
                    result = {
                        "files": len(files_processed),
                        "bytes": total_bytes,
                        "errors": 0,
                        "duration": 0.0,
                        "details": {
                            "files_processed": files_processed,
                            "files_failed": [],
                            "files_skipped": [],
                            "message": f"Found {len(files_processed)} previously uploaded files from version {current_version}",
                        },
                    }
            else:
                # Normal folder sync from server path
                if "path" in config and "root_path" not in config:
                    config["root_path"] = config["path"]

                # Convert 'file_types' to 'include' patterns
                if "file_types" in config and "include" not in config:
                    file_types = config["file_types"]
                    if isinstance(file_types, str):
                        # Split comma-separated file types
                        config["include"] = [ft.strip() for ft in file_types.split(",") if ft.strip()]
                    elif isinstance(file_types, list):
                        config["include"] = file_types
                    else:
                        config["include"] = ["*"]  # Default to all files

                connector = FolderConnector(config)
                result = connector.sync_full("primedata-raw", output_prefix)

        elif datasource.type.value == "aws_s3":
            connector = S3Connector(datasource.config)
            result = connector.sync_full("primedata-raw", output_prefix)

        elif datasource.type.value == "azure_blob":
            connector = AzureBlobConnector(datasource.config)
            result = connector.sync_full("primedata-raw", output_prefix)

        elif datasource.type.value == "google_drive":
            connector = GoogleDriveConnector(datasource.config)
            result = connector.sync_full("primedata-raw", output_prefix)

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sync not supported for data source type: {datasource.type.value}",
            )

        # Check raw files size limit before creating RawFile records
        from primedata.db.models import BillingProfile
        
        billing_profile = db.query(BillingProfile).filter(
            BillingProfile.workspace_id == datasource.workspace_id
        ).first()

        if billing_profile:
            plan_name = billing_profile.plan.value.lower() if hasattr(billing_profile.plan, "value") else str(billing_profile.plan).lower()
            max_size_mb = get_plan_limit(plan_name, "max_raw_files_size_mb")
            
            if max_size_mb != -1:  # If not unlimited
                # Calculate current workspace total size
                current_size_mb = calculate_workspace_raw_files_size_mb(str(datasource.workspace_id), db)
                
                # Calculate new files size from sync result (bytes to MB)
                new_files_bytes = result.get("bytes", 0)
                new_files_size_mb = new_files_bytes / (1024 * 1024)
                
                # Check if adding new files would exceed limit
                total_size_mb = current_size_mb + new_files_size_mb
                
                if total_size_mb > max_size_mb:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Raw files size limit exceeded. Current usage: {current_size_mb:.2f} MB, "
                               f"adding {new_files_size_mb:.2f} MB would exceed the limit of {max_size_mb} MB. "
                               f"Please upgrade your plan or remove some files."
                    )

        # Store raw file records in database
        details = result.get("details", {})

        # Handle both folder connector (files_processed) and web connector (urls_processed)
        files_processed = details.get("files_processed", [])
        urls_processed = details.get("urls_processed", [])

        files_created = 0

        # Process folder connector files
        for file_info in files_processed:
            try:
                # Extract file stem from the original path or MinIO key
                file_path = file_info.get("path", "")
                storage_key = file_info.get("key", "")

                # Get file stem (filename without extension)
                if file_path:
                    file_stem = Path(file_path).stem
                    filename = Path(file_path).name
                elif storage_key:
                    # Extract from storage key if path not available
                    filename = Path(storage_key).name
                    file_stem = Path(storage_key).stem
                else:
                    continue

                # Check if file already exists (avoid duplicates)
                existing = (
                    db.query(RawFile)
                    .filter(
                        RawFile.product_id == datasource.product_id, RawFile.version == version, RawFile.file_stem == file_stem
                    )
                    .first()
                )

                if not existing:
                    # Calculate checksum from file in storage
                    file_checksum = file_info.get("checksum")  # Check if connector provided checksum
                    if not file_checksum and storage_key:
                        try:
                            # Download file to calculate checksum
                            file_content = minio_client.get_bytes("primedata-raw", storage_key)
                            if file_content:
                                file_checksum = calculate_checksum(file_content, algorithm="sha256")
                            else:
                                # Fallback: use a placeholder if we can't read the file
                                logger.warning(f"Could not read file {storage_key} to calculate checksum")
                                file_checksum = ""  # This will fail, but at least we tried
                        except Exception as e:
                            logger.warning(f"Failed to calculate checksum for {storage_key}: {e}")
                            file_checksum = ""  # This will fail, but at least we tried

                    if not file_checksum:
                        raise ValueError(f"Could not determine checksum for file {storage_key}")

                    raw_file = RawFile(
                        workspace_id=datasource.workspace_id,
                        product_id=datasource.product_id,
                        data_source_id=datasource.id,
                        version=version,
                        filename=filename,
                        file_stem=file_stem,
                        storage_key=storage_key,
                        storage_bucket="primedata-raw",
                        file_size=file_info.get("size", 0),
                        content_type=file_info.get("content_type", "application/octet-stream"),
                        status=RawFileStatus.INGESTED,
                        file_checksum=file_checksum,
                    )
                    db.add(raw_file)
                    files_created += 1

            except Exception as e:
                # Log error but don't fail the entire sync
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to store raw file record: {e}")

        # Process web connector files (URLs)
        for url_info in urls_processed:
            try:
                filename = url_info.get("filename", "")
                if not filename:
                    continue

                # Generate storage key from prefix and filename
                storage_key = f"{output_prefix}{filename}"
                file_stem = Path(filename).stem

                # Check if file already exists (avoid duplicates)
                existing = (
                    db.query(RawFile)
                    .filter(
                        RawFile.product_id == datasource.product_id, RawFile.version == version, RawFile.file_stem == file_stem
                    )
                    .first()
                )

                if not existing:
                    # Calculate checksum from file in storage
                    file_checksum = url_info.get("checksum")  # Check if connector provided checksum
                    if not file_checksum:
                        try:
                            # Download file to calculate checksum
                            file_content = minio_client.get_bytes("primedata-raw", storage_key)
                            if file_content:
                                file_checksum = calculate_checksum(file_content, algorithm="sha256")
                            else:
                                logger.warning(f"Could not read file {storage_key} to calculate checksum")
                                file_checksum = ""
                        except Exception as e:
                            logger.warning(f"Failed to calculate checksum for {storage_key}: {e}")
                            file_checksum = ""

                    if not file_checksum:
                        raise ValueError(f"Could not determine checksum for file {storage_key}")

                    raw_file = RawFile(
                        workspace_id=datasource.workspace_id,
                        product_id=datasource.product_id,
                        data_source_id=datasource.id,
                        version=version,
                        filename=filename,
                        file_stem=file_stem,
                        storage_key=storage_key,
                        storage_bucket="primedata-raw",
                        file_size=url_info.get("size", 0),
                        content_type="text/html",  # Web connector stores HTML
                        status=RawFileStatus.INGESTED,
                        file_checksum=file_checksum,
                    )
                    db.add(raw_file)
                    files_created += 1

            except Exception as e:
                # Log error but don't fail the entire sync
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to store raw file record from URL: {e}")

        # Update product version if this was a new version
        if version > (product.current_version or 0):
            product.current_version = version

        # Update data source last_cursor with sync details
        datasource.last_cursor = {
            "last_sync_at": datetime.utcnow().isoformat(),
            "version": version,
            "files_synced": result["files"],
            "bytes_synced": result["bytes"],
            "errors": result["errors"],
            "files_created": files_created,
        }

        db.commit()

        return SyncFullResponse(
            version=version,
            files=result["files"],
            bytes=result["bytes"],
            errors=result["errors"],
            duration=result["duration"],
            prefix=output_prefix,
            details=result["details"],
        )

    except Exception as e:
        db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Sync failed: {str(e)}")


@router.post("/{datasource_id}/upload-files")
async def upload_files(
    datasource_id: UUID,
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload files to a folder-type datasource.
    Files are stored directly in MinIO/GCS and RawFile records are created.
    This bypasses the need for a server-side path.
    """
    # Get the data source
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    # Only allow for folder type
    if datasource.type != DataSourceType.FOLDER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"File upload only supported for folder datasources"
        )

    # Ensure user has access
    ensure_product_access(db, request, datasource.product_id)

    # Get product version
    product = db.query(Product).filter(Product.id == datasource.product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    version = product.current_version or 1
    output_prefix = raw_prefix(datasource.workspace_id, datasource.product_id, version)

    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"Uploading {len(files)} files to datasource {datasource_id}, product {datasource.product_id}, version {version}"
    )

    uploaded_files = []
    errors = []

    for file in files:
        try:
            content = await file.read()
            file_size = len(content)

            # Calculate checksum for integrity validation
            file_checksum = calculate_checksum(content, algorithm="sha256")

            # Generate safe key
            safe_key = safe_filename(file.filename)
            key = f"{output_prefix}{safe_key}"

            # Determine content type
            content_type = file.content_type or "application/octet-stream"

            # Upload directly to MinIO/GCS
            success = minio_client.put_bytes("primedata-raw", key, content, content_type)

            if success:
                # Create RawFile record (same as sync-full does)
                file_stem = Path(file.filename).stem
                filename = Path(file.filename).name

                # Check if file already exists
                existing = (
                    db.query(RawFile)
                    .filter(
                        RawFile.product_id == datasource.product_id, RawFile.version == version, RawFile.file_stem == file_stem
                    )
                    .first()
                )

                if not existing:
                    # Create new RawFile record
                    raw_file = RawFile(
                        workspace_id=datasource.workspace_id,
                        product_id=datasource.product_id,
                        data_source_id=datasource.id,
                        version=version,
                        filename=filename,
                        file_stem=file_stem,
                        storage_key=key,
                        storage_bucket="primedata-raw",
                        file_size=file_size,
                        content_type=content_type,
                        status=RawFileStatus.INGESTED,
                        file_checksum=file_checksum,
                    )
                    db.add(raw_file)
                    logger.info(
                        f"Created RawFile record for {filename} (version {version}, datasource {datasource_id}, key: {key})"
                    )
                    uploaded_files.append({"filename": filename, "size": file_size, "key": key})
                else:
                    # Update existing RawFile record (S3 file is already overwritten)
                    existing.workspace_id = datasource.workspace_id
                    existing.product_id = datasource.product_id
                    existing.data_source_id = datasource.id
                    existing.filename = filename
                    existing.storage_key = key
                    existing.storage_bucket = "primedata-raw"
                    existing.file_size = file_size
                    existing.content_type = content_type
                    existing.status = RawFileStatus.INGESTED
                    existing.file_checksum = file_checksum
                    # Update ingested_at to reflect the new upload
                    existing.ingested_at = datetime.now(timezone.utc)
                    logger.info(
                        f"Updated RawFile record for {filename} (version {version}, datasource {datasource_id}, key: {key})"
                    )
                    uploaded_files.append({"filename": filename, "size": file_size, "key": key})
            else:
                errors.append(f"Failed to upload {file.filename}")

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error uploading file {file.filename}: {e}")
            errors.append(f"Error uploading {file.filename}: {str(e)}")

    db.commit()

    return {
        "success": len(errors) == 0,
        "uploaded_count": len(uploaded_files),
        "error_count": len(errors),
        "uploaded_files": uploaded_files,
        "errors": errors,
    }


@router.delete("/{datasource_id}")
async def delete_datasource(
    datasource_id: UUID, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    Delete a data source and all associated raw files.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Get the data source
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    # Ensure user has access to the product
    ensure_product_access(db, request, datasource.product_id)

    # Get all raw files associated with this data source
    raw_files_count = db.query(RawFile).filter(RawFile.data_source_id == datasource_id).count()

    if raw_files_count > 0:
        # Delete all RawFile records associated with this datasource
        # This allows the same file to be re-uploaded later (S3 allows overwriting)
        db.query(RawFile).filter(RawFile.data_source_id == datasource_id).delete(synchronize_session=False)
        logger.info(f"Deleted {raw_files_count} RawFile records for data source {datasource_id}")

    # Delete the data source
    db.delete(datasource)
    db.commit()

    return {"message": "Data source deleted successfully"}
