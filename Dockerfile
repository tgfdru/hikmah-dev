# Knowledge & retrieval layer image. The agent/API service can use this image as
# its base (FROM this, add agent/ + api/) or install requirements.txt the same way.
FROM python:3.11-slim

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

VOLUME ["/var/lib/mueen"]
# Default: build (or refresh) the store and index into the volume, then exit.
CMD ["python", "-m", "ingest.build_all"]
