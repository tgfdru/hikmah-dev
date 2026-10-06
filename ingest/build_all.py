"""One command to build everything the retrieval layer needs.

    python -m ingest.build_all                 # download + Quran + Bayyinat + index
    python -m ingest.build_all --only quran    # just the verbatim store (fast, no models)
    python -m ingest.build_all --glossary      # also refresh data/glossary.json from Jamhara
    python -m ingest.build_all --shamela       # also add the selected Shamela books (Java 21+)

Steps (each is also runnable on its own):
  1. ingest.download     official files -> data/raw/          (~40 MB)
  2. ingest.quran        verbatim store + quran.jsonl          (seconds)
  3. ingest.bayyinat     Bayyinat Q&A -> bayyinat.jsonl        (~20 s)
  +  ingest.shamela      selected Shamela books -> shamela.jsonl  (opt-in: ~4.8 GB download
                         and ~25 min Java read, once; see docs/SOURCES.md)
  4. ingest.build_index  BGE-M3 vectors -> Qdrant, BM25        (~1 min with the committed
                         embedding cache; ~1.5 h on CPU without it)
data/glossary.json is committed, so step "glossary" is optional. The index takes
every file in processed/, so a shamela.jsonl built earlier (or copied in) is kept.
"""
from __future__ import annotations

import argparse
import time

from ingest import bayyinat, build_index, download, quran, shamela


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["quran", "bayyinat", "shamela", "index"], help="run a single step")
    ap.add_argument("--shamela", action="store_true", help="also build the Shamela passages")
    ap.add_argument("--glossary", action="store_true", help="refresh the Jamhara glossary too")
    ap.add_argument("--force-download", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    if args.only in (None, "quran", "bayyinat"):
        print("[1/4] downloading sources")
        download.download_quranpedia(args.force_download)
        download.download_langid(args.force_download)
        if args.only != "quran":
            download.download_bayyinat(args.force_download)
    if args.only in (None, "quran"):
        print("[2/4] building Quran verbatim store")
        quran.build()
    if args.only in (None, "bayyinat"):
        print("[3/4] parsing Bayyinat")
        bayyinat.build()
    if args.only == "shamela" or (args.only is None and args.shamela):
        print("[+] building Shamela passages")
        shamela.build()
    if args.glossary:
        from ingest import glossary

        print("[+] refreshing glossary from Jamhara")
        glossary.build()
    if args.only in (None, "index"):
        print("[4/4] building search index")
        build_index.build()
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
