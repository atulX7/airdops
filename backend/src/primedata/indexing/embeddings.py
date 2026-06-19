"""
Embedding generation module for PrimeData.

This module provides functionality to generate embeddings for text chunks
using various embedding models, with MiniLM as the default.
"""

import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Union
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from ..core.embedding_config import EmbeddingModelRegistry, get_embedding_model_config
from ..core.settings import get_settings

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for text using various models."""

    def __init__(self, model_name: str = "minilm", dimension: int = None, workspace_id: UUID = None, db: Session = None):
        """
        Initialize embedding generator.

        Args:
            model_name: Name of the embedding model to use
            dimension: Expected embedding dimension (auto-detected if None)
            workspace_id: Optional workspace ID to check for API keys in workspace settings
            db: Optional database session to query workspace settings
        """
        self.model_name = model_name

        # Get model configuration and validate
        model_config = get_embedding_model_config(model_name)
        if model_config:
            # Use configured dimension if not provided
            self.dimension = dimension or model_config.dimension
            logger.info(f"Initializing {model_config.name} with dimension {self.dimension}")
        else:
            # Fallback for unknown models
            self.dimension = dimension or 384
            logger.warning(f"Unknown model {model_name}, using fallback dimension {self.dimension}")

        self.model = None
        self.tokenizer = None
        self.openai_client = None
        self.model_config = model_config  # Store for later use
        self.workspace_id = workspace_id
        self.db = db

        # Initialize the model
        self._load_model()

    def _load_model(self):
        """Load the embedding model using centralized configuration."""
        try:
            # Use stored model_config from __init__
            model_config = self.model_config

            if not model_config:
                logger.warning(f"Unknown model {self.model_name}, falling back to hash-based embeddings")
                self.model = None
                return

            if not model_config.is_available:
                logger.warning(f"Model {self.model_name} is not available, falling back to hash-based embeddings")
                self.model = None
                return

            # Load model based on type
            if model_config.model_type.value == "sentence_transformers":
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(model_config.model_path)
                logger.info(f"Loaded {model_config.name} model with dimension {self.model.get_sentence_embedding_dimension()}")

            elif model_config.model_type.value == "openai":
                # OpenAI models are handled differently - they require API calls
                # Check workspace settings first, then fallback to environment variable
                api_key = None

                # Try to get from workspace settings first
                if self.workspace_id and self.db:
                    try:
                        from primedata.db.models import Workspace

                        workspace = self.db.query(Workspace).filter(Workspace.id == self.workspace_id).first()
                        if workspace and workspace.settings:
                            api_key = workspace.settings.get("openai_api_key")
                    except Exception as e:
                        logger.warning(f"Failed to load workspace settings: {e}")

                # Fallback to environment variable
                if not api_key:
                    settings = get_settings()
                    api_key = settings.OPENAI_API_KEY

                if not api_key:
                    logger.warning(
                        f"OpenAI API key not configured. Set it in workspace settings or OPENAI_API_KEY environment variable to use {model_config.name}"
                    )
                    logger.warning("Falling back to hash-based embeddings")
                    self.model = None
                    self.openai_client = None
                    return

                try:
                    import openai

                    self.openai_client = openai.OpenAI(api_key=api_key)
                    self.model = "openai"  # Mark as OpenAI model (not None)
                    logger.info(f"OpenAI model {model_config.name} configured with API key")
                except ImportError:
                    logger.error("openai package not installed. Install with: pip install openai")
                    logger.warning("Falling back to hash-based embeddings")
                    self.model = None
                    self.openai_client = None
                except Exception as e:
                    logger.error(f"Failed to initialize OpenAI client: {e}")
                    logger.warning("Falling back to hash-based embeddings")
                    self.model = None
                    self.openai_client = None

            else:
                logger.warning(f"Unsupported model type {model_config.model_type} for {self.model_name}")
                self.model = None

        except ImportError as e:
            logger.warning(f"Failed to import required dependencies: {e}")
            logger.warning("Falling back to hash-based embeddings")
            self.model = None

        except Exception as e:
            logger.error(f"Failed to load model {self.model_name}: {e}")
            logger.warning("Falling back to hash-based embeddings")
            self.model = None

    def embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as numpy array
        """
        # Handle OpenAI models
        if self.model == "openai" and self.openai_client and self.model_config:
            try:
                response = self.openai_client.embeddings.create(model=self.model_config.model_path, input=text)
                embedding_vector = response.data[0].embedding
                return np.array(embedding_vector, dtype=np.float32)
            except Exception as e:
                logger.error(f"Error generating OpenAI embedding: {e}")
                logger.warning("Falling back to hash-based embedding")
                return self._hash_embedding(text)

        # Handle sentence transformer models
        if self.model is not None and self.model != "openai":
            try:
                # Use the loaded model
                embedding = self.model.encode(text, convert_to_numpy=True)
                return embedding

            except Exception as e:
                logger.error(f"Error generating embedding with model: {e}")
                logger.warning("Falling back to hash-based embedding")
                return self._hash_embedding(text)

        # Fallback to hash-based embedding
        return self._hash_embedding(text)

    def embed_batch(self, texts: List[str], batch_size: Optional[int] = None) -> List[np.ndarray]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of input texts to embed
            batch_size: Optional batch size for sentence transformers (defaults to len(texts) or model-appropriate size)

        Returns:
            List of embedding vectors as numpy arrays
        """
        # Handle OpenAI models
        if self.model == "openai" and self.openai_client and self.model_config:
            try:
                # OpenAI API supports batch requests
                response = self.openai_client.embeddings.create(model=self.model_config.model_path, input=texts)
                embeddings = [np.array(item.embedding, dtype=np.float32) for item in response.data]
                return embeddings
            except Exception as e:
                logger.error(f"Error generating OpenAI batch embeddings: {e}")
                logger.warning("Falling back to hash-based embeddings")
                return [self._hash_embedding(text) for text in texts]

        # Handle sentence transformer models
        if self.model is not None and self.model != "openai":
            try:
                # For large models, use smaller batch_size parameter to manage memory
                # This prevents OOM errors with large models like BGE Large
                # sentence_transformers.encode() handles batching internally when batch_size is provided
                if batch_size is None:
                    # Auto-determine batch size based on model dimension
                    model_dim = self.get_dimension()
                    if model_dim >= 1024:
                        batch_size = 3  # Very large models (BGE Large) need tiny batches to avoid timeout
                    elif model_dim >= 768:
                        batch_size = 15  # Large models need medium batches
                    else:
                        batch_size = 32  # Smaller models can handle larger batches (default for sentence_transformers)

                # Use sentence_transformers' built-in batch_size parameter
                # This is more memory-efficient than manual batching
                # Enable progress bar for large batches to show progress
                show_progress = len(texts) > batch_size * 2  # Show progress for batches larger than 2x internal batch size
                embeddings = self.model.encode(
                    texts,
                    convert_to_numpy=True,
                    show_progress_bar=show_progress,
                    batch_size=batch_size,
                    normalize_embeddings=False,  # Don't normalize unless needed
                )
                return [emb for emb in embeddings]

            except Exception as e:
                logger.error(f"Error generating batch embeddings with model: {e}")
                logger.warning("Falling back to hash-based embeddings")
                return [self._hash_embedding(text) for text in texts]

        # Fallback to hash-based embeddings
        return [self._hash_embedding(text) for text in texts]

    def _hash_embedding(self, text: str) -> np.ndarray:
        """
        Generate a hash-based embedding as fallback.

        This creates a deterministic embedding by hashing the text
        and converting it to a vector of the expected dimension.

        Args:
            text: Input text

        Returns:
            Hash-based embedding vector
        """
        # Create a hash of the text
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # Convert hash to a vector of the expected dimension
        embedding = np.zeros(self.dimension)

        # Use hash bytes to fill the embedding
        hash_bytes = bytes.fromhex(text_hash)
        for i in range(self.dimension):
            byte_idx = i % len(hash_bytes)
            embedding[i] = (hash_bytes[byte_idx] - 128) / 128.0  # Normalize to [-1, 1]

        # Add some text length information
        text_length = len(text)
        embedding[0] = min(text_length / 1000.0, 1.0)  # Normalize length to [0, 1]

        return embedding

    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        # For OpenAI models, dimension comes from config
        if self.model == "openai" and self.model_config:
            return self.model_config.dimension

        # For sentence transformer models
        if self.model is not None and self.model != "openai":
            try:
                return self.model.get_sentence_embedding_dimension()
            except:
                return self.dimension
        return self.dimension

    def get_model_info(self) -> dict:
        """Get information about the loaded model."""
        is_loaded = self.model is not None and self.model != "openai"
        is_openai = self.model == "openai"
        # Also check if openai_client is set (even if model is not "openai" string)
        if not is_openai and self.openai_client is not None:
            is_openai = True
        model_loaded = is_loaded or is_openai  # Consider OpenAI as loaded
        return {
            "model_name": self.model_name,
            "dimension": self.get_dimension(),
            "is_loaded": is_loaded,
            "is_openai": is_openai,
            "model_loaded": model_loaded,
            "model_type": "openai" if is_openai else ("sentence_transformers" if is_loaded else None),
            "fallback_mode": not model_loaded,  # Using hash-based fallback if neither loaded nor OpenAI
        }


def create_embedding_generator(
    model_name: str = "minilm", dimension: int = 384, workspace_id: UUID = None, db: Session = None
) -> EmbeddingGenerator:
    """
    Factory function to create an embedding generator.

    Args:
        model_name: Name of the embedding model
        dimension: Expected embedding dimension
        workspace_id: Optional workspace ID for API key lookup
        db: Optional database session for API key lookup

    Returns:
        EmbeddingGenerator instance
    """
    return EmbeddingGenerator(model_name, dimension, workspace_id, db)


# Default embedding generator instance - REMOVED to avoid loading model at import time
# This was causing Airflow DAG import timeouts (30s limit exceeded)
#
# DO NOT create EmbeddingGenerator instances at module import time!
# Always create them inside task functions or use lazy loading.
#
# For backward compatibility, use get_default_embedder() function below,
# but prefer creating EmbeddingGenerator() instances inside your task functions
# to avoid import-time model loading.

_default_embedder = None


def get_default_embedder() -> EmbeddingGenerator:
    """
    Get the default embedding generator (lazy-loaded).

    This avoids loading the model at module import time, which is critical
    for Airflow DAG imports that have a 30s timeout.

    Returns:
        EmbeddingGenerator instance
    """
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = EmbeddingGenerator("minilm", 384)
    return _default_embedder


# Removed: default_embedder = EmbeddingGenerator("minilm", 384)
# This was causing import-time model loading which timed out Airflow DAG imports
# Use get_default_embedder() or create EmbeddingGenerator() inside task functions instead
