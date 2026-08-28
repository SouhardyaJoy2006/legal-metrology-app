"""bis_rag.embeddings package."""
from bis_rag.embeddings.models import get_active_model, MODEL_REGISTRY
from bis_rag.embeddings.embedder import get_embedder, Embedder
from bis_rag.embeddings.builder import build_standard_text, build_chunk_text

__all__ = [
    "get_active_model", "MODEL_REGISTRY",
    "get_embedder", "Embedder",
    "build_standard_text", "build_chunk_text",
]
