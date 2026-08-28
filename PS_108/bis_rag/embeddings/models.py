"""
bis_rag.embeddings.models
==========================
Model registry — maps model names to their configuration.

The active model is selected via .env:
    EMBEDDING_MODEL=BAAI/bge-m3
    EMBEDDING_DIM=1024          (must match the model)

Adding a new model: add an entry to MODEL_REGISTRY below.
No code changes elsewhere needed — the embedder reads from this registry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=False)
except ImportError:
    pass


@dataclass(frozen=True)
class ModelConfig:
    name: str               # HuggingFace model ID or "openai/<model>"
    dim: int                # embedding dimension
    # BGE and E5 models use an instruction prefix for retrieval tasks.
    # Improves retrieval accuracy significantly.
    query_prefix: str = ""  # prepended to user queries at search time
    doc_prefix: str = ""    # prepended to document text at embed time
    multilingual: bool = False
    backend: str = "sentence_transformers"  # or "flag_embedding" or "openai"


MODEL_REGISTRY: dict[str, ModelConfig] = {
    # ── Best choice: multilingual, dense+sparse hybrid, retrieval-optimised ──
    "BAAI/bge-m3": ModelConfig(
        name="BAAI/bge-m3",
        dim=1024,
        query_prefix="",    # BGE-M3 doesn't need a prefix (handles it internally)
        doc_prefix="",
        multilingual=True,
        backend="flag_embedding",
    ),
    # ── Strong multilingual alternative ───────────────────────────────────────
    "intfloat/multilingual-e5-large": ModelConfig(
        name="intfloat/multilingual-e5-large",
        dim=1024,
        query_prefix="query: ",
        doc_prefix="passage: ",
        multilingual=True,
        backend="sentence_transformers",
    ),
    "intfloat/multilingual-e5-base": ModelConfig(
        name="intfloat/multilingual-e5-base",
        dim=768,
        query_prefix="query: ",
        doc_prefix="passage: ",
        multilingual=True,
        backend="sentence_transformers",
    ),
    # ── English-only, high quality ────────────────────────────────────────────
    "BAAI/bge-large-en-v1.5": ModelConfig(
        name="BAAI/bge-large-en-v1.5",
        dim=1024,
        query_prefix="Represent this sentence for searching relevant passages: ",
        doc_prefix="",
        multilingual=False,
        backend="sentence_transformers",
    ),
    "BAAI/bge-base-en-v1.5": ModelConfig(
        name="BAAI/bge-base-en-v1.5",
        dim=768,
        query_prefix="Represent this sentence for searching relevant passages: ",
        doc_prefix="",
        multilingual=False,
        backend="sentence_transformers",
    ),
    # ── Lightweight / fast ─────────────────────────────────────────────────────
    "all-mpnet-base-v2": ModelConfig(
        name="all-mpnet-base-v2",
        dim=768,
        multilingual=False,
        backend="sentence_transformers",
    ),
    "all-MiniLM-L6-v2": ModelConfig(
        name="all-MiniLM-L6-v2",
        dim=384,
        multilingual=False,
        backend="sentence_transformers",
    ),
    # ── OpenAI API (paid) ──────────────────────────────────────────────────────
    "openai/text-embedding-3-small": ModelConfig(
        name="openai/text-embedding-3-small",
        dim=1536,
        multilingual=True,
        backend="openai",
    ),
    "openai/text-embedding-3-large": ModelConfig(
        name="openai/text-embedding-3-large",
        dim=3072,
        multilingual=True,
        backend="openai",
    ),
}


def get_active_model() -> ModelConfig:
    """
    Return the ModelConfig for the currently configured model.
    Reads EMBEDDING_MODEL from environment (set in .env).
    Falls back to BAAI/bge-m3 if not set.
    """
    model_name = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3").strip()
    if model_name not in MODEL_REGISTRY:
        available = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(
            f"Unknown EMBEDDING_MODEL={model_name!r}.\n"
            f"Available: {available}"
        )
    return MODEL_REGISTRY[model_name]


def get_expected_dim() -> int:
    """
    Return the expected embedding dimension from environment.
    Used to validate that the DB column matches the model.
    """
    env_dim = os.environ.get("EMBEDDING_DIM")
    if env_dim:
        return int(env_dim)
    return get_active_model().dim
