"""
Qdrant client for vector storage and retrieval.

This module provides functionality to interact with Qdrant vector database
for storing and retrieving embeddings.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

logger = logging.getLogger(__name__)

# Version detection for API compatibility
try:
    from importlib.metadata import version
    QDRANT_CLIENT_VERSION = version("qdrant-client")
    logger.debug(f"Detected qdrant-client version: {QDRANT_CLIENT_VERSION}")
except Exception:
    QDRANT_CLIENT_VERSION = None
    logger.warning("Could not detect qdrant-client version, using default API")


class QdrantClient:
    """Client for interacting with Qdrant vector database."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, grpc_port: Optional[int] = None):
        """
        Initialize Qdrant client.

        Args:
            host: Qdrant host (defaults to environment variable or localhost)
            port: Qdrant HTTP port (defaults to environment variable or 6333)
            grpc_port: Qdrant gRPC port (defaults to environment variable or 6334)
        """
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.grpc_port = grpc_port or int(os.getenv("QDRANT_GRPC_PORT", "6334"))

        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Qdrant client."""
        try:
            from qdrant_client import QdrantClient as QdrantClientLib
            from qdrant_client.http import models

            # Increase timeout for large batch operations (default is 30s, increase to 5 minutes)
            timeout = int(os.getenv("QDRANT_TIMEOUT", "300"))  # 5 minutes default

            self.client = QdrantClientLib(
                host=self.host,
                port=self.port,
                grpc_port=self.grpc_port,
                prefer_grpc=False,  # Use HTTP by default
                timeout=timeout,  # Increase timeout for large operations
            )

            # Test connection
            collections = self.client.get_collections()
            logger.info(f"Connected to Qdrant at {self.host}:{self.port} (timeout={timeout}s)")
            logger.info(f"Found {len(collections.collections)} existing collections")

        except ImportError:
            logger.error("qdrant-client not installed. Install with: pip install qdrant-client")
            self.client = None

        except Exception as e:
            logger.error(f"Failed to connect to Qdrant at {self.host}:{self.port}: {e}")
            self.client = None

    def is_connected(self) -> bool:
        """Check if client is connected to Qdrant."""
        return self.client is not None

    def ensure_collection(self, collection_name: str, vector_size: int, distance: str = "Cosine") -> bool:
        """
        Ensure a collection exists with the specified configuration.

        Args:
            collection_name: Name of the collection
            vector_size: Size of the vectors
            distance: Distance metric (Cosine, Dot, Euclid)

        Returns:
            True if collection exists or was created successfully
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return False

        try:
            from qdrant_client.http import models

            # Check if collection exists and verify dimension
            try:
                collection_info = self.client.get_collection(collection_name)
                existing_size = collection_info.config.params.vectors.size

                # Check if dimension matches
                if existing_size != vector_size:
                    logger.warning(
                        f"Collection {collection_name} exists with dimension {existing_size}, "
                        f"but required dimension is {vector_size}. Deleting and recreating collection."
                    )
                    # Delete the collection so it can be recreated with correct dimension
                    self.client.delete_collection(collection_name)
                    logger.info(f"Deleted collection {collection_name} to recreate with correct dimension")
                else:
                    logger.info(f"Collection {collection_name} already exists with correct dimension {vector_size}")
                    return True
            except Exception as e:
                # Collection doesn't exist, will create it
                logger.info(f"Collection {collection_name} does not exist, will create it")

            # Create collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=getattr(models.Distance, distance.upper())),
            )

            logger.info(f"Created collection {collection_name} with vector size {vector_size}")
            return True

        except Exception as e:
            error_msg = str(e)
            if "too many open files" in error_msg.lower() or "os error 24" in error_msg.lower():
                logger.error(
                    f"Failed to ensure collection {collection_name}: {e}\n"
                    f"This is a Qdrant server resource limit issue. "
                    f"Check that the Qdrant container has ulimits.nofile set to at least 65536. "
                    f"Current limit may be too low (often 1024 or 4096 by default)."
                )
            else:
                logger.error(f"Failed to ensure collection {collection_name}: {e}")
            return False

    def upsert_points(self, collection_name: str, points: List[Dict[str, Any]], batch_size: int = 50) -> bool:
        """
        Upsert points to a collection in batches to avoid timeouts.

        Args:
            collection_name: Name of the collection
            points: List of points to upsert, each containing 'id', 'vector', and 'payload'
            batch_size: Number of points to upsert per batch (default: 100)

        Returns:
            True if upsert was successful
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return False

        if not points:
            logger.warning("No points to upsert")
            return True

        try:
            from qdrant_client.http import models

            total_points = len(points)
            logger.info(f"Upserting {total_points} points to collection {collection_name} in batches of {batch_size}")

            # Process points in batches
            for i in range(0, total_points, batch_size):
                batch = points[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_points + batch_size - 1) // batch_size

                # Convert batch points to Qdrant format
                qdrant_points = []
                for point in batch:
                    qdrant_points.append(models.PointStruct(id=point["id"], vector=point["vector"], payload=point["payload"]))

                # Upsert batch with retry logic
                max_retries = 3
                batch_success = False
                for retry in range(max_retries):
                    try:
                        self.client.upsert(
                            collection_name=collection_name, points=qdrant_points, wait=True  # Wait for confirmation
                        )
                        logger.info(
                            f"Upserted batch {batch_num}/{total_batches} ({len(batch)} points) to collection {collection_name}"
                        )
                        batch_success = True
                        break
                    except Exception as batch_error:
                        if retry < max_retries - 1:
                            wait_time = 2**retry  # Exponential backoff: 1s, 2s, 4s
                            logger.warning(
                                f"Batch {batch_num}/{total_batches} failed (attempt {retry + 1}/{max_retries}): {batch_error}. Retrying in {wait_time}s..."
                            )
                            time.sleep(wait_time)
                        else:
                            logger.error(
                                f"Failed to upsert batch {batch_num}/{total_batches} after {max_retries} attempts: {batch_error}"
                            )
                            return False

                if not batch_success:
                    return False

            logger.info(f"Successfully upserted all {total_points} points to collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert points to collection {collection_name}: {e}")
            return False

    def search_points(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Search for similar points in a collection.

        Args:
            collection_name: Name of the collection
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score threshold
            filter_conditions: Optional filter conditions

        Returns:
            List of search results

        Raises:
            Exception: If search fails due to an error (not just no results)
        """
        if not self.is_connected():
            raise ConnectionError("Qdrant client not connected")

        try:
            from qdrant_client.http import models

            # Build query filter if needed
            query_filter = None
            if filter_conditions:
                query_filter = self._build_filter(filter_conditions)
                logger.info(
                    "Qdrant search_points: collection_name=%s, filter_conditions=%s",
                    collection_name,
                    json.dumps(filter_conditions, default=str),
                )

            # For qdrant-client 1.16.2+, use query_points API (more stable)
            # Check version to determine which API to use
            use_query_points = True
            if QDRANT_CLIENT_VERSION:
                try:
                    from packaging import version as pkg_version
                    # Use query_points for 1.16.0+
                    use_query_points = pkg_version.parse(QDRANT_CLIENT_VERSION) >= pkg_version.parse("1.16.0")
                except ImportError:
                    # packaging not available, default to query_points (safer for newer versions)
                    logger.debug("packaging module not available, defaulting to query_points API")
                    use_query_points = True
                except Exception:
                    # If version parsing fails, default to query_points
                    logger.debug(f"Version parsing failed for {QDRANT_CLIENT_VERSION}, defaulting to query_points")
                    use_query_points = True

            if use_query_points:
                # Use query_points API (stable in 1.16.2+)
                try:
                    results = self.client.query_points(
                        collection_name=collection_name,
                        query=query_vector,  # Direct vector list
                        limit=limit,
                        query_filter=query_filter,
                        with_payload=True,
                        with_vectors=False,
                        score_threshold=score_threshold,
                    )

                    # Convert QueryResponse to list of dicts
                    search_results = []
                    # query_points returns a QueryResponse object with points attribute
                    for point in results.points:
                        search_results.append({
                            "id": point.id,
                            "score": point.score,
                            "payload": point.payload if hasattr(point, 'payload') else {}
                        })

                    logger.info(f"Found {len(search_results)} results for search in collection {collection_name}")
                    return search_results

                except AttributeError as e:
                    # query_points might not exist in older versions, fall back to search()
                    logger.warning(f"query_points API not available, trying search() fallback: {e}")
                    use_query_points = False

            # Fallback to search() API for older versions or if query_points fails
            if not use_query_points:
                try:
                    results = self.client.search(
                        collection_name=collection_name,
                        query_vector=query_vector,
                        limit=limit,
                        score_threshold=score_threshold,
                        query_filter=query_filter,
                    )

                    # Convert results to list of dicts
                    search_results = []
                    for result in results:
                        search_results.append({
                            "id": result.id,
                            "score": result.score,
                            "payload": result.payload if hasattr(result, 'payload') else {}
                        })

                    logger.info(f"Found {len(search_results)} results for search in collection {collection_name}")
                    return search_results

                except AttributeError as e:
                    raise RuntimeError(
                        f"Neither query_points() nor search() API available in qdrant-client. "
                        f"Version: {QDRANT_CLIENT_VERSION}, Error: {e}"
                    )

        except Exception as e:
            # Re-raise as-is if it's already a specific exception type
            if isinstance(e, (ConnectionError, RuntimeError)):
                raise
            # Otherwise, wrap in a more descriptive error
            logger.error(f"Failed to search points in collection {collection_name}: {e}", exc_info=True)
            raise RuntimeError(f"Search failed for collection {collection_name}: {str(e)}") from e

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Search for similar points in a collection (alias for search_points for compatibility).
        
        Args:
            collection_name: Name of the collection
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score threshold
            filter_conditions: Optional filter conditions
            
        Returns:
            List of search results with 'id', 'score', and 'payload' keys
        """
        return self.search_points(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=filter_conditions,
        )

    def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Collection information or None if not found
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return None

        try:
            collection_info = self.client.get_collection(collection_name)
            
            # Debug logging to understand the actual structure
            logger.debug(f"Collection info type: {type(collection_info)}")
            logger.debug(f"Collection info dir: {[attr for attr in dir(collection_info) if not attr.startswith('_')]}")

            # Try to access points_count - handle both attribute and dict access
            # Qdrant client 1.16.2 may have changed the API structure
            try:
                points_count = collection_info.points_count
            except AttributeError:
                # Try as dict
                if hasattr(collection_info, 'get'):
                    points_count = collection_info.get('points_count', 0)
                elif hasattr(collection_info, '__dict__'):
                    points_count = collection_info.__dict__.get('points_count', 0)
                else:
                    logger.warning(f"Could not access points_count from {type(collection_info)}")
                    # Try fallback
                    return self._get_collection_info_fallback(collection_name)

            # Similar for other fields
            try:
                vectors_count = collection_info.vectors_count
                indexed_vectors_count = collection_info.indexed_vectors_count
                segments_count = collection_info.segments_count
                vector_size = collection_info.config.params.vectors.size
                distance = collection_info.config.params.vectors.distance
            except AttributeError as attr_error:
                # In qdrant-client 1.16.2, some attributes might not exist
                # Try to use points_count as fallback for vectors_count (each point has one vector)
                logger.debug(f"Attribute access failed (expected in qdrant-client 1.16.2): {attr_error}. Using fallback.")
                try:
                    vectors_count = points_count  # Safe fallback: each point has one vector
                    indexed_vectors_count = points_count  # Assume all are indexed if we can't determine
                    segments_count = getattr(collection_info, 'segments_count', 0)
                    vector_size = collection_info.config.params.vectors.size
                    distance = collection_info.config.params.vectors.distance
                except Exception:
                    # If fallback also fails, use the HTTP API fallback method
                    logger.warning("Fallback attribute access failed. Using HTTP API fallback.")
                    return self._get_collection_info_fallback(collection_name)

            result = {
                "name": collection_name,
                "vectors_count": vectors_count,
                "indexed_vectors_count": indexed_vectors_count,
                "points_count": points_count,
                "segments_count": segments_count,
                "config": {
                    "vector_size": vector_size,
                    "distance": str(distance) if distance else "Cosine",
                },
            }
            
            logger.debug(f"Collection info result: {result}")
            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get collection info for {collection_name}: {error_msg}", exc_info=True)
            
            # Check if this is a Pydantic validation error (version mismatch)
            if "validation error" in error_msg.lower() or "ParsingModel" in error_msg:
                logger.error(
                    f"Qdrant version mismatch detected. Client: 1.16.2, Server version may differ."
                )
            
            # Try fallback method
            return self._get_collection_info_fallback(collection_name)

    def _get_collection_info_fallback(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Fallback method to get collection info using direct HTTP API call.
        This handles cases where the Python client API has changed between versions.
        """
        try:
            import requests
            
            response = requests.get(
                f"http://{self.host}:{self.port}/collections/{collection_name}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                
                logger.info(f"Using HTTP API fallback for collection {collection_name}. Points: {result.get('points_count', 0)}")
                
                return {
                    "name": collection_name,
                    "vectors_count": result.get("vectors_count", 0),
                    "indexed_vectors_count": result.get("indexed_vectors_count", 0),
                    "points_count": result.get("points_count", 0),
                    "segments_count": result.get("segments_count", 0),
                    "config": {
                        "vector_size": result.get("config", {}).get("params", {}).get("vectors", {}).get("size", 0),
                        "distance": str(result.get("config", {}).get("params", {}).get("vectors", {}).get("distance", "Cosine")),
                    },
                }
            else:
                logger.error(f"HTTP API fallback failed for {collection_name}: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Fallback method failed for {collection_name}: {e}")
            return None

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if deletion was successful
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return False

        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False

    def list_collections(self) -> List[str]:
        """
        List all collections.

        Returns:
            List of collection names
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return []

        try:
            collections = self.client.get_collections()
            return [collection.name for collection in collections.collections]

        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def _build_filter(self, filter_conditions: Dict) -> Any:
        """
        Build Qdrant filter from conditions.

        Args:
            filter_conditions: Filter conditions dictionary
                - Supports exact match (value)
                - Supports list match (any of values)
                - Supports nested payload paths (e.g., "payload.chunk_id")

        Returns:
            Qdrant filter object
        """
        try:
            from qdrant_client.http import models

            # Simple filter building - can be extended for more complex conditions
            conditions = []

            for key, value in filter_conditions.items():
                # Handle nested payload paths (e.g., "payload.chunk_id" or just "chunk_id")
                # Qdrant expects payload fields without "payload." prefix in filters
                field_key = key.replace("payload.", "") if key.startswith("payload.") else key

                if isinstance(value, list):
                    # Must match any of the values
                    conditions.append(models.FieldCondition(key=field_key, match=models.MatchAny(any=value)))
                else:
                    # Must match exact value
                    conditions.append(models.FieldCondition(key=field_key, match=models.MatchValue(value=value)))

            if len(conditions) == 1:
                return models.Filter(must=[conditions[0]])
            elif len(conditions) > 1:
                return models.Filter(must=conditions)
            else:
                return None

        except Exception as e:
            logger.error(f"Failed to build filter: {e}")
            return None

    def _sanitize_collection_name(self, name: str) -> str:
        """
        Sanitize a product name to be safe for use in Qdrant collection names.

        Preserves case and hyphens for better readability while ensuring valid collection names.

        Args:
            name: Product name to sanitize

        Returns:
            Sanitized name safe for collection naming
        """
        import re

        if not name or not name.strip():
            return "product"

        # Start with the original name
        sanitized = name.strip()

        # Replace spaces with hyphens (more readable than underscores)
        sanitized = re.sub(r"\s+", "-", sanitized)

        # Replace any characters that aren't alphanumeric, hyphens, underscores with hyphens
        # This preserves hyphens and underscores but removes special characters
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", sanitized)

        # Remove multiple consecutive hyphens/underscores
        sanitized = re.sub(r"[-_]+", "-", sanitized)

        # Remove leading/trailing hyphens and underscores
        sanitized = sanitized.strip("-_")

        # Preserve case (don't convert to lowercase) for better readability
        # Qdrant supports case-sensitive collection names

        # Ensure it's not empty after sanitization
        if not sanitized:
            sanitized = "product"

        # Limit length (Qdrant collection names should be reasonable length)
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
            # Make sure we don't end with a hyphen after truncation
            sanitized = sanitized.rstrip("-_")

        logger.debug(f"Sanitized collection name: '{name}' -> '{sanitized}'")
        return sanitized

    def get_collection_name(
        self,
        workspace_id: str,
        product_id: str,
        version: int,
        product_name: Optional[str] = None,
        use_product_name: bool = True,
    ) -> str:
        """
        Get collection name for a product version.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number
            product_name: Optional product name (if use_product_name is True)
            use_product_name: Whether to use product name (True) or product_id (False)

        Returns:
            Collection name
        """
        if use_product_name and product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            return f"ws_{workspace_id}__{sanitized_name}__v_{version}"
        else:
            # Fallback to product_id for backward compatibility
            return f"ws_{workspace_id}__prod_{product_id}__v_{version}"

    def find_collection_name(
        self, workspace_id: str, product_id: str, version: int, product_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Find collection name by checking both naming schemes (product name and product_id).
        This provides backward compatibility.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number
            product_name: Optional product name

        Returns:
            Collection name if found, None otherwise
        """
        if not self.is_connected():
            return None

        # Try product name first if provided
        if product_name:
            sanitized_name = self._sanitize_collection_name(product_name)
            collection_name = f"ws_{workspace_id}__{sanitized_name}__v_{version}"
            collections = self.list_collections()
            if collection_name in collections:
                return collection_name

        # Fallback to product_id format
        collection_name = f"ws_{workspace_id}__prod_{product_id}__v_{version}"
        collections = self.list_collections()
        if collection_name in collections:
            return collection_name

        return None

    def set_prod_alias(self, workspace_id: str, product_id: str, version: int, product_name: Optional[str] = None) -> bool:
        """
        Set production alias to point to a specific version collection.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            version: Version number to promote
            product_name: Optional product name to use in collection name (sanitized)

        Returns:
            True if alias was set successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return False

        try:
            from qdrant_client.http import models

            # Create collection name - use product name if provided, otherwise use product_id
            if product_name:
                sanitized_name = self._sanitize_collection_name(product_name)
                collection_name = f"ws_{workspace_id}__{sanitized_name}__v_{version}"
                alias_name = f"prod_ws_{workspace_id}__{sanitized_name}"
            else:
                # Fallback to product_id for backward compatibility
                collection_name = f"ws_{workspace_id}__prod_{product_id}__v_{version}"
                alias_name = f"prod_ws_{workspace_id}__prod_{product_id}"

            # Check if the target collection exists
            collections = self.client.get_collections()
            collection_exists = any(col.name == collection_name for col in collections.collections)

            if not collection_exists:
                logger.error(f"Collection {collection_name} does not exist")
                return False

            # Create or update the alias using direct HTTP API
            import requests

            # First, try to delete existing alias if it exists
            try:
                existing_aliases = self.client.get_aliases()
                for alias in existing_aliases.aliases:
                    if alias.alias_name == alias_name:
                        # Delete existing alias
                        delete_payload = {"actions": [{"delete_alias": {"alias_name": alias_name}}]}
                        response = requests.post(
                            f"http://{self.host}:{self.port}/collections/aliases",
                            json=delete_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        if response.status_code == 200:
                            logger.info(f"Deleted existing alias '{alias_name}'")
                        break
            except Exception as e:
                logger.warning(f"Could not check/delete existing aliases: {e}")

            # Create the new alias
            create_payload = {"actions": [{"create_alias": {"collection_name": collection_name, "alias_name": alias_name}}]}

            response = requests.post(
                f"http://{self.host}:{self.port}/collections/aliases",
                json=create_payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                logger.info(f"Created production alias '{alias_name}' -> '{collection_name}'")
            else:
                raise Exception(f"Failed to create alias: {response.status_code} - {response.text}")

            return True

        except Exception as e:
            logger.error(f"Failed to set production alias: {e}")
            return False

    def get_prod_alias_collection(
        self, workspace_id: str, product_id: str, product_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the collection name that the production alias points to.

        Args:
            workspace_id: Workspace ID
            product_id: Product ID
            product_name: Optional product name to check for alias (sanitized)

        Returns:
            Collection name if alias exists, None otherwise
        """
        try:
            # Try product name first if provided, then fallback to product_id
            alias_names = []
            if product_name:
                sanitized_name = self._sanitize_collection_name(product_name)
                alias_names.append(f"prod_ws_{workspace_id}__{sanitized_name}")
            # Also check product_id for backward compatibility
            alias_names.append(f"prod_ws_{workspace_id}__prod_{product_id}")

            # Get all aliases using direct HTTP API
            import requests

            response = requests.get(f"http://{self.host}:{self.port}/aliases")

            if response.status_code == 200:
                data = response.json()
                for alias in data.get("result", {}).get("aliases", []):
                    alias_name = alias.get("alias_name")
                    if alias_name in alias_names:
                        return alias.get("collection_name")

            return None

        except Exception as e:
            logger.error(f"Failed to get production alias: {e}")
            return None

    def scroll_points(
        self,
        collection_name: str,
        limit: int = 100,
        offset: Optional[int] = None,
        filter_conditions: Optional[Dict] = None,
        with_payload: bool = True,
        with_vector: bool = False,
    ) -> Dict[str, Any]:
        """
        Scroll through points in a collection with pagination.

        Args:
            collection_name: Name of the collection
            limit: Maximum number of points to return
            offset: Optional offset for pagination (use offset from previous response)
            filter_conditions: Optional filter conditions
            with_payload: Whether to include payload in results
            with_vector: Whether to include vectors in results

        Returns:
            Dictionary with 'points' (list of points) and 'next_page_offset' (for pagination)
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return {"points": [], "next_page_offset": None}

        try:
            from qdrant_client.http import models

            # Build scroll request
            scroll_filter = None
            if filter_conditions:
                scroll_filter = self._build_filter(filter_conditions)

            # Perform scroll
            result = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=limit,
                offset=offset,
                with_payload=with_payload,
                with_vectors=with_vector,
            )

            # Convert points to list of dicts
            points = []
            for point in result[0]:  # result is (points, next_page_offset)
                point_dict = {
                    "id": point.id,
                    "payload": point.payload if hasattr(point, "payload") else {},
                }
                if with_vector and hasattr(point, "vector"):
                    point_dict["vector"] = point.vector
                points.append(point_dict)

            next_offset = result[1]  # next_page_offset

            logger.info(f"Scrolled {len(points)} points from collection {collection_name}")
            return {
                "points": points,
                "next_page_offset": next_offset,
            }

        except Exception as e:
            logger.error(f"Failed to scroll points in collection {collection_name}: {e}")
            return {"points": [], "next_page_offset": None}

    def get_point_by_chunk_id(
        self,
        collection_name: str,
        chunk_id: str,
        product_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a point by chunk_id from Qdrant payload.

        Args:
            collection_name: Name of the collection
            chunk_id: Chunk ID to search for
            product_id: Optional product ID filter
            version: Optional version filter

        Returns:
            Point dictionary with id, vector (if requested), and payload, or None if not found
        """
        if not self.is_connected():
            logger.error("Qdrant client not connected")
            return None

        try:
            from qdrant_client.http import models

            # Build filter for chunk_id
            filter_conditions = {"chunk_id": chunk_id}
            if product_id:
                filter_conditions["product_id"] = str(product_id)
            if version is not None:
                filter_conditions["version"] = version

            scroll_filter = self._build_filter(filter_conditions)

            # Scroll with limit 1 to get the matching point
            result = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            points = result[0]
            if points:
                point = points[0]
                return {
                    "id": point.id,
                    "payload": point.payload if hasattr(point, "payload") else {},
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get point by chunk_id {chunk_id} from collection {collection_name}: {e}")
            return None


# Global Qdrant client instance
qdrant_client = QdrantClient()
