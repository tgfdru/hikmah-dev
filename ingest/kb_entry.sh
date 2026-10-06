#!/bin/sh
# Entry point of the kb-build container: build (or refresh) the store and index into WORK_DIR.
#
# Shamela passages come, in order of preference, from:
#   1. WORK_DIR/processed/shamela.jsonl already in the volume (kept between deploys);
#   2. a seed mounted at /seed (shpart_00, shpart_01 … = base64 of shamela.jsonl.gz, split
#      because the Dokploy API accepts at most 1 MB per file) — built on another machine;
#   3. SHAMELA=1: build it here (needs ~4.8 GB download + Java; heavy, avoid on shared servers).
# HadeethEnc hadith (HADITH=1, the default): fetched from the hadeethenc.com API into the volume
# the first time (~1 h), then reused; set HADITH=0 to skip.
set -e
P="$WORK_DIR/processed"
mkdir -p "$P"
if [ ! -s "$P/shamela.jsonl" ] && ls /seed/shpart_* >/dev/null 2>&1; then
  echo "[seed] assembling processed/shamela.jsonl from /seed"
  cat /seed/shpart_* | base64 -d | gunzip > "$P/shamela.jsonl.tmp" && mv "$P/shamela.jsonl.tmp" "$P/shamela.jsonl"
  echo "[seed] $(wc -l < "$P/shamela.jsonl") passages"
fi
EXTRA=""
if [ "${HADITH:-1}" = 1 ]; then EXTRA="--hadith"; fi
if [ "$SHAMELA" = 1 ] && [ ! -s "$P/shamela.jsonl" ]; then
  python -m ingest.build_all --shamela $EXTRA
else
  python -m ingest.build_all $EXTRA
fi
rm -rf "$WORK_DIR/raw/shamela"   # the 4.8 GB download is not needed once shamela.jsonl exists
