"""
Embedding model configuration for PrimeData.

This module provides centralized configuration for all available embedding models,
their properties, and metadata. This ensures consistency across the application
and makes it easy to add new models or modify existing ones.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class EmbeddingModelType(str, Enum):
    """Types of embedding models."""

    SENTENCE_TRANSFORMERS = "sentence_transformers"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    CUSTOM = "custom"


@dataclass
class EmbeddingModelConfig:
    """Configuration for an embedding model."""

    id: str
    name: str
    description: str
    model_type: EmbeddingModelType
    dimension: int
    model_path: str
    is_available: bool = True
    requires_api_key: bool = False
    cost_per_token: Optional[float] = None
    max_tokens: Optional[int] = None
    metadata: Optional[Dict] = None


class EmbeddingModelRegistry:
    """Registry for all available embedding models."""

    # Default models configuration
    MODELS: Dict[str, EmbeddingModelConfig] = {
        "minilm": EmbeddingModelConfig(
            id="minilm",
            name="MiniLM",
            description="Lightweight sentence transformer model optimized for speed",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=384,
            model_path="all-MiniLM-L6-v2",
            is_available=True,
            requires_api_key=False,
            metadata={"provider": "sentence-transformers", "license": "apache-2.0", "performance": "fast", "quality": "good"},
        ),
        "minilm-l12": EmbeddingModelConfig(
            id="minilm-l12",
            name="MiniLM-L12",
            description="Higher quality MiniLM model with 12 layers",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=384,
            model_path="all-MiniLM-L12-v2",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "sentence-transformers",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "better",
            },
        ),
        "mpnet": EmbeddingModelConfig(
            id="mpnet",
            name="MPNet",
            description="Microsoft's MPNet model for high-quality embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="all-mpnet-base-v2",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "sentence-transformers",
                "license": "apache-2.0",
                "performance": "slower",
                "quality": "excellent",
            },
        ),
        "openai-ada-002": EmbeddingModelConfig(
            id="openai-ada-002",
            name="OpenAI Ada-002",
            description="OpenAI's text-embedding-ada-002 model",
            model_type=EmbeddingModelType.OPENAI,
            dimension=1536,
            model_path="text-embedding-ada-002",
            is_available=True,
            requires_api_key=True,
            cost_per_token=0.0001,  # $0.0001 per 1K tokens
            max_tokens=8191,
            metadata={"provider": "openai", "license": "commercial", "performance": "fast", "quality": "excellent"},
        ),
        "openai-3-small": EmbeddingModelConfig(
            id="openai-3-small",
            name="OpenAI Text-3-Small",
            description="OpenAI's latest small embedding model",
            model_type=EmbeddingModelType.OPENAI,
            dimension=1536,
            model_path="text-embedding-3-small",
            is_available=True,
            requires_api_key=True,
            cost_per_token=0.00002,  # $0.00002 per 1K tokens
            max_tokens=8191,
            metadata={"provider": "openai", "license": "commercial", "performance": "fast", "quality": "excellent"},
        ),
        "openai-3-large": EmbeddingModelConfig(
            id="openai-3-large",
            name="OpenAI Text-3-Large",
            description="OpenAI's latest large embedding model with higher dimensions",
            model_type=EmbeddingModelType.OPENAI,
            dimension=3072,
            model_path="text-embedding-3-large",
            is_available=True,
            requires_api_key=True,
            cost_per_token=0.00013,  # $0.00013 per 1K tokens
            max_tokens=8191,
            metadata={"provider": "openai", "license": "commercial", "performance": "medium", "quality": "excellent"},
        ),
        # Open-source models with 768 dimensions
        "e5-base": EmbeddingModelConfig(
            id="e5-base",
            name="E5 Base",
            description="Microsoft E5 base model for general-purpose embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="intfloat/e5-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "bge-base-en": EmbeddingModelConfig(
            id="bge-base-en",
            name="BGE Base (English)",
            description="BAAI General Embedding base model optimized for English",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="BAAI/bge-base-en-v1.5",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "baai",
                "license": "mit",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "instructor-base": EmbeddingModelConfig(
            id="instructor-base",
            name="Instructor Base",
            description="Instructor model for instruction-following embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="hkunlp/instructor-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "hkunlp",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "excellent",
                "instruction_tuned": True,
            },
        ),
        # Open-source models with 1024 dimensions
        "e5-large": EmbeddingModelConfig(
            id="e5-large",
            name="E5 Large",
            description="Microsoft E5 large model with 1024 dimensions for high-quality embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="intfloat/e5-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "bge-large-en": EmbeddingModelConfig(
            id="bge-large-en",
            name="BGE Large (English)",
            description="BAAI General Embedding large model with 1024 dimensions for English",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="BAAI/bge-large-en-v1.5",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "baai",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "gte-large": EmbeddingModelConfig(
            id="gte-large",
            name="GTE Large",
            description="General Text Embeddings large model with 1024 dimensions",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="thenlper/gte-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "thenlper",
                "license": "apache-2.0",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "instructor-large": EmbeddingModelConfig(
            id="instructor-large",
            name="Instructor Large",
            description="Instructor large model with 1024 dimensions for instruction-following",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="hkunlp/instructor-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "hkunlp",
                "license": "apache-2.0",
                "performance": "slower",
                "quality": "excellent",
                "instruction_tuned": True,
            },
        ),
        # Additional open-source models with other dimensions
        "e5-small": EmbeddingModelConfig(
            id="e5-small",
            name="E5 Small",
            description="Microsoft E5 small model optimized for speed",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=384,
            model_path="intfloat/e5-small",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "fast",
                "quality": "good",
                "multilingual": False,
            },
        ),
        "bge-small-en": EmbeddingModelConfig(
            id="bge-small-en",
            name="BGE Small (English)",
            description="BAAI General Embedding small model for fast embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=384,
            model_path="BAAI/bge-small-en-v1.5",
            is_available=True,
            requires_api_key=False,
            metadata={"provider": "baai", "license": "mit", "performance": "fast", "quality": "good", "multilingual": False},
        ),
        "gte-base": EmbeddingModelConfig(
            id="gte-base",
            name="GTE Base",
            description="General Text Embeddings base model with 768 dimensions",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="thenlper/gte-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "thenlper",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        # Multilingual models
        "multilingual-e5-base": EmbeddingModelConfig(
            id="multilingual-e5-base",
            name="Multilingual E5 Base",
            description="Microsoft E5 base model supporting 100+ languages",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="intfloat/multilingual-e5-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": True,
                "languages": "100+",
            },
        ),
        "multilingual-e5-large": EmbeddingModelConfig(
            id="multilingual-e5-large",
            name="Multilingual E5 Large",
            description="Microsoft E5 large model with 1024 dimensions supporting 100+ languages",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="intfloat/multilingual-e5-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": True,
                "languages": "100+",
            },
        ),
        "bge-m3": EmbeddingModelConfig(
            id="bge-m3",
            name="BGE M3",
            description="BAAI Multilingual Embedding model supporting 100+ languages with 1024 dimensions",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="BAAI/bge-m3",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "baai",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": True,
                "languages": "100+",
            },
        ),
        "paraphrase-multilingual": EmbeddingModelConfig(
            id="paraphrase-multilingual",
            name="Paraphrase Multilingual",
            description="Multilingual paraphrase model with 768 dimensions supporting 50+ languages",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="paraphrase-multilingual-mpnet-base-v2",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "sentence-transformers",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "good",
                "multilingual": True,
                "languages": "50+",
            },
        ),
    }

    @classmethod
    def get_model(cls, model_id: str) -> Optional[EmbeddingModelConfig]:
        """Get a specific model configuration by ID."""
        return cls.MODELS.get(model_id)

    @classmethod
    def get_available_models(cls) -> List[EmbeddingModelConfig]:
        """Get all available models."""
        return [model for model in cls.MODELS.values() if model.is_available]

    @classmethod
    def get_models_by_type(cls, model_type: EmbeddingModelType) -> List[EmbeddingModelConfig]:
        """Get models filtered by type."""
        return [model for model in cls.MODELS.values() if model.model_type == model_type and model.is_available]

    @classmethod
    def get_free_models(cls) -> List[EmbeddingModelConfig]:
        """Get models that don't require API keys."""
        return [model for model in cls.MODELS.values() if model.is_available and not model.requires_api_key]

    @classmethod
    def get_paid_models(cls) -> List[EmbeddingModelConfig]:
        """Get models that require API keys."""
        return [model for model in cls.MODELS.values() if model.is_available and model.requires_api_key]

    @classmethod
    def validate_model_id(cls, model_id: str) -> bool:
        """Validate if a model ID exists and is available."""
        model = cls.get_model(model_id)
        return model is not None and model.is_available

    @classmethod
    def get_model_dimension(cls, model_id: str) -> Optional[int]:
        """Get the dimension for a specific model."""
        model = cls.get_model(model_id)
        return model.dimension if model else None

    @classmethod
    def get_model_display_name(cls, model_id: str) -> str:
        """Get the display name for a model."""
        model = cls.get_model(model_id)
        return model.name if model else model_id

    @classmethod
    def get_models_for_ui(cls) -> List[Dict]:
        """Get models formatted for UI consumption."""
        return [
            {
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "dimension": model.dimension,
                "requires_api_key": model.requires_api_key,
                "cost_per_token": model.cost_per_token,
                "metadata": model.metadata,
            }
            for model in cls.get_available_models()
        ]


# Convenience functions for backward compatibility
def get_embedding_model_config(model_id: str) -> Optional[EmbeddingModelConfig]:
    """Get embedding model configuration."""
    return EmbeddingModelRegistry.get_model(model_id)


def get_available_embedding_models() -> List[EmbeddingModelConfig]:
    """Get all available embedding models."""
    return EmbeddingModelRegistry.get_available_models()


def validate_embedding_model(model_id: str) -> bool:
    """Validate embedding model ID."""
    return EmbeddingModelRegistry.validate_model_id(model_id)


def get_embedding_dimension(model_id: str) -> Optional[int]:
    """Get embedding dimension for model."""
    return EmbeddingModelRegistry.get_model_dimension(model_id)


def format_embedding_model_name(model_id: str) -> str:
    """Format embedding model name for display."""
    return EmbeddingModelRegistry.get_model_display_name(model_id)
