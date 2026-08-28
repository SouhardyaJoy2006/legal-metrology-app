"""
bis_rag.embeddings.embedder
============================
Loads the configured embedding model and generates dense vectors.

GPU is used automatically when available (CUDA via PyTorch).
Batch size is tuned for 8GB VRAM with BGE-M3 (batch=32).
Adjust EMBEDDING_BATCH_SIZE in .env if you run out of memory.

Model is loaded once per process — do not reinstantiate for each request.

Usage:
    from bis_rag.embeddings.embedder import get_embedder
    embedder = get_embedder()                    # loads model (slow, once)
    vecs = embedder.embed_documents(["text 1", "text 2"])
    query_vec = embedder.embed_query("search term")
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from bis_rag.embeddings.models import get_active_model, ModelConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 32   # safe default for 8GB VRAM with BGE-M3


class Embedder:
    """
    Wraps the underlying model (FlagEmbedding, sentence-transformers, or OpenAI)
    behind a uniform interface:
      embed_documents(texts)  → list[list[float]]
      embed_query(text)       → list[float]
    """

    def __init__(self, config: ModelConfig, batch_size: int = _DEFAULT_BATCH_SIZE):
        self.config = config
        self.batch_size = batch_size
        self._model = None
        self._load()

    def _load(self) -> None:
        backend = self.config.backend

        if backend == "flag_embedding":
            self._load_flag_embedding()
        elif backend == "sentence_transformers":
            self._load_sentence_transformers()
        elif backend == "openai":
            self._load_openai()
        else:
            raise ValueError(f"Unknown backend: {backend!r}")

    def _load_flag_embedding(self) -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except Exception as exc:
            logger.warning("FlagEmbedding load failed (%s), falling back to sentence-transformers.", exc)
            self._load_sentence_transformers()
            return

        import torch
        use_fp16 = torch.cuda.is_available()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading %s on %s (fp16=%s)", self.config.name, device, use_fp16)

        self._model = BGEM3FlagModel(
            self.config.name,
            use_fp16=use_fp16,
            device=device,
        )
        logger.info("Model loaded. Dimension: %d", self.config.dim)

    def _load_sentence_transformers(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers not installed. Run:\n"
                "  pip install sentence-transformers"
            ) from exc

        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading %s on %s", self.config.name, device)
        self._model = SentenceTransformer(self.config.name, device=device)
        logger.info("Model loaded. Dimension: %d", self.config.dim)

    def _load_openai(self) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError("openai not installed. Run:  pip install openai") from exc

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")

        self._model = openai.OpenAI(api_key=api_key)
        logger.info("OpenAI embedder ready. Model: %s", self.config.name)

    # ── Public API ────────────────────────────────────────────────────────────

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of document texts. Uses doc_prefix if configured.
        Returns one vector per text.
        """
        if self.config.doc_prefix:
            texts = [self.config.doc_prefix + t for t in texts]
        return self._embed_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        """
        Embed a single search query. Uses query_prefix if configured.
        Always returns exactly one vector.
        """
        prefixed = self.config.query_prefix + text if self.config.query_prefix else text
        return self._embed_batch([prefixed])[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        backend = self.config.backend
        if backend == "flag_embedding":
            return self._embed_flag(texts)
        elif backend == "sentence_transformers":
            return self._embed_st(texts)
        elif backend == "openai":
            return self._embed_openai(texts)
        raise ValueError(f"Unknown backend: {backend!r}")

    def _embed_flag(self, texts: list[str]) -> list[list[float]]:
        """BGE-M3 via FlagEmbedding. Returns dense vectors only."""
        result = self._model.encode(
            texts,
            batch_size=self.batch_size,
            max_length=512,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return result["dense_vecs"].tolist()

    def _embed_st(self, texts: list[str]) -> list[list[float]]:
        """sentence-transformers backend."""
        vecs = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        return vecs.tolist()

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """OpenAI API backend with automatic batching."""
        import time
        model_id = self.config.name.replace("openai/", "")
        all_vecs: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = self._model.embeddings.create(model=model_id, input=batch)
            all_vecs.extend(item.embedding for item in resp.data)
            if i + 100 < len(texts):
                time.sleep(0.05)
        return all_vecs


# ── Singleton factory ──────────────────────────────────────────────────────

_embedder_instance: Embedder | None = None


def get_embedder(force_reload: bool = False) -> Embedder:
    """
    Return the process-level Embedder singleton.
    Reads model from active config (EMBEDDING_MODEL in .env).
    Pass force_reload=True to reinitialise (e.g. after config change).
    """
    global _embedder_instance
    if _embedder_instance is None or force_reload:
        config = get_active_model()
        batch_size = int(os.environ.get("EMBEDDING_BATCH_SIZE", _DEFAULT_BATCH_SIZE))
        _embedder_instance = Embedder(config, batch_size=batch_size)
    return _embedder_instance
