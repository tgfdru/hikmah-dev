import pytest

from retrieval import config


def _store_built() -> bool:
    return config.VERBATIM_DB.exists()


def _index_built() -> bool:
    return (config.INDEX_DIR / "manifest.json").exists()


needs_store = pytest.mark.skipif(not _store_built(), reason="run: python -m ingest.build_all --only quran")
needs_index = pytest.mark.skipif(not _index_built(), reason="run: python -m ingest.build_all")
