"""Runtime settings for the knowledge & retrieval layer.

Every value can be overridden with an environment variable (or a `.env` file
at the repo root). Defaults are chosen so that `python -m ingest.build_all`
followed by `retrieve(...)` works on a laptop with no extra setup.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _flag(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(_env("DATA_DIR", str(ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STORE_DIR = DATA_DIR / "store"
INDEX_DIR = DATA_DIR / "index"
CACHE_DIR = DATA_DIR / "cache"

# SQLite file holding the exact Quran text + approved translations.
VERBATIM_DB = Path(_env("VERBATIM_DB", str(STORE_DIR / "verbatim.sqlite")))
GLOSSARY_PATH = Path(_env("GLOSSARY_PATH", str(DATA_DIR / "glossary.json")))

# Which retriever `retrieval.get_retriever()` returns: "hybrid" | "mock".
RETRIEVER = _env("RETRIEVER", "hybrid")

# Qdrant: set QDRANT_URL to use a server (docker compose); leave empty to use
# the embedded on-disk mode under data/index/qdrant (no server needed).
QDRANT_URL = _env("QDRANT_URL", "")
QDRANT_API_KEY = _env("QDRANT_API_KEY", "")
QDRANT_PATH = Path(_env("QDRANT_PATH", str(INDEX_DIR / "qdrant")))
QDRANT_COLLECTION = _env("QDRANT_COLLECTION", "islamic_kb")

EMBED_MODEL = _env("EMBED_MODEL", "BAAI/bge-m3")
DEVICE = _env("DEVICE", "cpu")  # "cuda" if the server has a GPU

# Confidence scoring of the fused candidates:
#   "bge"    - BAAI/bge-reranker-v2-m3 cross-encoder: best quality; needs a GPU for live use
#   "minilm" - multilingual MiniLM cross-encoder: fast on CPU, weaker
#   "none"   - the dense BGE-M3 cosine similarity (no extra model; fastest)
RERANKER = _env("RERANKER", "none").lower()
RERANK_CANDIDATES = int(_env("RERANK_CANDIDATES", "12"))
RERANK_QUERIES = int(_env("RERANK_QUERIES", "1"))  # how many of the queries to rerank against

# Evidence whose score is below this means "not enough evidence -> abstain".
# Scores are on different scales per RERANKER, so each has its own tuned default
# (see docs/EVALUATION.md); ABSTAIN_THRESHOLD overrides all of them.
ABSTAIN_THRESHOLDS = {"bge": 0.35, "minilm": 0.35, "none": 0.55}
ABSTAIN_THRESHOLD = float(_env("ABSTAIN_THRESHOLD", str(ABSTAIN_THRESHOLDS.get(RERANKER, 0.35))))

# Translation book ids on Quranpedia (both published by the King Fahd Complex).
QURAN_TRANSLATIONS = {
    "en": int(_env("QURAN_TRANSLATION_EN", "1948")),  # Hilali & Muhsin Khan
    "ur": int(_env("QURAN_TRANSLATION_UR", "1966")),  # Muhammad Ibrahim Junagarhi
}
QURAN_MUSHAF_ID = int(_env("QURAN_MUSHAF_ID", "1"))  # Hafs, matches the KFC print

# Optional live hadith search on dorar.net (off by default, see retrieval/dorar.py).
DORAR_ENABLED = _flag("DORAR_ENABLED", False)
DORAR_TIMEOUT = float(_env("DORAR_TIMEOUT", "8"))

# LLM (OpenAI-compatible endpoint). Only the evaluation's LLM-judge uses it here.
AI_BASE_URL = _env("AI_BASE_URL", "https://opencode.ai/zen/v1")
AI_API_KEY = _env("AI_API_KEY", "")
AI_MODEL = _env("AI_MODEL", "space-bunny-free")
