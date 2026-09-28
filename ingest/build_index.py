"""Build the search index: BGE-M3 vectors in Qdrant + a BM25 index.

    python -m ingest.build_index

Reads every data/processed/*.jsonl file. Embeddings are cached by content hash
in data/embeddings/ (committed to git), so rebuilding only embeds new or changed
text; a fresh clone rebuilds the index in about a minute instead of an hour.

Fixes over the plan's sketch: stable point ids (uuid5 of the logical id) so
indexing one source never overwrites another, and the collection is rebuilt
atomically from all sources together.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from retrieval import config
from retrieval.normalize_ar import strip_diacritics, tokenize

EMBED_CACHE_DIR = config.DATA_DIR / "embeddings"


def embed_text(r: dict) -> str:
    """Text that is embedded for dense search (never shown to users)."""
    if r["type"] == "quran":
        parts = [strip_diacritics(r["text_ar"]), r["translations"].get("en", "")]
        if r.get("topics"):
            parts.append("، ".join(r["topics"]))
        return "\n".join(p for p in parts if p)
    parts = [r.get("title", ""), strip_diacritics(r["text_ar"])]
    return "\n".join(p for p in parts if p)


def bm25_text(r: dict) -> str:
    if r["type"] == "quran":
        return " ".join([r["text_ar"], r["translations"].get("en", ""), " ".join(r.get("topics", []))])
    return " ".join([r.get("title", ""), r["text_ar"]])


def load_records() -> list[dict]:
    records, seen = [], set()
    for path in sorted(config.PROCESSED_DIR.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r["id"] in seen:
                    raise ValueError(f"duplicate id {r['id']} in {path.name}")
                seen.add(r["id"])
                records.append(r)
    if not records:
        raise SystemExit("No processed records. Run: python -m ingest.build_all")
    return records


class EmbeddingCache:
    """{sha1(model + text): float16 vector}, stored as .npz shards per source type."""

    def __init__(self, model: str):
        self.model = model
        self.dir = EMBED_CACHE_DIR / model.replace("/", "__")
        self.vectors: dict[str, np.ndarray] = {}
        for shard in sorted(self.dir.glob("*.npz")):
            data = np.load(shard)
            for k, v in zip(data["keys"], data["vectors"]):
                self.vectors[str(k)] = v
        self.dirty: dict[str, set[str]] = {}

    def key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}\n{text}".encode()).hexdigest()

    def put(self, shard: str, key: str, vec: np.ndarray) -> None:
        self.vectors[key] = vec.astype(np.float16)
        self.dirty.setdefault(shard, set()).add(key)

    def save(self, shard_keys: dict[str, list[str]]) -> None:
        """Rewrite each shard with exactly the keys currently used by that source type."""
        self.dir.mkdir(parents=True, exist_ok=True)
        for shard, keys in shard_keys.items():
            keys = sorted(set(k for k in keys if k in self.vectors))
            np.savez_compressed(self.dir / f"{shard}.npz", keys=np.array(keys),
                                vectors=np.stack([self.vectors[k] for k in keys]))


def embed_all(records: list[dict], batch: int = 32) -> np.ndarray:
    from retrieval.models import embed

    cache = EmbeddingCache(config.EMBED_MODEL)
    texts = [embed_text(r) for r in records]
    keys = [cache.key(t) for t in texts]
    shard_keys: dict[str, list[str]] = {}
    for r, k in zip(records, keys):
        shard_keys.setdefault(r["type"], []).append(k)
    missing = [i for i, k in enumerate(keys) if k not in cache.vectors]
    print(f"embeddings: {len(records) - len(missing)} cached, {len(missing)} to compute")
    # Longest first keeps memory stable; save progress regularly.
    missing.sort(key=lambda i: -len(texts[i]))
    t0 = time.time()
    for n, start in enumerate(range(0, len(missing), batch)):
        idx = missing[start:start + batch]
        vecs = embed([texts[i] for i in idx], batch_size=16)
        for i, v in zip(idx, vecs):
            cache.put(records[i]["type"], keys[i], v)
        done = start + len(idx)
        if n % 10 == 9 or done == len(missing):
            cache.save(shard_keys)
            rate = done / max(time.time() - t0, 1e-6)
            print(f"  {done}/{len(missing)} ({rate:.1f}/s, ~{(len(missing) - done) / rate / 60:.0f} min left)",
                  flush=True)
    cache.save(shard_keys)
    return np.stack([cache.vectors[k].astype(np.float32) for k in keys])


def payload(r: dict) -> dict:
    keep = ("id", "type", "text_ar", "translations", "source", "ref", "grade", "source_url",
            "title", "surah", "ayah", "parent_id", "part")
    return {k: r[k] for k in keep if k in r}


def write_qdrant(records: list[dict], vectors: np.ndarray) -> None:
    from qdrant_client import QdrantClient, models

    from retrieval.hybrid import point_id, qdrant_client

    client: QdrantClient = qdrant_client()
    name = config.QDRANT_COLLECTION
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        name, vectors_config=models.VectorParams(size=vectors.shape[1], distance=models.Distance.COSINE)
    )
    if config.QDRANT_URL:  # payload indexes only matter (and only exist) on a server
        client.create_payload_index(name, "type", models.PayloadSchemaType.KEYWORD)
    step = 256
    for start in range(0, len(records), step):
        client.upsert(name, points=[
            models.PointStruct(id=point_id(r["id"]), vector=v.tolist(), payload=payload(r))
            for r, v in zip(records[start:start + step], vectors[start:start + step])
        ])
    print(f"qdrant: {client.count(name).count} points in '{name}'")


def write_bm25_and_docs(records: list[dict]) -> None:
    from rank_bm25 import BM25Okapi

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    corpus = [tokenize(bm25_text(r)) for r in records]
    bm25 = BM25Okapi(corpus)
    with open(config.INDEX_DIR / "bm25.pkl", "wb") as f:
        pickle.dump({"ids": [r["id"] for r in records], "bm25": bm25}, f)
    with open(config.INDEX_DIR / "docs.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(payload(r), ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for r in records:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "embed_model": config.EMBED_MODEL,
                "counts": counts, "total": len(records)}
    (config.INDEX_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"bm25 + docs: {len(records)} records {counts}")


def build(embed_only: bool = False) -> None:
    records = load_records()
    vectors = embed_all(records)
    if embed_only:
        return
    write_qdrant(records, vectors)
    write_bm25_and_docs(records)


if __name__ == "__main__":
    build(embed_only="--embed-only" in sys.argv)
