"""Download the raw source files into data/raw/ (official dumps only).

    python -m ingest.download            # Quran + translations + Bayyinat PDF

Every Quranpedia file is checked against the SHA-256 published in the dump
manifest, so a corrupted or tampered download fails loudly.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

from retrieval import config

QURANPEDIA_DUMPS = "https://api.quranpedia.net/dumps"
# The dump page links translation books to http://localhost/... (a bug on their
# side); the files are actually served from this path.
QURANPEDIA_TRANSLATIONS = "https://api.quranpedia.net/translation-books"
QURANPEDIA_FILES = ["mushafs-1.json.gz", "surahs-index.json.gz", "topics.json.gz"]

BAYYINAT_PAGE = "https://dawa.center/file/7937"
BAYYINAT_PDF = "https://dawa.center/storage/files/AMYj6DfmHlSnZ766Zz0VlBNwmYtdwhAl31XMETlT.pdf"

USER_AGENT = "MueenKnowledgeBuilder/1.0 (+https://sheykak.com; hackathon research use)"


def _get(url: str, dest: Path, timeout: float = 300) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(4):
        try:
            with httpx.stream("GET", url, timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT}) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            tmp.replace(dest)
            return dest
        except httpx.HTTPError as exc:
            if attempt == 3:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  retry {url} in {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    return dest


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download_quranpedia(force: bool = False) -> Path:
    out = config.RAW_DIR / "quranpedia"
    manifest_path = _get(f"{QURANPEDIA_DUMPS}/manifest.json", out / "manifest.json", timeout=60)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {f["name"]: f.get("sha256") for f in manifest.get("files", [])}
    _get(f"{QURANPEDIA_DUMPS}/LICENSE.md", out / "LICENSE.md", timeout=60)

    for name in QURANPEDIA_FILES:
        dest = out / name
        if force or not dest.exists() or (expected.get(name) and _sha256(dest) != expected[name]):
            print(f"  downloading {name}")
            _get(f"{QURANPEDIA_DUMPS}/{name}", dest)
        digest = expected.get(name)
        if digest and _sha256(dest) != digest:
            raise RuntimeError(f"SHA-256 mismatch for {name}; delete it and retry")

    for lang, book_id in config.QURAN_TRANSLATIONS.items():
        dest = out / f"translation-{book_id}.json"
        if force or not dest.exists():
            print(f"  downloading translation {book_id} ({lang})")
            _get(f"{QURANPEDIA_TRANSLATIONS}/{book_id}.json", dest)
    print(f"Quranpedia dump version {manifest.get('version')} -> {out}")
    return out


def download_bayyinat(force: bool = False) -> Path:
    dest = config.RAW_DIR / "bayyinat" / "bayyinat.pdf"
    if force or not dest.exists():
        print("  downloading Bayyinat PDF (~17 MB)")
        _get(BAYYINAT_PDF, dest)
    return dest


def download_langid(force: bool = False) -> Path:
    from retrieval.langid import MODEL_PATH, MODEL_URL

    if force or not MODEL_PATH.exists():
        print("  downloading fastText language-id model (lid.176.ftz, ~1 MB)")
        _get(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def main() -> None:
    force = "--force" in sys.argv
    download_quranpedia(force)
    download_bayyinat(force)
    download_langid(force)


if __name__ == "__main__":
    main()
