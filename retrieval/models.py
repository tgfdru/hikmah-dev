"""Lazy loaders for the embedding and reranking models (shared by ingest and runtime)."""
from __future__ import annotations

import math
import os
import threading
from functools import lru_cache

from retrieval import config

# Reranker choices: "bge" (best quality, slow on CPU), "minilm" (fast, multilingual),
# "none" (use the dense similarity from BGE-M3 as the confidence score).
RERANKERS = {
    "bge": "BAAI/bge-reranker-v2-m3",
    "minilm": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
}
_lock = threading.Lock()


def _torch_threads() -> None:
    import torch

    n = os.getenv("TORCH_THREADS")
    if n:
        torch.set_num_threads(int(n))


@lru_cache(maxsize=1)
def get_embedder():
    with _lock:
        _torch_threads()
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(config.EMBED_MODEL, device=config.DEVICE)
        model.max_seq_length = 512
        return model


def embed(texts: list[str], batch_size: int = 16, show_progress: bool = False):
    """L2-normalized dense vectors (numpy float32, shape [n, 1024])."""
    return get_embedder().encode(
        texts, batch_size=batch_size, normalize_embeddings=True,
        show_progress_bar=show_progress, convert_to_numpy=True,
    )


@lru_cache(maxsize=2)
def get_reranker(name: str):
    with _lock:
        _torch_threads()
        from sentence_transformers import CrossEncoder

        model_id = RERANKERS.get(name, name)
        return CrossEncoder(model_id, device=config.DEVICE, max_length=384)


def rerank_scores(name: str, query: str, docs: list[str]) -> list[float]:
    """Relevance of each doc to the query, squashed to 0-1 with a sigmoid."""
    if not docs:
        return []
    import torch

    # Take raw logits (models ship different default activations) and apply one sigmoid.
    raw = get_reranker(name).predict([[query, d] for d in docs], batch_size=16,
                                     activation_fn=torch.nn.Identity(), convert_to_numpy=True)
    return [1 / (1 + math.exp(-float(x))) for x in raw]
