# Knowledge & retrieval layer image. The agent/API service can use this image as
# its base (FROM this, add agent/ + api/) or install requirements.txt the same way.
# BASE_IMAGE can point at a mirror if Docker Hub rate-limits you, e.g.
#   --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WORK_DIR=/var/lib/mueen \
    HF_HOME=/var/lib/mueen/models/hf

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY retrieval/ retrieval/
COPY ingest/ ingest/
COPY eval/ eval/
COPY data/glossary.json data/glossary.json
COPY data/embeddings/ data/embeddings/

# Java 21 for the optional Shamela step (ingest/shamela.py compiles a small Lucene reader).
# Copied from the official Temurin image so it works whatever Debian release the base uses.
COPY --from=eclipse-temurin:21-jdk /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk PATH="/opt/java/openjdk/bin:${PATH}"

VOLUME ["/var/lib/mueen"]
# Default: build (or refresh) the store and index into the volume, then exit.
# Shamela passages: kept in the volume, or assembled from a seed in /seed, or built when
# SHAMELA=1 (heavy). See ingest/kb_entry.sh.
CMD ["sh", "ingest/kb_entry.sh"]
